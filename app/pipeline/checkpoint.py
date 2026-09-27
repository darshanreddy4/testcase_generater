"""On-disk checkpointing so an interrupted pipeline run (network drop, crash,
Ctrl-C) can resume from the last successfully completed stage instead of
re-calling the LLM for everything from scratch.

Checkpoints are keyed by a `run_id` derived from the requirement content, so
re-running the exact same input automatically picks up where it left off.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from app.config import settings

T = TypeVar("T", bound=BaseModel)

_TEXT_STAGE_FILENAME = "{stage}.txt"
_MODEL_STAGE_FILENAME = "{stage}.json"


def make_run_id(text: str, source_type: str) -> str:
    """Deterministic ID for a requirement so identical reruns resume automatically."""
    digest = hashlib.sha256(f"{source_type}::{text}".encode("utf-8")).hexdigest()
    return digest[:20]


class CheckpointStore:
    def __init__(self, run_id: str, base_dir: Optional[str] = None) -> None:
        self.run_id = run_id
        self.dir = Path(base_dir or settings.checkpoint_dir) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def has(self, stage: str) -> bool:
        return (self.dir / _MODEL_STAGE_FILENAME.format(stage=stage)).exists() or (
            self.dir / _TEXT_STAGE_FILENAME.format(stage=stage)
        ).exists()

    def load(self, stage: str, schema: Type[T]) -> Optional[T]:
        path = self.dir / _MODEL_STAGE_FILENAME.format(stage=stage)
        if not path.exists():
            return None
        return schema.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, stage: str, data: BaseModel) -> None:
        path = self.dir / _MODEL_STAGE_FILENAME.format(stage=stage)
        path.write_text(data.model_dump_json(indent=2), encoding="utf-8")

    def load_text(self, stage: str) -> Optional[str]:
        path = self.dir / _TEXT_STAGE_FILENAME.format(stage=stage)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def save_text(self, stage: str, text: str) -> None:
        path = self.dir / _TEXT_STAGE_FILENAME.format(stage=stage)
        path.write_text(text, encoding="utf-8")

    def clear(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
