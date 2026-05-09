"""Shared helpers for codex-pet-maker scripts."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

ROW_NAMES = (
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
)
ROW_FRAME_COUNTS = {
    "idle": 6,
    "running-right": 8,
    "running-left": 8,
    "waving": 4,
    "jumping": 5,
    "failed": 8,
    "waiting": 6,
    "running": 6,
    "review": 6,
}
ROW_INDEX = {name: idx for idx, name in enumerate(ROW_NAMES)}

ATLAS_W = 1536
ATLAS_H = 1872
CELL_W = 192
CELL_H = 208
GRID_COLS = 8
GRID_ROWS = 9


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    value = value.strip("-")
    if not value:
        raise ValueError("slug is empty after normalization")
    return value


def new_run_id(slug: str) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    nano = time.time_ns() % 1_000_000
    return f"{stamp}-{nano:06d}-{slug}"


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def update_row(path: Path, row: str, patch: dict[str, Any]) -> None:
    data = read_manifest(path)
    rows = data.setdefault("rows", {})
    rows[row] = {**rows.get(row, {}), **patch}
    write_manifest(path, data)


def codex_pets_dir() -> Path:
    home = os.environ.get("CODEX_HOME")
    base = Path(home) if home else Path.home() / ".codex"
    return base / "pets"
