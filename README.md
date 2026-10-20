# face-engine: face detection & recognition core

A modular, standalone Python engine (no web framework) for enrolling people and recognising them from a webcam.
It is the AI core for a future smart-attendance system; FastAPI and React are **not** part of this repository.

**Pipeline:** SCRFD detector -> 5-point alignment -> ArcFace (`w600k_r50`) embedding -> cosine matching against a
SQLite gallery -> quality / margin / temporal-vote decision.

## 1. Honest status

| Area | State |
|---|---|
| Registration (webcam / folder import, quality gates, duplicate checks, update, add samples, delete) | Implemented; **tested with a synthetic backend** |
| Recognition decision logic (threshold, margin, UNKNOWN / UNCERTAIN / quality-rejected, multi-face) | Implemented; **tested with a synthetic backend** |
| Temporal smoothing + IoU tracking | Implemented; unit-tested |
| SQLite storage, admin auth, lockout, audit log, optional embedding encryption | Implemented; unit-tested |
| Evaluation (FAR/FRR/TAR, EER, open-set ID, per-condition, leakage xtlib import asynccontextmanager
import cv2, numpy as np
from fastapi import FastAPI, UploadFile
from face_engine.config import load_config
from face_engine.engine import FaceEngine

@asynccontextmanachecks, latency) | Implemented; pipeline tested on synthetic data |
| **InsightFace SCRFD + ArcFace backend** | **Written against insightface 0.7.3's API from documentation knowledge; NEVER executed** (see below) |
| **Live webcam window / guided capture** | **Implemented; never run against a real camera** |
| Anti-spoofing / liveness | **Interface only.** `NullLivenessChecker` does nothing. No model is shipped or tested |
| Real-world accuracy | **Unmeasured.** No benchmark numbers exist for this project. Run `face-engine evaluate` on your data |

What the authoring environment could and could not do: it had no internet, no camera, no model files and no `pytest`.
So the 51 tests were run with a small stand-in runner (`pytest` is only used for `raises`, `approx`, `tmp_path`), and the
InsightFace backend, model download and webcam code were only import-checked. **Run `pytest` and `face-engine check`
yourself first.** If an InsightFace call differs in your installed version, only `backends/insightface_backend.py` changes.

## 2. Why SCRFD + ArcFace (single pipeline)

InsightFace ships both models from one ONNX model pack (`buffalo_l`: `det_10g.onnx` SCRFD, `w600k_r50.onnx` ArcFace
ResNet-50 trained on WebFace600K). They share the same 5-landmark convention, run on CPU through ONNX Runtime and
need no PyTorch/TensorFlow. FaceNet was not added: a second recognition framework would add complexity without a
demonstrated advantage here. The detector and embedder are separate interfaces (`interfaces.py`), so either can be replaced.

**Licence warning:** InsightFace *code* is MIT, but its pretrained model packs are distributed for non-commercial research.
Obtain a commercial licence or use different weights before any commercial deployment. Verify the current terms yourself.

## 3. Installation

Requires Python 3.10+ (developed on 3.12). Check wheel availability for your platform; `insightface` may compile a
C extension, so Windows needs "Microsoft C++ Build Tools", Linux needs `build-essential python3-dev`.

```bash
# Linux / macOS
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

# Windows (PowerShell)
py -3.12 -m venv .venv ; .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Compatibility notes (unverified here, check on install):
- `numpy<2` is a conservative pin because insightface 0.7.3 predates NumPy 2; relax only after testing.
- Install **either** `opencv-python` (live window) **or** `opencv-python-headless` (servers), never both.
- `onnxruntime` (CPU) **or** `onnxruntime-gpu`, never both. Set `providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]` for GPU.
- Linux camera access needs membership of the `video` group; macOS/Windows prompt for camera permission.

### Models

```bash
face-engine init-models      # downloads buffalo_l to ~/.insightface/models/buffalo_l/ (needs internet)
face-engine check            # loads both models and prints the embedding dimension
```
Offline: copy `det_10g.onnx` and `w600k_r50.onnx` into that folder (or set `model_path` in the config).

### Tests
```bash
pip install pytest && pytest -q
```

## 4. Usage

```bash
face-engine init-admin                                    # set the administrator passcode (>= 10 chars)
face-engine register --id S001 --name "Ada Lovelace" --department CS --class A1 --webcam
face-engine register --id S002 --name "Alan Turing" --from-dir ./photos/alan
face-engine add-samples --id S001 --webcam --samples 5
face-engine update --id S001 --department Math
face-engine list
face-engine live                                          # q / Esc quits
face-engine delete --id S002                              # removes the person, embeddings, compacts the DB
face-engine --config config/default.toml evaluate --dataset ./dataset --target-far 0.001
```
Scripts can set `FACE_ENGINE_ADMIN_PASSCODE` instead of the interactive prompt.

### How enrollment works
- Every image must contain exactly one face, pass the quality gates (size, detection confidence, sharpness, brightness,
  contrast, roll, and yaw/pitch **proxies** from landmarks, edge clipping) and be non-redundant (cosine < 0.98 to other samples).
- Samples that disagree with the rest of the batch (cosine to batch centroid < 0.30) are rejected: this catches a wrong person in an import folder.
- At least `min_samples` (5) must pass or **nothing is saved** (registration is one SQLite transaction).
- A face matching an existing person above `duplicate_identity_threshold` raises `PossibleDuplicateIdentityError` (admin may override).
- Each accepted sample is stored as its own L2-normalised float32 vector (raw bytes, no pickle). **No face images are stored.**
- Adding a person only adds rows; the network is never retrained.

### How recognition decides
Per face: quality gate -> (liveness, if configured) -> embedding -> per-person score (`max`, `topk_mean` or `centroid` over that person's samples) ->
- `RECOGNIZED` only if best >= threshold **and** best - runner-up >= margin
- `UNCERTAIN` if within `uncertain_band` below the threshold or ambiguous between two people
- `UNKNOWN` otherwise; `REJECTED_QUALITY` / `REJECTED_LIVENESS` if the evidence is unusable.

Live mode adds per-face tracking and a vote window: a name is shown only after `min_votes` of the last `window` checks agree.
Detection confidence and similarity are displayed separately.

### Thresholds are NOT calibrated
Defaults (`threshold = 0.45`, quality limits, etc.) are provisional starting points in the range commonly used for ArcFace-style
cosine scores. They are not validated for your cameras or population. Calibrate:

1. Build `dataset/` (layout in `evaluation/dataset.py`): `enroll`, `val`, `val_unknown`, `test`, `test_unknown`, optional `tags.json`, `detection_gt.json`.
2. `face-engine evaluate ...` picks the threshold on **validation** for your target FAR, then reports on **test** with that frozen threshold.
3. Read `report.md`: FAR/FRR/TAR with 95% Wilson intervals, misidentification rate, unknown-acceptance rate, per-condition breakdown, latency, hardware.
4. Put the chosen value in `[recognition] threshold`. For attendance, prefer a low FAR (wrongly marking someone present) and accept a higher FRR.

The runner refuses datasets where the same image appears in two splits, where "unknown" people are enrolled, or where
`val_unknown` and `test_unknown` share identities. It also states when a target FAR is smaller than `1/N` impostor trials and cannot be verified.

## 5. Architecture

```
src/face_engine/
  interfaces.py     FaceDetector, FaceEmbedder, LivenessChecker (replaceable parts)
  backends/         InsightFace SCRFD + ArcFace (lazy imports); registry for other backends
  alignment.py      5-point ArcFace alignment      quality.py   sample quality checks
  gallery.py        in-memory matching             storage/     SQLite (+ optional encryption)
  registration.py   RegistrationService            recognition.py  RecognitionService
  tracking.py       IoU tracker + vote smoothing   security.py  admin auth / sessions
  engine.py         FaceEngine (composition root)  evaluation/ metrics, dataset, runner
  webcam.py, cli.py the only OpenCV-window / terminal code
```
Services take and return plain data (`RecognitionResult.to_dict()`, `EnrollmentReport.to_dict()`) and raise typed exceptions
(`exceptions.py`), so a web layer can map them to HTTP codes.

## 6. Future FastAPI integration (illustrative, not implemented)

```python
# app.py: sketch only
from contextlib import asynccontextmanager
import cv2, numpy as np
from fastapi import FastAPI, UploadFile
from face_engine.config import load_config
from face_engine.engine import FaceEngine

@asynccontextmanager
async def lifespan(app):
    app.state.engine = FaceEngine.from_config(load_config("config/default.toml"))   # load models once
    yield
    app.state.engine.close()

app = FastAPI(lifespan=lifespan)

@app.post("/recognize")
def recognize(file: UploadFile):            # sync def => FastAPI runs it in a thread pool
    frame = cv2.imdecode(np.frombuffer(file.file.read(), np.uint8), cv2.IMREAD_COLOR)
    return [r.to_dict() for r in app.state.engine.recognition.recognize_frame(frame)]
```
Notes for that phase: the DB layer is thread-safe via a lock but is single-process SQLite (move to PostgreSQL for multi-worker deployments);
add real user accounts/roles on top of `AdminAuth`; rate-limit and authenticate every endpoint; apply the same image-size limits as `load_image`.

## 7. Security and privacy

Implemented: admin passcode (salted PBKDF2-SHA256, constant-time compare, lockout), expiring sessions required by every mutating
service call, audit log (actor, action, person ID; never embeddings or images), owner-only file permissions on POSIX, `secure_delete` +
`VACUUM` on deletion, optional Fernet encryption of embeddings (`encrypt_embeddings = true`, key from the env var `FACE_ENGINE_DB_KEY`;
generate with `python -c "from face_engine.storage.crypto import VectorCipher as V; print(V.generate_key())"`), model-ID binding so incompatible embeddings are never mixed, no image storage, logs without biometric payloads.

Not covered: full-disk encryption, key management, network security, backups (back up encrypted, and remember backups contain biometric data), user roles, and the OS-level protection of the process.

**Embeddings are biometric data.** Obtain informed consent, define retention, and check applicable law (GDPR, BIPA and similar) before deployment.
Treat the stored embeddings as sensitive even though they are not images.

**Anti-spoofing:** a normal webcam plus a recognition model does **not** reliably stop printed photos or screen replays. `LivenessChecker` is a hook:
`require_liveness = true` makes start-up fail until a real checker is supplied (fail-closed). Evaluate any liveness model separately
(e.g. against ISO/IEC 30107-3 style attack types) before relying on it.

## 8. Known limitations
- No measured accuracy; thresholds provisional; the real backend and webcam path unexecuted by the author.
- Pose "angles" are landmark heuristics, not calibrated head pose. Quality thresholds are provisional.
- Enrollment does not enforce pose diversity, only quality; two near-frontal batches will give a narrow gallery.
- One detector pass per frame; very small, heavily occluded (mask, sunglasses), extreme-pose or low-light faces will be missed or rejected. Detection is not claimed to be reliable in all conditions.
- Accuracy can differ across demographic groups; evaluate on the population you will serve.
- Look-alikes and identical twins can exceed the duplicate/recognition thresholds. The margin rule reduces, but cannot eliminate, confusion.
- SQLite, single process; gallery is held in RAM and matched by brute force (fine for thousands of people, not millions).
- Evaluation measures what its dataset represents; small datasets give wide confidence intervals.
