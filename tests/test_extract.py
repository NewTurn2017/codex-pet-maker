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


def _make_strip(target: Path, frame_count: int, width=900, height=180) -> None:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = img.load()
    spacing = width / frame_count
    for i in range(frame_count):
        cx = int(spacing * (i + 0.5))
        for y in range(40, height - 40):
            for x in range(cx - 30, cx + 30):
                pixels[x, y] = (255, 100, 50, 255)
    img.save(target)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scripts.extract", *args],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )


def test_extract_writes_six_idle_frames(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _make_strip(run_dir / "matte" / "idle.png", 6)
    res = _run(["--run-dir", str(run_dir), "--row", "idle"])
    assert res.returncode == 0, res.stderr
    frames = sorted((run_dir / "frames" / "idle").glob("*.png"))
    assert len(frames) == 6
    with Image.open(frames[0]) as im:
        assert im.size == (192, 208)
        assert im.mode == "RGBA"


def test_extract_count_mismatch_returns_5(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _make_strip(run_dir / "matte" / "idle.png", 5)
    res = _run(["--run-dir", str(run_dir), "--row", "idle"])
    assert res.returncode == 5
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["rows"]["idle"]["status"] == "needs_retry"


def test_extract_second_mismatch_marks_failed(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _make_strip(run_dir / "matte" / "idle.png", 5)
    _run(["--run-dir", str(run_dir), "--row", "idle"])  # first → needs_retry
    _make_strip(run_dir / "matte" / "idle.png", 5)
    res = _run(["--run-dir", str(run_dir), "--row", "idle"])  # second → failed
    assert res.returncode == 5
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["rows"]["idle"]["status"] == "failed"


def test_extract_all_rows_when_no_row_arg(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _make_strip(run_dir / "matte" / "idle.png", 6)
    _make_strip(run_dir / "matte" / "waving.png", 4)
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 0, res.stderr
    assert len(list((run_dir / "frames" / "idle").glob("*.png"))) == 6
    assert len(list((run_dir / "frames" / "waving").glob("*.png"))) == 4
