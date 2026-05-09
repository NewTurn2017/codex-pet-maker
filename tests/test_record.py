from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image


def _make_png(path: Path, color=(255, 255, 255), size=(64, 32)) -> None:
    Image.new("RGB", size, color).save(path)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scripts.record", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def _bootstrap_run_dir(tmp_path: Path) -> Path:
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "x", "references": []}))
    out = tmp_path / "runs"
    res = subprocess.run(
        [sys.executable, "-m", "scripts.prepare", "--request", str(req), "--output-dir", str(out)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    return Path(json.loads(res.stdout)["run_dir"])


def test_record_moves_png_to_decoded(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    src = tmp_path / "raw.png"
    _make_png(src)
    res = _run(["--run-dir", str(run_dir), "--row", "idle", "--source", str(src)])
    assert res.returncode == 0, res.stderr
    target = run_dir / "decoded" / "idle.png"
    assert target.exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["rows"]["idle"]["status"] == "decoded"


def test_record_base(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    src = tmp_path / "raw.png"
    _make_png(src)
    res = _run(["--run-dir", str(run_dir), "--row", "base", "--source", str(src)])
    assert res.returncode == 0, res.stderr
    assert (run_dir / "decoded" / "base.png").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["base"]["status"] == "decoded"


def test_record_unknown_row_errors(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    src = tmp_path / "raw.png"
    _make_png(src)
    res = _run(["--run-dir", str(run_dir), "--row", "bogus", "--source", str(src)])
    assert res.returncode == 2


def test_record_refuses_overwrite_without_force(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    src = tmp_path / "raw.png"
    _make_png(src)
    _run(["--run-dir", str(run_dir), "--row", "idle", "--source", str(src)])
    src2 = tmp_path / "raw2.png"
    _make_png(src2, color=(0, 0, 0))
    res = _run(["--run-dir", str(run_dir), "--row", "idle", "--source", str(src2)])
    assert res.returncode == 2

    res_force = _run(["--run-dir", str(run_dir), "--row", "idle", "--source", str(src2), "--force"])
    assert res_force.returncode == 0
