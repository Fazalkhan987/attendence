"""Evaluation runner: calibrate a threshold on VALIDATION data, then report on TEST data with that frozen threshold.

Nothing here touches the production database: the gallery is built in memory from dataset/enroll.
"""
from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path

import numpy as np

from ..exceptions import DatasetError
from ..frames import load_image
from ..gallery import Gallery
from ..quality import assess_face_quality
from . import metrics as M
from .dataset import Dataset, Item, load_dataset

LIMITATIONS = [
    "Results describe ONLY this dataset, these cameras/conditions and this hardware; they do not transfer automatically.",
    "Rates with few trials have wide confidence intervals (see ci95). A target FAR below 1/N_impostor_trials cannot be verified.",
    "Condition tags (lighting/pose/distance) are as labelled by whoever prepared the dataset.",
    "Anti-spoofing / presentation-attack detection is NOT evaluated here.",
    "Dataset demographics are not analysed; check performance across the groups you will actually serve.",
]


def hardware_info() -> dict:
    info = {"platform": platform.platform(), "python": platform.python_version(),
            "processor": platform.processor() or platform.machine(), "cpu_count": os.cpu_count()}
    try:
        import onnxruntime as ort
        info["onnxruntime"] = ort.__version__
        info["onnxruntime_providers"] = ort.get_available_providers()
    except ImportError:
        info["onnxruntime"] = "not installed"
    return info


def _largest(dets):
    return max(dets, key=lambda d: d.area) if dets else None


def _process(engine, item: Item, lat_det: list, lat_emb: list, quality_cfg=None):
    img = load_image(item.path, engine.cfg.enrollment.max_file_mb, engine.cfg.enrollment.max_image_side)
    t0 = time.perf_counter()
    dets = engine.detector.detect(img)
    lat_det.append((time.perf_counter() - t0) * 1000)
    det = _largest(dets)
    if det is None or det.landmarks is None:
        return None, dets, None
    t0 = time.perf_counter()
    emb = engine.embedder.embed(img, det)
    lat_emb.append((time.perf_counter() - t0) * 1000)
    q = assess_face_quality(img, det, quality_cfg) if quality_cfg else None
    return emb, dets, q


def run_evaluation(engine, dataset_dir, out_dir, target_far: float = 1e-3, warmup: int = 3) -> dict:
    ds: Dataset = load_dataset(dataset_dir)
    if not ds.items["enroll"]:
        raise DatasetError("dataset has no enroll images")
    lat_det: list[float] = []
    lat_emb: list[float] = []
    pred_boxes: dict[str, list] = {}

    # warm-up so the first-call overhead does not distort latency
    for it in ds.items["enroll"][:warmup]:
        _process(engine, it, [], [])

    # 1) gallery from enrollment images
    ids, vecs, enroll_fail = [], [], 0
    for it in ds.items["enroll"]:
        emb, _, _ = _process(engine, it, lat_det, lat_emb)
        if emb is None:
            enroll_fail += 1
            continue
        ids.append(it.identity); vecs.append(emb)
    if not vecs:
        raise DatasetError("no enrollment image produced an embedding")
    rc = engine.cfg.recognition
    gal = Gallery(rc.score_mode, rc.topk)
    gal.set_data(ids, np.stack(vecs))

    # 2) probes
    def probes_for(known_split: str, unknown_split: str):
        out, no_det, qrej = [], 0, 0
        for split, known in ((known_split, True), (unknown_split, False)):
            for it in ds.items[split]:
                emb, dets, q = _process(engine, it, lat_det, lat_emb, engine.cfg.quality_live)
                if it.rel in ds.detection_gt:
                    pred_boxes[it.rel] = [list(d.bbox) for d in sorted(dets, key=lambda d: -d.score)]
                if emb is None:
                    no_det += 1
                    continue
                if q is not None and not q.ok:
                    qrej += 1
                out.append(M.Probe(it.identity if known else None, gal.person_scores(emb),
                                   ds.tags.get(it.rel, {}), it.rel))
        return out, no_det, qrej

    val, val_nodet, val_qrej = probes_for("val", "val_unknown")
    test, test_nodet, test_qrej = probes_for("test", "test_unknown")

    summary: dict = {"enrollment_images_without_usable_face": enroll_fail}
    report: dict = {"summary": summary, "dataset": ds.counts(), "hardware": hardware_info(),
                    "config": {"score_mode": rc.score_mode, "margin": rc.margin, "target_far": target_far,
                               "model_id": engine.embedder.model_id},
                    "limitations": LIMITATIONS}

    # 3) calibrate on validation
    vg, vi = M.verification_scores(val)
    if len(vg) == 0 or len(vi) == 0:
        raise DatasetError("validation split needs genuine and impostor trials (val + val_unknown or >=2 people)")
    cal = M.select_threshold_at_far(vi, target_far)
    thr = cal["threshold"]
    report["calibration"] = {**cal, "n_genuine_trials": len(vg), "val_eer": M.equal_error_rate(vg, vi),
                             "val_at_selected_threshold": M.verification_rates(vg, vi, thr),
                             "roc_validation": M.roc_points(vg, vi, 25),
                             "note": "threshold selected on validation only; test results below use it unchanged"}
    summary["selected_threshold"] = thr
    summary["configured_threshold_in_use"] = rc.threshold

    # 4) frozen-threshold test report
    tg, ti = M.verification_scores(test)
    report["test"] = {
        "probes_scored": len(test), "images_without_detection": test_nodet, "images_failing_live_quality_gate": test_qrej,
        "verification_at_selected_threshold": M.verification_rates(tg, ti, thr) if len(tg) and len(ti) else None,
        "verification_at_configured_threshold": M.verification_rates(tg, ti, rc.threshold) if len(tg) and len(ti) else None,
        "identification_at_selected_threshold": M.identification_metrics(test, thr, rc.margin),
        "by_condition": M.breakdown_by_tag(test, thr, rc.margin),
    }
    report["validation_images_without_detection"] = val_nodet
    if ds.detection_gt:
        report["detection"] = M.detection_precision_recall(pred_boxes, ds.detection_gt)
    else:
        report["detection"] = "not evaluated: no detection_gt.json supplied"
    report["latency"] = {"detector_ms": M.latency_stats(lat_det), "embedder_ms": M.latency_stats(lat_emb),
                         "note": "per image on the hardware above, including preprocessing inside each model"}
    summary["test_identification"] = report["test"]["identification_at_selected_threshold"]["correct_identification_rate"]
    summary["test_misidentification"] = report["test"]["identification_at_selected_threshold"]["misidentification_rate"]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def _fmt(r) -> str:
    if not isinstance(r, dict) or r.get("value") is None:
        return "n/a"
    lo, hi = r["ci95"]
    return f"{r['value']:.4f} ({r['count']}/{r['n']}, 95% CI {lo:.4f}-{hi:.4f})"


def render_markdown(rep: dict) -> str:
    L = ["# Face recognition evaluation report", "", "## Dataset"]
    for s, c in rep["dataset"].items():
        L.append(f"- {s}: {c['images']} images, {c['identities']} identities")
    L += ["", "## Hardware", *(f"- {k}: {v}" for k, v in rep["hardware"].items()), "", "## Calibration (validation split)"]
    c = rep["calibration"]
    L += [f"- target FAR: {c['target_far']} | impostor trials: {c['n_impostor_trials']} | "
          f"min resolvable FAR: {c['min_resolvable_far']:.2e} | resolvable: {c['target_resolvable']}",
          f"- selected threshold: {c['threshold']:.4f} | validation EER: {c['val_eer']['eer']:.4f}"]
    t = rep["test"]
    L += ["", "## Test split (threshold frozen from validation)"]
    v = t["verification_at_selected_threshold"]
    if v:
        L += [f"- FAR: {_fmt(v['FAR'])}", f"- FRR: {_fmt(v['FRR'])}", f"- TAR: {_fmt(v['TAR'])}"]
    i = t["identification_at_selected_threshold"]
    L += [f"- correct identification: {_fmt(i['correct_identification_rate'])}",
          f"- known person rejected: {_fmt(i['known_rejected_rate'])}",
          f"- misidentification: {_fmt(i['misidentification_rate'])}",
          f"- unknown person wrongly accepted: {_fmt(i['unknown_false_accept_rate'])}",
          f"- images with no detected face: {t['images_without_detection']}"]
    if t["by_condition"]:
        L += ["", "### By condition"]
        for k, vals in t["by_condition"].items():
            for name, m in vals.items():
                L.append(f"- {k}={name}: correct-ID {_fmt(m['correct_identification_rate'])}, "
                         f"unknown-accepted {_fmt(m['unknown_false_accept_rate'])}")
    d = rep["detection"]
    L += ["", "## Detection"]
    L.append(d if isinstance(d, str) else f"- precision {_fmt(d['precision'])}, recall {_fmt(d['recall'])} (IoU>={d['iou_threshold']})")
    lt = rep["latency"]
    L += ["", "## Latency", f"- detector: {lt['detector_ms']}", f"- embedder: {lt['embedder_ms']}",
          "", "## Limitations", *(f"- {x}" for x in rep["limitations"])]
    return "\n".join(L) + "\n"
