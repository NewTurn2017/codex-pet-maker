from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import petio


def test_slugify_basic():
    assert petio.slugify("Foxy") == "foxy"
    assert petio.slugify("  Foxy  ") == "foxy"
    assert petio.slugify("Mr. Whiskers") == "mr-whiskers"
    assert petio.slugify("café 99!") == "caf-99"
    assert petio.slugify("---a---b---") == "a-b"


def test_slugify_rejects_empty():
    with pytest.raises(ValueError):
        petio.slugify("   ")
    with pytest.raises(ValueError):
        petio.slugify("!!!")


def test_run_id_is_unique_and_sortable():
    a = petio.new_run_id("foxy")
    b = petio.new_run_id("foxy")
    assert a != b
    assert a < b or a > b  # lex-comparable
    assert a.startswith("20") and "foxy" in a


def test_manifest_round_trip(tmp_path: Path):
    target = tmp_path / "manifest.json"
    data = {"run_id": "x", "rows": {"idle": {"status": "pending"}}}
    petio.write_manifest(target, data)
    assert json.loads(target.read_text()) == data
    assert petio.read_manifest(target) == data


def test_manifest_update_merges_rows(tmp_path: Path):
    target = tmp_path / "manifest.json"
    petio.write_manifest(target, {"run_id": "x", "rows": {"idle": {"status": "pending"}}})
    petio.update_row(target, "idle", {"status": "matted"})
    petio.update_row(target, "running-right", {"status": "pending"})
    final = petio.read_manifest(target)
    assert final["rows"]["idle"] == {"status": "matted"}
    assert final["rows"]["running-right"] == {"status": "pending"}


def test_codex_pets_dir_respects_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert petio.codex_pets_dir() == tmp_path / "pets"
    monkeypatch.delenv("CODEX_HOME")
    assert petio.codex_pets_dir() == Path.home() / ".codex" / "pets"
