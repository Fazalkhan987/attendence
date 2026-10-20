"""Lightweight IoU tracker + temporal vote smoothing, to stop flicker and avoid one-frame false accepts."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from .types import Detection, MatchStatus, RecognitionResult


def iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


@dataclass
class SmoothedDecision:
    status: MatchStatus
    person_id: str | None = None
    name: str | None = None
    similarity: float | None = None       # mean similarity of the winning votes


@dataclass
class Track:
    track_id: int
    bbox: tuple
    window: int
    min_votes: int
    missed: int = 0
    age: int = 0
    last_embedded_age: int = -10**9
    history: deque = field(default_factory=deque)
    last_result: RecognitionResult | None = None

    def __post_init__(self):
        self.history = deque(maxlen=self.window)

    def add_result(self, r: RecognitionResult) -> None:
        """Quality-rejected results carry no identity evidence and are not added to the vote window."""
        self.last_result = r
        if r.status in (MatchStatus.REJECTED_QUALITY, MatchStatus.REJECTED_LIVENESS):
            return
        self.history.append(r)

    def decision(self) -> SmoothedDecision:
        if not self.history:
            lr = self.last_result
            return SmoothedDecision(lr.status if lr else MatchStatus.UNCERTAIN)
        votes = Counter(r.person_id for r in self.history if r.status == MatchStatus.RECOGNIZED)
        if votes:
            (pid, n), *rest = votes.most_common()
            second = rest[0][1] if rest else 0
            if n >= self.min_votes and n > second:
                wins = [r for r in self.history if r.person_id == pid and r.status == MatchStatus.RECOGNIZED]
                return SmoothedDecision(MatchStatus.RECOGNIZED, pid, wins[-1].name,
                                        sum(r.similarity for r in wins) / len(wins))
        unknown = sum(1 for r in self.history if r.status == MatchStatus.UNKNOWN)
        if len(self.history) >= self.min_votes and unknown > len(self.history) / 2:
            return SmoothedDecision(MatchStatus.UNKNOWN)
        return SmoothedDecision(MatchStatus.UNCERTAIN)       # still verifying / conflicting evidence


class SimpleTracker:
    def __init__(self, window: int, min_votes: int, max_missed: int, iou_threshold: float = 0.3):
        self.window, self.min_votes, self.max_missed, self.iou_threshold = window, min_votes, max_missed, iou_threshold
        self.tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, detections: list[Detection]) -> list[tuple[Track, Detection]]:
        pairs = sorted(((iou(t.bbox, d.bbox), tid, di) for tid, t in self.tracks.items()
                        for di, d in enumerate(detections)), reverse=True)
        used_t, used_d, matched = set(), set(), []
        for score, tid, di in pairs:
            if score < self.iou_threshold:
                break
            if tid in used_t or di in used_d:
                continue
            used_t.add(tid), used_d.add(di)
            matched.append((self.tracks[tid], detections[di]))
        for di, d in enumerate(detections):
            if di not in used_d:
                t = Track(self._next_id, d.bbox, self.window, self.min_votes)
                self._next_id += 1
                self.tracks[t.track_id] = t
                matched.append((t, d))
        for tid in list(self.tracks):
            if tid not in used_t and all(self.tracks[tid] is not m[0] for m in matched):
                self.tracks[tid].missed += 1
                if self.tracks[tid].missed > self.max_missed:
                    del self.tracks[tid]
        for t, d in matched:
            t.bbox, t.missed, t.age = d.bbox, 0, t.age + 1
        return matched
