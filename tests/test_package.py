from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


def _bootstrap_run_dir(tmp_path: Path) -> Path:
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "Small orange fox.", "references": []}))
    out = tmp_path / "runs"
    res = subprocess.run(
        [sys.executable, "-m", "scripts.prepare", "--request", str(req), "--output-dir", str(out)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    return Path(json.loads(res.stdout)["run_dir"])


def _seed_validated_atlas(run_dir: Path):
    sheet = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    sheet.save(run_dir / "final" / "spritesheet.png")
    qa = run_dir / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "review.json").write_text(json.dumps({"hard_checks": {"dimensions": "pass"}}))


def _run(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scripts.package", *args],
        capture_output=True, text=True, env=env,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_package_writes_webp_and_petjson(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _seed_validated_atlas(run_dir)
    codex_home = tmp_path / "codex_home"
    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    res = _run(["--run-dir", str(run_dir)], env)
    assert res.returncode == 0, res.stderr
    pet_dir = codex_home / "pets" / "foxy"
    assert (pet_dir / "spritesheet.webp").exists()
    pet_meta = json.loads((pet_dir / "pet.json").read_text())
    assert set(pet_meta.keys()) == {"id", "displayName", "description", "spritesheetPath"}
    assert pet_meta["id"] == "foxy"
    assert pet_meta["displayName"] == "Foxy"
    assert pet_meta["spritesheetPath"] == "spritesheet.webp"


def test_package_refuses_existing_pet_without_force(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _seed_validated_atlas(run_dir)
    codex_home = tmp_path / "codex_home"
    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    _run(["--run-dir", str(run_dir)], env)
    res = _run(["--run-dir", str(run_dir)], env)
    assert res.returncode == 7
    res_force = _run(["--run-dir", str(run_dir), "--force"], env)
    assert res_force.returncode == 0


def test_package_rejects_failed_qa(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    sheet = Image.new("RGBA", (1024, 1024))
    sheet.save(run_dir / "final" / "spritesheet.png")
    qa = run_dir / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "review.json").write_text(json.dumps({"hard_checks": {"dimensions": "fail"}}))
    env = {**os.environ, "CODEX_HOME": str(tmp_path / "codex_home")}
    res = _run(["--run-dir", str(run_dir)], env)
    assert res.returncode == 2
    assert "qa" in res.stderr.lower()
