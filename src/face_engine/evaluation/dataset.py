"""Evaluation dataset layout + leakage checks.

dataset/
  enroll/<person_id>/*.jpg          images used to build the gallery
  val/<person_id>/*.jpg             DIFFERENT images of the enrolled people (threshold calibration)
  val_unknown/<identity>/*.jpg      people who are NOT enrolled (threshold calibration)
  test/<person_id>/*.jpg            held-out images of enrolled people (final report)
  test_unknown/<identity>/*.jpg     held-out non-enrolled people (final report)
  tags.json          optional: {"test/p1/a.jpg": {"lighting": "low", "pose": "profile", "distance": "far"}}
  detection_gt.json  optional: {"test/p1/a.jpg": [[x1,y1,x2,y2], ...]}
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..exceptions import DatasetError
from ..frames import iter_image_files

SPLITS = ("enroll", "val", "val_unknown", "test", "test_unknown")


@dataclass
class Item:
    path: Path
    rel: str
    split: str
    identity: str
    sha256: str


@dataclass
class Dataset:
    root: Path
    items: dict[str, list[Item]] = field(default_factory=dict)
    tags: dict[str, dict[str, str]] = field(default_factory=dict)
    detection_gt: dict[str, list] = field(default_factory=dict)

    def counts(self) -> dict:
        return {s: {"images": len(v), "identities": len({i.identity for i in v})} for s, v in self.items.items()}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_dataset(root: str | Path) -> Dataset:
    r = Path(root)
    if not r.is_dir():
        raise DatasetError(f"dataset directory not found: {r}")
    ds = Dataset(r)
    for split in SPLITS:
        ds.items[split] = []
        d = r / split
        if not d.is_dir():
            continue
        for sub in sorted(x for x in d.iterdir() if x.is_dir()):
            for f in iter_image_files(sub):
                ds.items[split].append(Item(f, f"{split}/{sub.name}/{f.name}", split, sub.name, _sha(f)))
    for name, attr in (("tags.json", "tags"), ("detection_gt.json", "detection_gt")):
        f = r / name
        if f.exists():
            setattr(ds, attr, json.loads(f.read_text(encoding="utf-8")))
    check_leakage(ds)
    return ds


def check_leakage(ds: Dataset) -> None:
    """Raise DatasetError when splits share image content or when 'unknown' people are actually enrolled."""
    seen: dict[str, Item] = {}
    for split in SPLITS:
        for it in ds.items.get(split, []):
            prev = seen.get(it.sha256)
            if prev is not None:
                raise DatasetError(f"data leakage: identical image content in '{prev.rel}' and '{it.rel}'")
            seen[it.sha256] = it
    enrolled = {i.identity for i in ds.items.get("enroll", [])}
    for split in ("val_unknown", "test_unknown"):
        clash = {i.identity for i in ds.items.get(split, [])} & enrolled
        if clash:
            raise DatasetError(f"'{split}' contains enrolled identities: {sorted(clash)}")
    v = {i.identity for i in ds.items.get("val_unknown", [])}
    t = {i.identity for i in ds.items.get("test_unknown", [])}
    if v & t:
        raise DatasetError(f"val_unknown and test_unknown share identities {sorted(v & t)}: "
                           f"thresholds would be tuned on the test people")
    for split in ("val", "test"):
        extra = {i.identity for i in ds.items.get(split, [])} - enrolled
        if extra:
            raise DatasetError(f"'{split}' has identities that are not in 'enroll': {sorted(extra)}")
