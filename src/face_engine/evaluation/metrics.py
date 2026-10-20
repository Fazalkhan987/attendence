"""Pure-numpy evaluation metrics. No model or camera dependencies, so they are unit-testable."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n. Small samples give honestly wide intervals."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rate(k: int, n: int) -> dict:
    lo, hi = wilson_interval(k, n)
    return {"value": (k / n) if n else None, "count": k, "n": n, "ci95": [lo, hi]}


def verification_rates(genuine: np.ndarray, impostor: np.ndarray, threshold: float) -> dict:
    """Accept when score >= threshold. FAR over impostor trials, FRR/TAR over genuine trials."""
    g, i = np.asarray(genuine), np.asarray(impostor)
    fa, ta = int((i >= threshold).sum()), int((g >= threshold).sum())
    return {"threshold": float(threshold), "FAR": rate(fa, len(i)),
            "FRR": rate(len(g) - ta, len(g)), "TAR": rate(ta, len(g))}


def select_threshold_at_far(impostor: np.ndarray, target_far: float) -> dict:
    """Smallest threshold whose empirical FAR <= target_far. Reports when the data cannot resolve the target."""
    imp = np.sort(np.asarray(impostor))[::-1]
    n = len(imp)
    if n == 0:
        raise ValueError("no impostor scores")
    k = int(math.floor(target_far * n))          # at most k impostors may be accepted
    thr = float(np.nextafter(imp[k], np.inf)) if k < n else float(imp[-1])
    resolvable = (1.0 / n) <= target_far
    return {"threshold": thr, "target_far": target_far, "n_impostor_trials": n,
            "min_resolvable_far": 1.0 / n, "target_resolvable": resolvable}


def equal_error_rate(genuine: np.ndarray, impostor: np.ndarray) -> dict:
    g, i = np.asarray(genuine), np.asarray(impostor)
    cands = np.unique(np.concatenate([g, i]))
    best = None
    for t in cands:
        far = float((i >= t).mean())
        frr = float((g < t).mean())
        gap = abs(far - frr)
        if best is None or gap < best[0]:
            best = (gap, float(t), (far + frr) / 2)
    return {"eer": best[2], "threshold": best[1]}


def roc_points(genuine, impostor, n: int = 50) -> list[dict]:
    g, i = np.asarray(genuine), np.asarray(impostor)
    lo, hi = float(min(g.min(), i.min())), float(max(g.max(), i.max()))
    return [{"threshold": float(t), "FAR": float((i >= t).mean()), "TAR": float((g >= t).mean())}
            for t in np.linspace(lo, hi, n)]


@dataclass
class Probe:
    """One probe image's outcome against the enrolled gallery."""
    true_id: str | None             # None => person is NOT enrolled (unknown / impostor identity)
    scores: dict[str, float]        # per-enrolled-person score
    tags: dict[str, str]
    path: str = ""


def verification_scores(probes: list[Probe]) -> tuple[np.ndarray, np.ndarray]:
    gen, imp = [], []
    for p in probes:
        for pid, s in p.scores.items():
            (gen if pid == p.true_id else imp).append(s)
    return np.asarray(gen), np.asarray(imp)


def identification_metrics(probes: list[Probe], threshold: float, margin: float = 0.0) -> dict:
    """Open-set identification with the same accept rule the live system uses (threshold + runner-up margin)."""
    kn = [p for p in probes if p.true_id is not None and p.scores]
    un = [p for p in probes if p.true_id is None and p.scores]

    def top(p):
        ranked = sorted(p.scores.items(), key=lambda kv: -kv[1])
        best = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else None
        accepted = best[1] >= threshold and (second is None or best[1] - second >= margin)
        return best[0], accepted

    correct_accept = wrong_accept = reject = rank1 = 0
    for p in kn:
        pid, acc = top(p)
        rank1 += pid == p.true_id
        if not acc:
            reject += 1
        elif pid == p.true_id:
            correct_accept += 1
        else:
            wrong_accept += 1
    false_accept_unknown = sum(top(p)[1] for p in un)
    return {
        "known_probes": len(kn), "unknown_probes": len(un),
        "closed_set_rank1_accuracy": rate(rank1, len(kn)),
        "correct_identification_rate": rate(correct_accept, len(kn)),     # accepted AND right person
        "known_rejected_rate": rate(reject, len(kn)),                     # false reject at identification level
        "misidentification_rate": rate(wrong_accept, len(kn)),            # accepted but WRONG person (worst case)
        "unknown_false_accept_rate": rate(false_accept_unknown, len(un)),
        "unknown_correct_rejection_rate": rate(len(un) - false_accept_unknown, len(un)),
    }


def breakdown_by_tag(probes: list[Probe], threshold: float, margin: float) -> dict:
    keys = sorted({k for p in probes for k in p.tags})
    out: dict = {}
    for k in keys:
        out[k] = {}
        for v in sorted({p.tags[k] for p in probes if k in p.tags}):
            sub = [p for p in probes if p.tags.get(k) == v]
            m = identification_metrics(sub, threshold, margin)
            out[k][v] = {"known_probes": m["known_probes"], "unknown_probes": m["unknown_probes"],
                         "correct_identification_rate": m["correct_identification_rate"],
                         "misidentification_rate": m["misidentification_rate"],
                         "unknown_false_accept_rate": m["unknown_false_accept_rate"]}
    return out


def box_iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def detection_precision_recall(pred: dict[str, list], gt: dict[str, list], iou_thr: float = 0.5) -> dict:
    """pred/gt: image -> list of [x1,y1,x2,y2]. Greedy IoU matching (preds should be sorted by score by the caller)."""
    tp = fp = fn = 0
    for img, gboxes in gt.items():
        used: set[int] = set()
        for pb in pred.get(img, []):
            best, bj = 0.0, -1
            for j, gb in enumerate(gboxes):
                if j in used:
                    continue
                v = box_iou(pb, gb)
                if v > best:
                    best, bj = v, j
            if best >= iou_thr:
                tp += 1
                used.add(bj)
            else:
                fp += 1
        fn += len(gboxes) - len(used)
    return {"iou_threshold": iou_thr, "tp": tp, "fp": fp, "fn": fn,
            "precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn)}


def latency_stats(ms: list[float]) -> dict:
    if not ms:
        return {"n": 0}
    a = np.asarray(ms)
    return {"n": len(ms), "mean_ms": float(a.mean()), "p50_ms": float(np.percentile(a, 50)),
            "p95_ms": float(np.percentile(a, 95)), "max_ms": float(a.max())}
