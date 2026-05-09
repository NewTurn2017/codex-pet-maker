from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _copy_repo_without_local_artifacts(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            ".omx",
            "pet-runs",
            "__pycache__",
            "*.egg-info",
            "*.pyc",
        ),
    )


def _assert_installed_bundle(target: Path) -> None:
    assert (target / "SKILL.md").exists()
    assert (target / "README.md").exists()
    assert (target / "pyproject.toml").exists()
    assert (target / "install.sh").exists()
    assert (target / "install.ps1").exists()
    assert (target / "scripts" / "prepare.py").exists()
    assert (target / "prompts" / "base.md").exists()
    assert (target / "references" / "codex-pet-contract.md").exists()
    assert (target / "docs" / "assets" / "examples" / "cap-coder-spritesheet.png").exists()


def _make_tar_archive(source: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source, arcname="codex-pet-maker-main")


def _make_zip_archive(source: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in source.rglob("*"):
            if path.is_file():
                zf.write(path, Path("codex-pet-maker-main") / path.relative_to(source))


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell installer is covered by Linux/macOS CI")
def test_install_script_copies_self_contained_skill_bundle(tmp_path: Path):
    codex_home = tmp_path / "codex-home"
    env = {
        **os.environ,
        "CODEX_HOME": str(codex_home),
        "CODEX_PET_MAKER_SKIP_VENV": "1",
    }

    res = subprocess.run(
        ["./install.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert res.returncode == 0, res.stderr
    target = codex_home / "skills" / "codex-pet-maker"
    _assert_installed_bundle(target)

    assert not (target / ".git").exists()
    assert not (target / ".venv").exists()
    assert not (target / "pet-runs").exists()
    assert not (target / "pet_request.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell installer is covered by Linux/macOS CI")
def test_install_script_works_from_a_copied_repository(tmp_path: Path):
    copied = tmp_path / "copied-codex-pet-maker"
    _copy_repo_without_local_artifacts(ROOT, copied)
    codex_home = tmp_path / "codex-home"
    env = {
        **os.environ,
        "CODEX_HOME": str(codex_home),
        "CODEX_PET_MAKER_SKIP_VENV": "1",
    }

    res = subprocess.run(["./install.sh"], cwd=copied, env=env, capture_output=True, text=True)

    assert res.returncode == 0, res.stderr
    target = codex_home / "skills" / "codex-pet-maker"
    _assert_installed_bundle(target)
    assert "codex-pet-maker installed" in res.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell installer is covered by Linux/macOS CI")
def test_install_script_can_run_from_installed_target_without_recursing(tmp_path: Path):
    target = tmp_path / "codex-home" / "skills" / "codex-pet-maker"
    env = {
        **os.environ,
        "CODEX_PET_MAKER_TARGET": str(target),
        "CODEX_PET_MAKER_SKIP_VENV": "1",
    }

    first = subprocess.run(["./install.sh"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr

    second = subprocess.run(["./install.sh"], cwd=target, env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert (target / "install.sh").exists()
    assert (target / "SKILL.md").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell installer is covered by Linux/macOS CI")
def test_curl_pipe_mode_installs_from_archive_without_local_checkout(tmp_path: Path):
    copied = tmp_path / "archive-source"
    _copy_repo_without_local_artifacts(ROOT, copied)
    archive = tmp_path / "codex-pet-maker.tar.gz"
    _make_tar_archive(copied, archive)

    codex_home = tmp_path / "codex-home"
    env = {
        **os.environ,
        "CODEX_HOME": str(codex_home),
        "CODEX_PET_MAKER_SKIP_VENV": "1",
        "CODEX_PET_MAKER_ARCHIVE_PATH": str(archive),
    }

    with (ROOT / "install.sh").open("rb") as stdin:
        res = subprocess.run(["sh"], cwd=tmp_path, env=env, stdin=stdin, capture_output=True, text=True)

    assert res.returncode == 0, res.stderr
    target = codex_home / "skills" / "codex-pet-maker"
    _assert_installed_bundle(target)
    assert "codex-pet-maker installed" in res.stdout


def test_powershell_remote_installer_from_archive_when_pwsh_available(tmp_path: Path):
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        pytest.skip("PowerShell is not installed")

    copied = tmp_path / "archive-source"
    _copy_repo_without_local_artifacts(ROOT, copied)
    archive = tmp_path / "codex-pet-maker.zip"
    _make_zip_archive(copied, archive)

    codex_home = tmp_path / "codex-home"
    command = f"$env:CODEX_HOME='{codex_home}'; $env:CODEX_PET_MAKER_SKIP_VENV='1'; $env:CODEX_PET_MAKER_ARCHIVE_PATH='{archive}'; Get-Content -Raw '{ROOT / 'install.ps1'}' | Invoke-Expression"
    res = subprocess.run([pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], capture_output=True, text=True)

    assert res.returncode == 0, res.stderr
    _assert_installed_bundle(codex_home / "skills" / "codex-pet-maker")
