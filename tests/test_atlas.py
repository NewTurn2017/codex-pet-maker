from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def _seed_frames(run_dir: Path, row: str, count: int, color=(120, 200, 255, 255)):
    out_dir = run_dir / "frames" / row
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        Image.new("RGBA", (192, 208), color).save(out_dir / f"{i:02d}.png")


def test_atlas_dimensions_and_mode(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    for row, count in [
        ("idle", 6), ("running-right", 8), ("running-left", 8),
        ("waving", 4), ("jumping", 5), ("failed", 8),
        ("waiting", 6), ("running", 6), ("review", 6),
    ]:
        _seed_frames(run_dir, row, count)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.atlas", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    sheet = run_dir / "final" / "spritesheet.png"
    assert sheet.exists()
    with Image.open(sheet) as im:
        assert im.size == (1536, 1872)
        assert im.mode == "RGBA"


def test_atlas_unused_cells_transparent(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _seed_frames(run_dir, "waving", 4)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.atlas", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    with Image.open(run_dir / "final" / "spritesheet.png") as im:
        rgba = im.convert("RGBA")
        for col in range(4, 8):
            x = col * 192 + 96
            y = 3 * 208 + 104
            assert rgba.getpixel((x, y))[3] == 0


def test_atlas_missing_row_leaves_transparent(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _seed_frames(run_dir, "idle", 6)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.atlas", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    with Image.open(run_dir / "final" / "spritesheet.png") as im:
        rgba = im.convert("RGBA")
        for col in range(8):
            x = col * 192 + 96
            y = 1 * 208 + 104
            assert rgba.getpixel((x, y))[3] == 0
