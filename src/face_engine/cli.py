"""Command-line entry point (`face-engine ...`). A deliberately thin wrapper over the services."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from .config import load_config
from .exceptions import FaceEngineError, InsufficientSamplesError, PossibleDuplicateIdentityError
from .registration import load_directory, samples_from_frames
from .security import AdminAuth


def _admin_session(engine):
    pw = os.environ.get("FACE_ENGINE_ADMIN_PASSCODE") or getpass.getpass("Admin passcode: ")
    return engine.auth.authenticate(pw)


def _print_report(rep) -> None:
    print(f"accepted {rep.accepted}, rejected {rep.rejected}, total stored {rep.total_samples}")
    for s in rep.samples:
        if not s.accepted:
            print(f"  - {s.source}: {'; '.join(s.reasons)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="face-engine")
    p.add_argument("--config", help="path to TOML config (default: built-in defaults)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-admin", help="set the administrator passcode")
    sub.add_parser("init-models", help="download the InsightFace buffalo_l model pack (needs internet)")
    sub.add_parser("check", help="verify models load and run a smoke test")
    sub.add_parser("list", help="list registered people")

    r = sub.add_parser("register", help="register a new person")
    r.add_argument("--id", required=True)
    r.add_argument("--name", required=True)
    r.add_argument("--department")
    r.add_argument("--class", dest="class_name")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--webcam", type=int, nargs="?", const=0, metavar="INDEX")
    g.add_argument("--from-dir")
    r.add_argument("--samples", type=int, default=8, help="webcam frames to capture")
    r.add_argument("--allow-possible-duplicate", action="store_true")

    a = sub.add_parser("add-samples", help="add more face samples to an existing person")
    a.add_argument("--id", required=True)
    g2 = a.add_mutually_exclusive_group(required=True)
    g2.add_argument("--webcam", type=int, nargs="?", const=0, metavar="INDEX")
    g2.add_argument("--from-dir")
    a.add_argument("--samples", type=int, default=5)

    u = sub.add_parser("update", help="update person metadata")
    u.add_argument("--id", required=True)
    u.add_argument("--name")
    u.add_argument("--department")
    u.add_argument("--class", dest="class_name")

    d = sub.add_parser("delete", help="delete a person and all biometric data")
    d.add_argument("--id", required=True)
    d.add_argument("--yes", action="store_true")

    lv = sub.add_parser("live", help="live webcam recognition")
    lv.add_argument("--camera", type=int)

    ev = sub.add_parser("evaluate", help="evaluate on a labelled dataset (see docs/EVALUATION.md)")
    ev.add_argument("--dataset", required=True)
    ev.add_argument("--out", default="eval_report")
    ev.add_argument("--target-far", type=float, default=1e-3)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    try:
        if args.cmd == "init-admin":
            auth = AdminAuth(cfg.admin_path, cfg.security)
            old = None
            if auth.is_initialized():
                old = getpass.getpass("Current passcode: ")
            new = getpass.getpass("New passcode: ")
            if new != getpass.getpass("Repeat: "):
                print("passcodes differ"); return 2
            auth.set_passcode(new, old)
            print("admin passcode set")
            return 0
        if args.cmd == "init-models":
            from .backends.insightface_backend import download_models
            print("models in:", download_models())
            return 0

        from .engine import FaceEngine
        engine = FaceEngine.from_config(cfg)
        try:
            return _run(args, cfg, engine)
        finally:
            engine.close()
    except InsufficientSamplesError as e:
        print(f"ERROR: {e}")
        if e.report:
            _print_report(e.report)
        return 1
    except PossibleDuplicateIdentityError as e:
        print(f"ERROR: {e}\nRe-run with --allow-possible-duplicate if this is really a different person.")
        return 1
    except FaceEngineError as e:
        print(f"ERROR: {e}")
        return 1


def _gather(args, engine):
    if args.from_dir:
        return load_directory(args.from_dir, engine.cfg.enrollment)
    from .webcam import capture_samples
    return samples_from_frames(capture_samples(engine, args.webcam, args.samples))


def _run(args, cfg, engine) -> int:
    if args.cmd == "check":
        print(f"detector: {type(engine.detector).__name__}\nembedder: {engine.embedder.model_id} "
              f"(dim {engine.embedder.embedding_dim})\npeople: {engine.gallery.num_persons}, samples: {engine.gallery.num_samples}")
        return 0
    if args.cmd == "list":
        for p in engine.registration.list_persons():
            print(f"{p.person_id}\t{p.full_name}\t{p.department or ''}\t{p.class_name or ''}\tsamples={p.sample_count}")
        return 0
    if args.cmd == "live":
        from .webcam import run_live
        run_live(engine, args.camera)
        return 0
    if args.cmd == "evaluate":
        from .evaluation.evaluate import run_evaluation
        report = run_evaluation(engine, args.dataset, args.out, target_far=args.target_far)
        print(json.dumps(report["summary"], indent=2))
        return 0

    s = _admin_session(engine)
    reg = engine.registration
    if args.cmd == "register":
        rep = reg.register_person(s, args.id, args.name, _gather(args, engine), args.department, args.class_name,
                                  allow_possible_duplicate=args.allow_possible_duplicate)
        print(f"registered {args.id}"); _print_report(rep)
    elif args.cmd == "add-samples":
        _print_report(reg.add_samples(s, args.id, _gather(args, engine)))
    elif args.cmd == "update":
        print(reg.update_person(s, args.id, args.name, args.department, args.class_name).to_dict())
    elif args.cmd == "delete":
        if not args.yes and input(f"Permanently delete {args.id} and all face data? [y/N] ").lower() != "y":
            print("aborted"); return 1
        print(f"deleted {args.id} ({reg.delete_person(s, args.id)} embeddings removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
