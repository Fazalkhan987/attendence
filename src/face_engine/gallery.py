"""In-memory gallery of enrolled embeddings and similarity scoring.

Enrollment embeddings: every accepted sample is stored individually (L2-normalised). At match time a
per-person score is derived from the per-sample cosine similarities:

* max        - best single sample (default; robust when samples cover different poses/lighting)
* topk_mean  - mean of the k best samples (smoother, less sensitive to one lucky sample)
* centroid   - cosine to the re-normalised mean embedding (one template per person)

Adding a person only appends vectors: no neural network retraining is involved.
"""
from __future__ import annotations

import numpy as np

from .storage.db import Database


def l2_normalize(v: np.ndarray, axis: int = -1) -> np.ndarray:
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    return (v / np.maximum(n, 1e-12)).astype(np.float32)


class Gallery:
    def __init__(self, score_mode: str = "max", topk: int = 3):
        self.score_mode = score_mode
        self.topk = topk
        self.names: dict[str, str] = {}
        self._ids: list[str] = []
        self._matrix = np.zeros((0, 0), dtype=np.float32)
        self._rows: dict[str, np.ndarray] = {}
        self._centroids: dict[str, np.ndarray] = {}

    # ---- loading ---------------------------------------------------------
    def set_data(self, row_person_ids: list[str], matrix: np.ndarray, names: dict[str, str] | None = None) -> None:
        self._ids = list(row_person_ids)
        self._matrix = l2_normalize(np.asarray(matrix, dtype=np.float32)) if len(row_person_ids) else \
            np.zeros((0, 0), dtype=np.float32)
        arr = np.asarray(self._ids)
        self._rows = {pid: np.flatnonzero(arr == pid) for pid in dict.fromkeys(self._ids)}
        self._centroids = {pid: l2_normalize(self._matrix[idx].mean(axis=0)) for pid, idx in self._rows.items()}
        self.names = dict(names or {})

    def reload(self, db: Database) -> None:
        ids, mat = db.load_all_embeddings()
        self.set_data(ids, mat, {p.person_id: p.full_name for p in db.list_persons()})

    @property
    def num_persons(self) -> int:
        return len(self._rows)

    @property
    def num_samples(self) -> int:
        return len(self._ids)

    @property
    def empty(self) -> bool:
        return not self._ids

    # ---- scoring ---------------------------------------------------------
    def person_scores(self, emb: np.ndarray, exclude: set[str] | None = None) -> dict[str, float]:
        q = l2_normalize(np.asarray(emb, dtype=np.float32))
        out: dict[str, float] = {}
        if self.empty:
            return out
        sims = self._matrix @ q
        for pid, idx in self._rows.items():
            if exclude and pid in exclude:
                continue
            if self.score_mode == "centroid":
                out[pid] = float(self._centroids[pid] @ q)
            elif self.score_mode == "topk_mean":
                s = np.sort(sims[idx])[::-1][: self.topk]
                out[pid] = float(s.mean())
            else:
                out[pid] = float(sims[idx].max())
        return out

    def top2(self, emb: np.ndarray, exclude: set[str] | None = None) -> list[tuple[str, float]]:
        scores = self.person_scores(emb, exclude)
        return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:2]
