"""Manifest: the data contract between split / remake / merge."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from weibo.errors import ManifestError

MANIFEST_VERSION = 1


@dataclass
class SegmentEntry:
    index: int
    source_path: str
    frame_path: str
    segment_url: str | None = None
    remade_path: str | None = None
    task_id: str | None = None
    status: str = "pending"


@dataclass
class Manifest:
    version: int = MANIFEST_VERSION
    source: str = ""
    preset: str = "h2v"
    prompt: str = ""
    segment_seconds: int = 15
    segments: list[SegmentEntry] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not path.exists():
            raise ManifestError(f"Manifest not found: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestError(f"Invalid manifest JSON: {exc}") from exc

        segments = [SegmentEntry(**s) for s in raw.pop("segments", [])]
        return cls(**raw, segments=segments)

    @property
    def job_dir(self) -> Path:
        """Infer the job directory from the first segment's source_path parent."""
        if self.segments:
            return Path(self.segments[0].source_path).parent.parent
        return Path(".")

    def pending_segments(self) -> list[SegmentEntry]:
        return [s for s in self.segments if s.status == "pending"]

    def succeeded_segments(self) -> list[SegmentEntry]:
        return [s for s in self.segments if s.status == "succeeded"]
