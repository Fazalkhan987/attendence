"""Typed configuration loaded from TOML (stdlib tomllib; no extra dependency)."""
from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import ConfigError


@dataclass
class PathsConfig:
    data_dir: str = "data"


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class DetectorConfig:
    backend: str = "insightface_scrfd"
    model_path: str = "~/.insightface/models/buffalo_l/det_10g.onnx"
    det_size: list = field(default_factory=lambda: [640, 640])
    min_confidence: float = 0.5
    providers: list = field(default_factory=lambda: ["CPUExecutionProvider"])


@dataclass
class EmbedderConfig:
    backend: str = "insightface_arcface"
    model_path: str = "~/.insightface/models/buffalo_l/w600k_r50.onnx"
    model_id: str = "insightface-buffalo_l-w600k_r50"
    providers: list = field(default_factory=lambda: ["CPUExecutionProvider"])


@dataclass
class QualityConfig:
    min_face_px: float = 80
    min_det_score: float = 0.70
    min_blur: float = 50.0
    min_brightness: float = 50.0
    max_brightness: float = 220.0
    min_contrast: float = 25.0
    max_yaw_proxy: float = 0.45
    max_roll_deg: float = 25.0
    min_pitch_ratio: float = 0.30
    max_pitch_ratio: float = 0.70
    max_border_clip: float = 0.10


def _live_quality() -> QualityConfig:
    return QualityConfig(
        min_face_px=50, min_det_score=0.5, min_blur=25.0, min_brightness=40.0, max_brightness=230.0,
        min_contrast=15.0, max_yaw_proxy=0.6, max_roll_deg=35.0, min_pitch_ratio=0.25,
        max_pitch_ratio=0.75, max_border_clip=0.2)


@dataclass
class EnrollmentConfig:
    min_samples: int = 5
    max_samples_per_person: int = 20
    duplicate_identity_threshold: float = 0.60
    redundancy_threshold: float = 0.98
    consistency_threshold: float = 0.30
    reject_multiple_faces: bool = True
    max_image_side: int = 1920
    max_file_mb: float = 20


@dataclass
class RecognitionConfig:
    threshold: float = 0.45
    uncertain_band: float = 0.05
    margin: float = 0.05
    score_mode: str = "max"
    topk: int = 3
    require_liveness: bool = False


@dataclass
class LiveConfig:
    camera_index: int = 0
    recognition_interval: int = 5
    window: int = 7
    min_votes: int = 4
    max_track_missed: int = 10
    detect_max_side: int = 640
    max_read_failures: int = 30


@dataclass
class SecurityConfig:
    admin_file: str = "admin.json"
    session_ttl_s: int = 900
    max_failed_attempts: int = 5
    lockout_s: int = 300
    pbkdf2_iterations: int = 600_000
    min_passcode_length: int = 10
    encrypt_embeddings: bool = False
    key_env: str = "FACE_ENGINE_DB_KEY"


@dataclass
class AppConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    quality_enroll: QualityConfig = field(default_factory=QualityConfig)
    quality_live: QualityConfig = field(default_factory=_live_quality)
    enrollment: EnrollmentConfig = field(default_factory=EnrollmentConfig)
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    live: LiveConfig = field(default_factory=LiveConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    @property
    def data_dir(self) -> Path:
        return Path(self.paths.data_dir).expanduser()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "face_engine.sqlite3"

    @property
    def admin_path(self) -> Path:
        return self.data_dir / self.security.admin_file


def _build(cls, data: dict, section: str):
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ConfigError(f"Unknown key(s) in [{section}]: {sorted(unknown)}")
    return cls(**data)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load config from TOML. With path=None the built-in defaults are used."""
    cfg = AppConfig()
    if path is None:
        return cfg
    p = Path(path)
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {p}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {p}: {e}") from e
    sections = {f.name for f in dataclasses.fields(AppConfig)}
    unknown = set(raw) - sections
    if unknown:
        raise ConfigError(f"Unknown config section(s): {sorted(unknown)}")
    for name, values in raw.items():
        setattr(cfg, name, _build(type(getattr(cfg, name)), values, name))
    validate_config(cfg)
    return cfg


def validate_config(cfg: AppConfig) -> None:
    r = cfg.recognition
    if not -1.0 <= r.threshold <= 1.0:
        raise ConfigError("recognition.threshold must be within [-1, 1] (cosine similarity)")
    if r.score_mode not in ("max", "topk_mean", "centroid"):
        raise ConfigError("recognition.score_mode must be max | topk_mean | centroid")
    e = cfg.enrollment
    if e.min_samples < 1 or e.min_samples > e.max_samples_per_person:
        raise ConfigError("enrollment.min_samples must be in [1, max_samples_per_person]")
    if cfg.live.min_votes > cfg.live.window:
        raise ConfigError("live.min_votes cannot exceed live.window")
