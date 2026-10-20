"""Registration service: enrolment, sample management, updates and deletion. All mutations need an AdminSession."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from .config import EnrollmentConfig, QualityConfig
from .exceptions import (ConfigError, DuplicatePersonError, FaceEngineError, ImageLoadError, InsufficientSamplesError,
                         InvalidFrameError, PossibleDuplicateIdentityError, ValidationError)
from .frames import iter_image_files, load_image, validate_frame
from .gallery import Gallery, l2_normalize
from .interfaces import FaceDetector, FaceEmbedder
from .quality import assess_face_quality
from .security import AdminAuth, AdminSession
from .storage.db import Database, PersonRecord, validate_person_id

log = logging.getLogger(__name__)


@dataclass
class ImageSample:
    source: str                              # file name or "webcam#3" - never a full biometric payload
    image: np.ndarray | None = None
    error: str | None = None                 # set when loading failed (corrupt file, ...)


@dataclass
class SampleReport:
    index: int
    source: str
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    quality: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class EnrollmentReport:
    person_id: str
    samples: list[SampleReport]
    total_samples: int = 0                   # samples stored for the person after this operation

    @property
    def accepted(self) -> int:
        return sum(s.accepted for s in self.samples)

    @property
    def rejected(self) -> int:
        return len(self.samples) - self.accepted

    def to_dict(self) -> dict:
        return {"person_id": self.person_id, "accepted": self.accepted, "rejected": self.rejected,
                "total_samples": self.total_samples, "samples": [s.to_dict() for s in self.samples]}


def load_directory(directory: str | Path, cfg: EnrollmentConfig) -> list[ImageSample]:
    """Import every image in a folder; unreadable files become error samples instead of aborting the batch."""
    out = []
    for p in iter_image_files(directory):
        try:
            out.append(ImageSample(p.name, load_image(p, cfg.max_file_mb, cfg.max_image_side)))
        except ImageLoadError as e:
            out.append(ImageSample(p.name, None, str(e)))
    return out


def samples_from_frames(frames: Sequence[np.ndarray], prefix: str = "webcam") -> list[ImageSample]:
    return [ImageSample(f"{prefix}#{i + 1}", f) for i, f in enumerate(frames)]


class RegistrationService:
    def __init__(self, db: Database, detector: FaceDetector, embedder: FaceEmbedder, gallery: Gallery,
                 auth: AdminAuth, cfg: EnrollmentConfig, quality_cfg: QualityConfig):
        self.db, self.detector, self.embedder, self.gallery = db, detector, embedder, gallery
        self.auth, self.cfg, self.quality_cfg = auth, cfg, quality_cfg
        db.bind_model(embedder.model_id, embedder.embedding_dim)
        gallery.reload(db)

    # ---- single-image analysis (also used for live capture feedback) -------
    def analyze_image(self, image, source: str = "image", index: int = 0) -> tuple[SampleReport, np.ndarray | None]:
        def reject(reason, quality=None):
            return SampleReport(index, source, False, [reason] if isinstance(reason, str) else reason,
                                quality or {}), None
        try:
            validate_frame(image)
        except InvalidFrameError as e:
            return reject(f"invalid image: {e}")
        dets = self.detector.detect(image)
        if not dets:
            return reject("no face detected")
        if len(dets) > 1 and self.cfg.reject_multiple_faces:
            return reject(f"{len(dets)} faces detected; individual enrolment needs exactly one")
        det = max(dets, key=lambda d: d.area)
        q = assess_face_quality(image, det, self.quality_cfg)
        if not q.ok:
            return reject(q.reasons, q.metrics)
        if det.landmarks is None:
            return reject("detector returned no landmarks (needed for alignment)", q.metrics)
        emb = self.embedder.embed(image, det)
        return SampleReport(index, source, True, [], q.metrics), emb

    def _analyze_batch(self, samples: list[ImageSample], existing: np.ndarray | None,
                       capacity: int) -> tuple[list[SampleReport], list[np.ndarray]]:
        reports: list[SampleReport] = []
        embs: list[tuple[int, np.ndarray]] = []
        for i, s in enumerate(samples):
            if s.image is None:
                reports.append(SampleReport(i, s.source, False, [s.error or "could not load image"]))
                continue
            rep, emb = self.analyze_image(s.image, s.source, i)
            reports.append(rep)
            if emb is not None:
                embs.append((i, emb))

        # redundancy + consistency + capacity filters (operate on embeddings only)
        kept: list[tuple[int, np.ndarray]] = []
        base = [] if existing is None or not len(existing) else list(existing)
        for i, e in embs:
            ref = base + [k[1] for k in kept]
            if ref and float(np.max(np.stack(ref) @ e)) >= self.cfg.redundancy_threshold:
                reports[i].accepted, reports[i].reasons = False, ["near-identical to another sample"]
                continue
            kept.append((i, e))
        if kept:
            pool = np.stack(base + [k[1] for k in kept])
            centroid = l2_normalize(pool.mean(axis=0))
            survivors = []
            for i, e in kept:
                if float(e @ centroid) < self.cfg.consistency_threshold:
                    reports[i].accepted, reports[i].reasons = False, ["does not match the other samples (different person?)"]
                else:
                    survivors.append((i, e))
            kept = survivors
        for i, _ in kept[max(capacity, 0):]:
            reports[i].accepted, reports[i].reasons = False, ["sample limit per person reached"]
        kept = kept[: max(capacity, 0)]
        return reports, [e for _, e in kept]

    def _duplicate_candidates(self, embs: list[np.ndarray], exclude: str | None) -> list[tuple[str, str, float]]:
        best: dict[str, float] = {}
        ex = {exclude} if exclude else None
        for e in embs:
            for pid, s in self.gallery.person_scores(e, ex).items():
                best[pid] = max(best.get(pid, -1.0), s)
        found = [(pid, self.gallery.names.get(pid, ""), s) for pid, s in best.items()
                 if s >= self.cfg.duplicate_identity_threshold]
        return sorted(found, key=lambda t: -t[2])

    # ---- public operations --------------------------------------------------
    def register_person(self, session: AdminSession, person_id: str, full_name: str, samples: list[ImageSample],
                        department: str | None = None, class_name: str | None = None, extra: dict | None = None,
                        allow_possible_duplicate: bool = False) -> EnrollmentReport:
        s = self.auth.require(session)
        validate_person_id(person_id)
        if not full_name or not full_name.strip():
            raise ValidationError("full_name is required")
        if self.db.person_exists(person_id):
            raise DuplicatePersonError(f"person_id '{person_id}' already exists")

        reports, embs = self._analyze_batch(samples, None, self.cfg.max_samples_per_person)
        report = EnrollmentReport(person_id, reports, len(embs))
        if len(embs) < self.cfg.min_samples:
            raise InsufficientSamplesError(
                f"{len(embs)} usable sample(s); at least {self.cfg.min_samples} required. Nothing was saved.", report)
        cands = self._duplicate_candidates(embs, None)
        if cands and not allow_possible_duplicate:
            raise PossibleDuplicateIdentityError(
                "this face closely matches an existing registration: "
                + ", ".join(f"{pid} ({sim:.2f})" for pid, _, sim in cands), cands)

        with self.db.transaction():                      # all-or-nothing
            self.db.create_person(person_id, full_name, department, class_name, extra)
            self.db.add_embeddings(person_id, embs)
            self.db.audit(s.actor, "register", person_id, f"samples={len(embs)}"
                          + (" forced_duplicate" if cands else ""))
        self.gallery.reload(self.db)
        log.info("registered %s with %d samples", person_id, len(embs))
        return report

    def add_samples(self, session: AdminSession, person_id: str, samples: list[ImageSample],
                    allow_possible_duplicate: bool = False) -> EnrollmentReport:
        s = self.auth.require(session)
        person = self.db.get_person(person_id)
        existing = self.db.get_person_embeddings(person_id)
        reports, embs = self._analyze_batch(samples, existing, self.cfg.max_samples_per_person - person.sample_count)
        report = EnrollmentReport(person_id, reports, person.sample_count)
        if not embs:
            raise InsufficientSamplesError("no usable new samples; nothing was saved", report)
        cands = self._duplicate_candidates(embs, person_id)
        if cands and not allow_possible_duplicate:
            raise PossibleDuplicateIdentityError(
                "new samples closely match a different registered person: "
                + ", ".join(f"{pid} ({sim:.2f})" for pid, _, sim in cands), cands)
        with self.db.transaction():
            self.db.add_embeddings(person_id, embs)
            self.db.audit(s.actor, "add_samples", person_id, f"added={len(embs)}")
        report.total_samples = person.sample_count + len(embs)
        self.gallery.reload(self.db)
        return report

    def update_person(self, session: AdminSession, person_id: str, full_name: str | None = None,
                      department: str | None = None, class_name: str | None = None,
                      extra: dict | None = None) -> PersonRecord:
        s = self.auth.require(session)
        self.db.update_person(person_id, full_name, department, class_name, extra)
        self.db.audit(s.actor, "update", person_id)
        self.gallery.reload(self.db)
        return self.db.get_person(person_id)

    def delete_person(self, session: AdminSession, person_id: str) -> int:
        """Remove the person, every embedding, and compact the DB file. Returns embeddings deleted."""
        s = self.auth.require(session)
        n = self.db.delete_person(person_id)
        self.db.audit(s.actor, "delete", person_id, f"embeddings_deleted={n}")
        self.gallery.reload(self.db)
        log.info("deleted %s (%d embeddings)", person_id, n)
        return n

    # read-only helpers (no admin session needed in-process; an API layer should still protect them)
    def get_person(self, person_id: str) -> PersonRecord:
        return self.db.get_person(person_id)

    def list_persons(self) -> list[PersonRecord]:
        return self.db.list_persons()
