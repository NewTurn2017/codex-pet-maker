from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


def _bootstrap_run_dir(tmp_path: Path) -> Path:
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "x", "references": []}))
    out = tmp_path / "runs"
    res = subprocess.run(
        [sys.executable, "-m", "scripts.prepare", "--request", str(req), "--output-dir", str(out)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    return Path(json.loads(res.stdout)["run_dir"])


def _drop_decoded(run_dir: Path, row: str, color=(0, 200, 0), shape_color=(255, 100, 50)) -> Path:
    img = Image.new("RGB", (192 * 6, 208), color)
    pixels = img.load()
    for cell in range(6):
        cx = cell * 192 + 96
        for y in range(40, 168):
            for x in range(cx - 40, cx + 40):
                pixels[x, y] = shape_color
    target = run_dir / "decoded" / f"{row}.png"
    img.save(target)
    return target


def _has_rembg_smoke() -> bool:
    return os.environ.get("REMBG_SMOKE") == "1"


def test_matte_skips_when_no_decoded(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.matte", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr


@pytest.mark.slow
def test_matte_writes_rgba_outputs(tmp_path: Path):
    if not _has_rembg_smoke():
        pytest.skip("REMBG_SMOKE != 1")
    run_dir = _bootstrap_run_dir(tmp_path)
    _drop_decoded(run_dir, "idle")
    res = subprocess.run(
        [sys.executable, "-m", "scripts.matte", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    out = run_dir / "matte" / "idle.png"
    assert out.exists()
    with Image.open(out) as im:
        assert im.mode == "RGBA"
