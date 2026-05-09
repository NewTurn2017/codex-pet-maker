from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scripts.prepare", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_prepare_creates_run_dir(tmp_path: Path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "Small orange fox.", "references": []}))
    out = tmp_path / "runs"
    res = _run(["--request", str(req), "--output-dir", str(out)])
    assert res.returncode == 0, res.stderr
    status = json.loads(res.stdout)
    run_dir = Path(status["run_dir"])
    assert run_dir.parent == out
    assert (run_dir / "pet_request.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "prompts" / "base.md").exists()
    assert (run_dir / "prompts" / "rows" / "idle.md").exists()
    assert (run_dir / "decoded").is_dir()
    assert (run_dir / "matte").is_dir()
    assert (run_dir / "frames").is_dir()
    assert (run_dir / "final").is_dir()
    assert (run_dir / "qa").is_dir()


def test_prepare_substitutes_variables(tmp_path: Path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "Small orange fox.", "references": []}))
    out = tmp_path / "runs"
    res = _run(["--request", str(req), "--output-dir", str(out)])
    status = json.loads(res.stdout)
    base_prompt = (Path(status["run_dir"]) / "prompts" / "base.md").read_text()
    assert "Foxy" in base_prompt
    assert "Small orange fox." in base_prompt
    assert "{{pet_name}}" not in base_prompt
    assert "{{style_block}}" not in base_prompt
    assert "Codex Digital Pet Style" in base_prompt


def test_prepare_manifest_lists_all_rows(tmp_path: Path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "Small orange fox.", "references": []}))
    out = tmp_path / "runs"
    res = _run(["--request", str(req), "--output-dir", str(out)])
    status = json.loads(res.stdout)
    manifest = json.loads((Path(status["run_dir"]) / "manifest.json").read_text())
    assert manifest["slug"] == "foxy"
    assert manifest["display_name"] == "Foxy"
    assert set(manifest["rows"].keys()) == {
        "idle", "running-right", "running-left", "waving", "jumping",
        "failed", "waiting", "running", "review",
    }
    for entry in manifest["rows"].values():
        assert entry["status"] == "pending"


def test_prepare_resume_returns_existing_run(tmp_path: Path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "Small orange fox.", "references": []}))
    out = tmp_path / "runs"
    first = json.loads(_run(["--request", str(req), "--output-dir", str(out)]).stdout)
    second = json.loads(
        _run(["--request", str(req), "--output-dir", str(out), "--resume", first["run_id"]]).stdout
    )
    assert first["run_id"] == second["run_id"]


def test_prepare_rejects_missing_name(tmp_path: Path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"description": "x"}))
    res = _run(["--request", str(req), "--output-dir", str(tmp_path / "runs")])
    assert res.returncode == 2
    assert "name" in res.stderr.lower()
