from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_pet_request() -> dict:
    return {
        "name": "Foxy",
        "description": "A small orange fox with white belly and a black-tipped tail.",
        "references": [],
    }


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    return d


@pytest.fixture
def write_request(run_dir: Path, sample_pet_request: dict):
    def _write(req: dict | None = None) -> Path:
        target = run_dir / "pet_request.json"
        target.write_text(json.dumps(req if req is not None else sample_pet_request))
        return target

    return _write
