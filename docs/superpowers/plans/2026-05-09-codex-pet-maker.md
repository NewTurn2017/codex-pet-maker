# codex-pet-maker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a leaner Codex skill (`codex-pet-maker`) that produces Codex-app-compatible animated pet packages — fixing the green-halo background-removal failure of the original `hatch-pet` and removing operational ceremony.

**Architecture:** Codex agent reads `SKILL.md`, runs deterministic Python scripts via subprocess for prepare/matte/extract/atlas/qa/package steps, and invokes the built-in `image_gen` tool for visual generation (10 calls per pet: 1 base + 9 row strips). Run state lives under `./pet-runs/<run-id>/`; final package lands at `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/`. Manifest is informational; on-disk file existence is authoritative (sangpye-style). `rembg` + alpha matting replaces chroma-key.

**Tech Stack:** Python 3.11+, Pillow, rembg (U2Net via onnxruntime), pytest. No ffmpeg, no OpenAI REST direct calls, no `codex responses-api-proxy`.

**Spec reference:** `docs/superpowers/specs/2026-05-09-codex-pet-maker-design.md` — load this in any subagent that picks up a task; it contains the immutable Codex Pet contract (Section 2), the row table, prompt template (Section 4.3), the rembg call (Section 5.1), and the QA rubric (Section 7).

---

## File Structure

| Path | Responsibility | LOC budget |
|---|---|---|
| `SKILL.md` | Codex-facing workflow doc | ≤250 |
| `README.md` | Human install + example | ~80 |
| `pyproject.toml` | Deps (rembg, onnxruntime, Pillow, pytest) | ~30 |
| `scripts/__init__.py` | Empty package marker | 0 |
| `scripts/petio.py` | Shared paths, slugify, manifest read/write, run-id helpers | ~120 |
| `scripts/prepare.py` | CLI: take pet request JSON → init run dir, prompts, manifest, status | ~150 |
| `scripts/record.py` | CLI: ingest a freshly written `image_gen` PNG into `decoded/<row>.png` | ~80 |
| `scripts/matte.py` | CLI: rembg + alpha matting over `decoded/*.png` → `matte/*.png` | ~120 |
| `scripts/extract.py` | CLI: connected components per row, retry-once-then-fail, write `frames/<row>/NN.png` | ~150 |
| `scripts/atlas.py` | CLI: stitch `frames/*` into 1536×1872 RGBA `final/spritesheet.png` | ~100 |
| `scripts/qa.py` | CLI: hard+soft validation; write `final/validation.json`, `qa/review.json`, `qa/contact-sheet.png` | ~150 |
| `scripts/package.py` | CLI: encode WebP + write `pet.json` to `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/` | ~80 |
| `prompts/style.md` | Codex Digital Pet Style block (verbatim from hatch-pet) | ~40 |
| `prompts/base.md` | base.png prompt template | ~30 |
| `prompts/rows/idle.md` ... `review.md` | One per row; per-frame pose lists | ~30 each × 9 |
| `references/codex-pet-contract.md` | Atlas contract (Section 2 of spec) | ~80 |
| `references/animation-rows.md` | Row table | ~40 |
| `references/qa-rubric.md` | Acceptance criteria | ~40 |
| `tests/test_petio.py` | slug, run-id, manifest round-trip | — |
| `tests/test_prepare.py` | run dir layout, status output | — |
| `tests/test_record.py` | ingest semantics | — |
| `tests/test_matte.py` | rembg call wired (smoke; skipped if model not present) | — |
| `tests/test_extract.py` | synthetic strip → component count → retry signaling | — |
| `tests/test_atlas.py` | dims, RGBA, transparent unused cells | — |
| `tests/test_qa.py` | hard checks (good+bad fixtures) | — |
| `tests/test_package.py` | webp round-trip, pet.json key set | — |

Total: ~1000 Python LOC + ~250 SKILL.md + ~500 prompts/refs. One third the size of original `hatch-pet`.

---

## Conventions

- Every script is invokable as `python -m scripts.<name> --run-dir ./pet-runs/<id> [extra]` and `python scripts/<name>.py ...`. Use `argparse`.
- Exit codes: `0` ok, `2` user/usage error, `5` row failed after retry, `6` QA hard-check failed, `7` package collision without `--force`.
- Tests use pytest, live in `tests/`, hit only the local filesystem under `tmp_path`. The rembg test is marked `@pytest.mark.slow` and is skipped if `REMBG_SMOKE != 1`.
- Commit after each task. Commit messages: `feat(<scope>): ...`, `test(<scope>): ...`, `docs: ...`.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `scripts/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/genie/dev/tools/skills/codex-pet-maker
git init
git add docs/
git commit -m "docs: import design spec"
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "codex-pet-maker"
version = "0.1.0"
description = "Lean Codex skill for generating Codex-app-compatible animated pet packages."
requires-python = ">=3.11"
dependencies = [
    "Pillow>=10.0",
    "rembg>=2.0.50",
    "onnxruntime>=1.17",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: tests that download models or do heavy work",
]
```

- [ ] **Step 3: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
pet-runs/
.u2net/
*.egg-info/
```

- [ ] **Step 4: Create empty package markers**

`scripts/__init__.py`:
```python
"""codex-pet-maker scripts package."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 5: Write `tests/conftest.py`**

```python
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
```

- [ ] **Step 6: Verify pytest discovers no tests yet (sanity)**

Run: `python -m pytest -q`
Expected: `no tests ran` or `0 passed`. If `pytest` not installed: `pip install pytest`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore scripts/ tests/
git commit -m "chore: scaffold project (pyproject, gitignore, test conftest)"
```

---

## Task 2: References docs (contract, rows, rubric)

**Files:**
- Create: `references/codex-pet-contract.md`
- Create: `references/animation-rows.md`
- Create: `references/qa-rubric.md`

These are read by the codex agent (and humans) to constrain implementation. Content is lifted from spec Section 2 and Section 7.3.

- [ ] **Step 1: Write `references/codex-pet-contract.md`**

```markdown
# Codex Pet Contract (immutable)

These values are dictated by the Codex desktop app. Do not change them.

## Atlas

| Property | Value |
|---|---|
| Format | PNG (working) → WebP (final) |
| Dimensions | exactly **1536 × 1872** pixels |
| Color | RGBA, transparent-capable |
| Grid | **8 columns × 9 rows** |
| Cell | exactly **192 × 208** pixels |
| Background | fully transparent |
| Unused cells | fully transparent (alpha == 0) |
| Forbidden | labels, gutters, borders, drawn grid lines, shadows outside cells, extra frames |

## WebP encoding

```python
image.convert("RGBA").save(target, format="WEBP", lossless=True, quality=100, method=6)
```

## `pet.json` (exact key set, no extras)

```json
{
  "id": "pet-name",
  "displayName": "Pet Name",
  "description": "One short sentence.",
  "spritesheetPath": "spritesheet.webp"
}
```

## ID slug

```python
def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")
```

## Output package location

```
${CODEX_HOME:-$HOME/.codex}/pets/<pet-id>/
├── pet.json
└── spritesheet.webp
```
```

- [ ] **Step 2: Write `references/animation-rows.md`**

```markdown
# Animation rows

The Codex app reads cells by fixed (row, column) index and animates per these durations.
Used cells in each row must be non-empty. Cells in unused columns of each row must be fully transparent.

| Row | State | Used cols | Frame count | Per-frame duration (ms) |
|:--:|---|:--:|:--:|---|
| 0 | idle | 0–5 | 6 | 280, 110, 110, 140, 140, 320 |
| 1 | running-right | 0–7 | 8 | 120 each, final 220 |
| 2 | running-left | 0–7 | 8 | 120 each, final 220 |
| 3 | waving | 0–3 | 4 | 140 each, final 280 |
| 4 | jumping | 0–4 | 5 | 140 each, final 280 |
| 5 | failed | 0–7 | 8 | 140 each, final 240 |
| 6 | waiting | 0–5 | 6 | 150 each, final 260 |
| 7 | running | 0–5 | 6 | 120 each, final 220 |
| 8 | review | 0–5 | 6 | 150 each, final 280 |

Notes:
- `running-right` and `running-left` are full locomotion cycles (foot-running).
- `running` (row 7) is a "busy task" loop — bustling at a workbench/keyboard, NOT foot-running.
- `idle`, `waiting`, `review` must be visually distinguishable from each other (different focal action; not all "looking around").
```

- [ ] **Step 3: Write `references/qa-rubric.md`**

```markdown
# QA rubric

Hard checks (`scripts/qa.py` exits 6 on failure; package not written):

- `final/spritesheet.png` size == (1536, 1872)
- mode == RGBA
- For each row, used-column cells have non-zero alpha somewhere
- For each row, unused-column cells have alpha == 0 everywhere
- After WebP encode + decode, dimensions still (1536, 1872)
- `pet.json` has exactly `{id, displayName, description, spritesheetPath}` keys, no others
- `id == slugify(displayName)`

Soft checks (warnings in `qa/review.json`; package still written):

- frame_count detected per row matches expected count (already enforced by extract.py)
- per-frame pixel-area outliers within a row (likely identity drift)
- chroma-key-adjacent residual pixels (rembg should leave none)

Visual review (human or codex agent on `qa/contact-sheet.png`):

- No green halo or background bleed
- Identity consistent across all rows
- Per-row action distinguishable from idle
- Directional rows actually directional
- Idle / waiting / review distinguishable from each other
- No motion lines, dust, shadows outside character, text
```

- [ ] **Step 4: Commit**

```bash
git add references/
git commit -m "docs: add codex-pet-contract, animation-rows, qa-rubric references"
```

---

## Task 3: petio shared module — slugify, run-id, manifest

**Files:**
- Create: `scripts/petio.py`
- Test: `tests/test_petio.py`

This holds the only logic shared across CLI scripts. Keep narrow.

- [ ] **Step 1: Write the failing test**

`tests/test_petio.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_petio.py -v`
Expected: ImportError or `AttributeError: module 'scripts.petio' has no attribute 'slugify'`.

- [ ] **Step 3: Implement `scripts/petio.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_petio.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/petio.py tests/test_petio.py
git commit -m "feat(petio): slugify, run-id, manifest helpers, row constants"
```

---

## Task 4: Style + base prompt

**Files:**
- Create: `prompts/style.md`
- Create: `prompts/base.md`

These are templates. Variables use `{{var}}` (Mustache-style) and are substituted by `prepare.py` in Task 5.

- [ ] **Step 1: Write `prompts/style.md`**

```markdown
## Codex Digital Pet Style (mandatory)

Render the character as a small chibi-style digital pet:
- Soft, rounded silhouette; oversized head relative to body (~1.2:1).
- Crisp 1–2 px outline in a colour darker than the body, never pure black.
- Limited palette: 1 primary body colour, 1 accent, 1 outline. No gradients, no rim light.
- Flat shading with a single, soft cell-shaded shadow shape per limb. No painterly textures.
- Eyes are simple shapes (round or curved) with one specular dot. No realistic eyes.
- No drop shadow under the character. No motion blur. No depth-of-field.
- Pixel-aware: keep small features (paw tips, ear tufts, accessories) at least 4 px across.
- Background pure white #FFFFFF everywhere outside the character.
```

- [ ] **Step 2: Write `prompts/base.md`**

```markdown
{{style_block}}

Subject: {{pet_name}} — {{pet_description}}

Goal: produce ONE canonical front-facing portrait of {{pet_name}} that locks identity for the rest of this run.

Pose: standing, front-facing, neutral expression, arms/paws relaxed at sides, full body visible.
Composition: single character centered, ample padding on all sides, background pure white #FFFFFF.

Forbidden: text, labels, watermarks, multiple characters, alternate poses, frames, grid lines, borders, scenery, motion lines, drop shadow.

Output: a single PNG sized 1024×1024 with the character roughly 70% of frame height.
```

- [ ] **Step 3: Commit**

```bash
git add prompts/style.md prompts/base.md
git commit -m "feat(prompts): style block + base portrait prompt"
```

---

## Task 5: Per-row prompts (9 files)

**Files:**
- Create: `prompts/rows/idle.md`
- Create: `prompts/rows/running-right.md`
- Create: `prompts/rows/running-left.md`
- Create: `prompts/rows/waving.md`
- Create: `prompts/rows/jumping.md`
- Create: `prompts/rows/failed.md`
- Create: `prompts/rows/waiting.md`
- Create: `prompts/rows/running.md`
- Create: `prompts/rows/review.md`

Every prompt follows the template from spec Section 4.3 and includes per-frame poses (Section 8.3 finding: required for real frame variation).

Convention for the "Action" line: one short sentence describing what the row depicts.
Convention for "Forbidden in this row": items unique to this row's failure modes (e.g., `idle` forbids large body movement; `jumping` forbids drop shadow).

- [ ] **Step 1: Write `prompts/rows/idle.md`** (6 frames)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: idle
Frame count: produce EXACTLY 6 distinct frames in a horizontal strip.

Per-frame poses:
  Frame 1: long blink — eyes fully closed, mouth relaxed neutral
  Frame 2: eyes opening halfway, head tilted +5° to its right
  Frame 3: eyes fully open, head still tilted +5° to its right, slight chest rise (breath in)
  Frame 4: eyes fully open, head returning to center, chest at peak (breath held)
  Frame 5: eyes fully open, head tilted -3° to its left, chest lowering (breath out)
  Frame 6: eyes fully open, head centered, chest at rest, mouth slight smile

Layout: horizontal strip, all 6 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a calm idle breathing loop with a long blink at the start.

Forbidden in this row: walking, running, jumping, waving, large body movement, hand gestures, holding objects, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 6 frames, more than 6 frames.
```

- [ ] **Step 2: Write `prompts/rows/running-right.md`** (8 frames)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: running-right
Frame count: produce EXACTLY 8 distinct frames in a horizontal strip.

Per-frame poses (a full locomotion cycle, character facing screen-right and travelling rightward):
  Frame 1: contact — right paw planted forward, left paw lifting back, body upright
  Frame 2: down — right paw planted, body slightly lowered, left paw mid-air swinging forward
  Frame 3: passing — both paws crossing under body, body at lowest point
  Frame 4: up — left paw planted forward, right paw pushing off, body rising
  Frame 5: contact — left paw planted forward, right paw lifting back, body upright (mirror of frame 1)
  Frame 6: down — left paw planted, body lowered, right paw mid-air swinging forward
  Frame 7: passing — both paws crossing under body, body at lowest point
  Frame 8: up — right paw planted forward, left paw pushing off, body rising

Layout: horizontal strip, all 8 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a full foot-running cycle, character facing screen-right.

Forbidden in this row: facing left, facing camera, walking-in-place with no body bob, motion lines, dust puffs, speed lines, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 8 frames, more than 8 frames.
```

- [ ] **Step 3: Write `prompts/rows/running-left.md`** (8 frames)

Same as `running-right.md` but mirrored: replace "facing screen-right" with "facing screen-left", "right paw planted forward" with "left paw planted forward" throughout, and add "facing right" to the Forbidden list.

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: running-left
Frame count: produce EXACTLY 8 distinct frames in a horizontal strip.

Per-frame poses (a full locomotion cycle, character facing screen-left and travelling leftward):
  Frame 1: contact — left paw planted forward, right paw lifting back, body upright
  Frame 2: down — left paw planted, body slightly lowered, right paw mid-air swinging forward
  Frame 3: passing — both paws crossing under body, body at lowest point
  Frame 4: up — right paw planted forward, left paw pushing off, body rising
  Frame 5: contact — right paw planted forward, left paw lifting back, body upright (mirror of frame 1)
  Frame 6: down — right paw planted, body lowered, left paw mid-air swinging forward
  Frame 7: passing — both paws crossing under body, body at lowest point
  Frame 8: up — left paw planted forward, right paw pushing off, body rising

Layout: horizontal strip, all 8 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a full foot-running cycle, character facing screen-left.

Forbidden in this row: facing right, facing camera, walking-in-place with no body bob, motion lines, dust puffs, speed lines, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 8 frames, more than 8 frames.
```

- [ ] **Step 4: Write `prompts/rows/waving.md`** (4 frames)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: waving
Frame count: produce EXACTLY 4 distinct frames in a horizontal strip.

Per-frame poses (right arm/paw raised; legs and torso static):
  Frame 1: right paw at shoulder height, palm facing camera, mouth small smile
  Frame 2: right paw raised above the head, fully extended, palm facing camera, mouth open smile
  Frame 3: right paw rotated to its right (the paw's right), elbow slightly bent, mouth open smile
  Frame 4: right paw rotated to its left (the paw's left), elbow slightly bent, mouth open smile

Layout: horizontal strip, all 4 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a friendly hand-wave with the right paw above the head.

Forbidden in this row: jumping, walking, lower-body motion, both arms raised, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 4 frames, more than 4 frames.
```

- [ ] **Step 5: Write `prompts/rows/jumping.md`** (5 frames)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: jumping
Frame count: produce EXACTLY 5 distinct frames in a horizontal strip.

Per-frame poses:
  Frame 1: anticipation — knees bent, body crouched low, arms back, eyes wide
  Frame 2: takeoff — legs fully extended pushing off, arms swinging up, body launching
  Frame 3: peak — fully airborne, body at apex, knees tucked slightly, arms above head
  Frame 4: descent — body falling, knees beginning to bend, arms forward for balance
  Frame 5: landing — feet planted, knees deeply bent, body absorbing impact, arms forward

Layout: horizontal strip, all 5 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a single vertical jump from anticipation to landing.

Forbidden in this row: drop shadow under feet, motion lines, dust puffs at takeoff or landing, multiple jumps, walking, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 5 frames, more than 5 frames.
```

- [ ] **Step 6: Write `prompts/rows/failed.md`** (8 frames)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: failed
Frame count: produce EXACTLY 8 distinct frames in a horizontal strip.

Per-frame poses (a "something went wrong" reaction loop):
  Frame 1: standing neutral, eyes open, mouth flat
  Frame 2: shoulders drop, head tilts forward, eyes squinting
  Frame 3: head shakes once to the right, mouth turning down
  Frame 4: head shakes once to the left, mouth fully frowning
  Frame 5: hands raised palms-up in a "what now" shrug, head still tilted forward
  Frame 6: hands lowered, head bowed lowest, eyes closed
  Frame 7: head beginning to lift, eyes still closed, small sigh
  Frame 8: head lifted to neutral, eyes opening, resigned half-smile

Layout: horizontal strip, all 8 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a small, comical disappointment loop after something went wrong.

Forbidden in this row: tears or sweat drops, anger, broken equipment, walking, jumping, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 8 frames, more than 8 frames.
```

- [ ] **Step 7: Write `prompts/rows/waiting.md`** (6 frames)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: waiting
Frame count: produce EXACTLY 6 distinct frames in a horizontal strip.

Per-frame poses (impatient waiting; one paw taps an invisible surface in front):
  Frame 1: standing, right paw extended forward at waist height, palm down, head looking at paw
  Frame 2: right paw lifted ~30° above the surface, head still looking at paw
  Frame 3: right paw back down on surface, head turning to its right, eyes glancing right
  Frame 4: right paw lifted ~30° again, head still glancing right
  Frame 5: right paw back down, head turned to its left, eyes glancing left
  Frame 6: right paw lifted ~30°, head returning to center, eyes forward

Layout: horizontal strip, all 6 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: an impatient waiting loop — paw-taps and head-glances side to side.

Forbidden in this row: any whole-body movement, walking, jumping, holding objects, drumming with both paws, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 6 frames, more than 6 frames.
```

- [ ] **Step 8: Write `prompts/rows/running.md`** (6 frames; busy-task NOT foot-running)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: running
Frame count: produce EXACTLY 6 distinct frames in a horizontal strip.

Per-frame poses (a "busy task in progress" loop — the character is at work, NOT running on feet):
  Frame 1: standing, both paws raised in front at chest height, fingers fanned
  Frame 2: paws moving — left paw down at waist, right paw still up at chest, head tracking the busy paw
  Frame 3: paws crossed in front of chest, eyes focused down on the work
  Frame 4: right paw down at waist, left paw up at chest, head tracking the busy paw
  Frame 5: both paws apart at shoulder height, eyebrows up in concentration
  Frame 6: both paws together in front of chest, small approving nod, eyes half-closed in focus

Layout: horizontal strip, all 6 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a busy-hands working loop — the character is performing a task, hands moving, NOT running on feet.

Forbidden in this row: foot-running, walking, jumping, holding any specific object (no laptop, no tools), motion lines, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 6 frames, more than 6 frames.
```

- [ ] **Step 9: Write `prompts/rows/review.md`** (6 frames)

```markdown
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: review
Frame count: produce EXACTLY 6 distinct frames in a horizontal strip.

Per-frame poses (an inspect-and-judge loop — the character is reviewing something):
  Frame 1: right paw at chin, head tilted forward, eyes squinting in study
  Frame 2: head tilted +10° to its right, paw still at chin, one eyebrow raised
  Frame 3: head tilted -10° to its left, paw still at chin, both eyebrows up
  Frame 4: paw lowered slightly, head straight, eyes wide as if noticing
  Frame 5: paw at side, head straight, single decisive nod, mouth small smile
  Frame 6: paw raised in a small thumbs-up, head straight, mouth open smile

Layout: horizontal strip, all 6 frames in a single row, equal spacing, each frame the same size, safe padding around each, no frame touching another. Background pure white #FFFFFF everywhere.

Action: a thoughtful review loop ending in approval.

Forbidden in this row: holding documents or screens, walking, jumping, foot-running, plus everywhere: text, labels, frame numbers, borders, grid lines, shadows outside character, scenery, fewer than 6 frames, more than 6 frames.
```

- [ ] **Step 10: Commit**

```bash
git add prompts/rows/
git commit -m "feat(prompts): per-row prompts with explicit per-frame poses"
```

---

## Task 6: prepare.py — initialize run dir + status

**Files:**
- Create: `scripts/prepare.py`
- Test: `tests/test_prepare.py`

`prepare.py` reads a pet request JSON, creates the run directory, renders prompts (substituting `{{pet_name}}`, `{{pet_description}}`, `{{style_block}}`), copies references, writes `manifest.json`, and prints a JSON status to stdout.

- [ ] **Step 1: Write the failing test**

`tests/test_prepare.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_prepare.py -v`
Expected: failures (script doesn't exist).

- [ ] **Step 3: Implement `scripts/prepare.py`**

```python
"""Initialize a codex-pet-maker run directory from a pet request."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from scripts import petio

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _render(template: str, *, style: str, pet_name: str, pet_description: str) -> str:
    return (
        template.replace("{{style_block}}", style.strip())
        .replace("{{pet_name}}", pet_name)
        .replace("{{pet_description}}", pet_description)
    )


def _ensure_dirs(run_dir: Path) -> None:
    for sub in ("decoded", "matte", "frames", "final", "qa", "references", "prompts/rows"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)


def _copy_references(srcs: list[str], run_dir: Path) -> list[str]:
    copied: list[str] = []
    for src in srcs:
        src_path = Path(src).expanduser().resolve()
        if not src_path.exists():
            raise SystemExit(f"reference not found: {src}")
        dest = run_dir / "references" / src_path.name
        shutil.copy2(src_path, dest)
        copied.append(str(dest))
    return copied


def _render_prompts(run_dir: Path, pet_name: str, pet_description: str) -> None:
    style = (PROMPTS_DIR / "style.md").read_text()
    base_template = (PROMPTS_DIR / "base.md").read_text()
    (run_dir / "prompts" / "base.md").write_text(
        _render(base_template, style=style, pet_name=pet_name, pet_description=pet_description)
    )
    rows_dir = PROMPTS_DIR / "rows"
    out_rows = run_dir / "prompts" / "rows"
    for row in petio.ROW_NAMES:
        template = (rows_dir / f"{row}.md").read_text()
        (out_rows / f"{row}.md").write_text(
            _render(template, style=style, pet_name=pet_name, pet_description=pet_description)
        )


def _initial_manifest(run_id: str, slug: str, display_name: str, description: str, references: list[str]) -> dict:
    return {
        "run_id": run_id,
        "slug": slug,
        "display_name": display_name,
        "description": description,
        "references": references,
        "rows": {row: {"status": "pending", "frame_count": petio.ROW_FRAME_COUNTS[row]} for row in petio.ROW_NAMES},
        "base": {"status": "pending"},
    }


def _existing_run_dir(parent: Path, run_id: str) -> Path | None:
    candidate = parent / run_id
    return candidate if candidate.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a codex-pet-maker run directory")
    parser.add_argument("--request", required=True, help="path to pet request JSON")
    parser.add_argument("--output-dir", required=True, help="parent directory for runs (e.g. ./pet-runs)")
    parser.add_argument("--resume", default=None, help="existing run id under --output-dir")
    args = parser.parse_args(argv)

    request_path = Path(args.request)
    if not request_path.exists():
        print(f"request file not found: {request_path}", file=sys.stderr)
        return 2

    try:
        request = json.loads(request_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"invalid request JSON: {exc}", file=sys.stderr)
        return 2

    name = request.get("name")
    description = request.get("description", "")
    references = list(request.get("references", []))

    if not isinstance(name, str) or not name.strip():
        print("request.name must be a non-empty string", file=sys.stderr)
        return 2
    if not isinstance(description, str):
        print("request.description must be a string", file=sys.stderr)
        return 2

    try:
        slug = petio.slugify(name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.resume:
        run_dir = _existing_run_dir(output_dir, args.resume)
        if run_dir is None:
            print(f"resume target not found: {args.resume}", file=sys.stderr)
            return 2
        run_id = args.resume
    else:
        run_id = petio.new_run_id(slug)
        run_dir = output_dir / run_id
        run_dir.mkdir()

    _ensure_dirs(run_dir)
    shutil.copy2(request_path, run_dir / "pet_request.json")
    refs = _copy_references(references, run_dir)
    _render_prompts(run_dir, pet_name=name, pet_description=description)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        petio.write_manifest(
            manifest_path,
            _initial_manifest(run_id, slug, name, description, refs),
        )

    status = {
        "run_id": run_id,
        "run_dir": str(run_dir.resolve()),
        "slug": slug,
        "display_name": name,
        "rows": list(petio.ROW_NAMES),
        "frame_counts": petio.ROW_FRAME_COUNTS,
        "next_action": "image_gen base.png and per-row strips",
    }
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_prepare.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/prepare.py tests/test_prepare.py
git commit -m "feat(prepare): initialize run dir, render prompts, write manifest, emit status JSON"
```

---

## Task 7: record.py — ingest image_gen output

**Files:**
- Create: `scripts/record.py`
- Test: `tests/test_record.py`

`record.py` is what the codex agent calls after the `image_gen` tool writes its output PNG. It moves the file to `decoded/<row>.png` (or `decoded/base.png`) and updates manifest. Idempotent: if `decoded/<row>.png` already exists, it errors unless `--force`.

- [ ] **Step 1: Write the failing test**

`tests/test_record.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_record.py -v`

- [ ] **Step 3: Implement `scripts/record.py`**

```python
"""Ingest an image_gen output PNG into a codex-pet-maker run."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

from scripts import petio


def _validate_image(path: Path) -> None:
    with Image.open(path) as im:
        im.verify()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest an image_gen PNG into a run")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--row", required=True, help="row name or 'base'")
    parser.add_argument("--source", required=True, help="PNG written by image_gen")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not (run_dir / "manifest.json").exists():
        print(f"not a run dir: {run_dir}", file=sys.stderr)
        return 2

    if args.row != "base" and args.row not in petio.ROW_NAMES:
        print(f"unknown row: {args.row}", file=sys.stderr)
        return 2

    src = Path(args.source)
    if not src.exists():
        print(f"source not found: {src}", file=sys.stderr)
        return 2

    try:
        _validate_image(src)
    except Exception as exc:
        print(f"invalid PNG: {exc}", file=sys.stderr)
        return 2

    dest = run_dir / "decoded" / f"{args.row}.png"
    if dest.exists() and not args.force:
        print(f"already recorded: {dest} (pass --force to overwrite)", file=sys.stderr)
        return 2

    shutil.copy2(src, dest)

    manifest_path = run_dir / "manifest.json"
    data = petio.read_manifest(manifest_path)
    if args.row == "base":
        data["base"] = {"status": "decoded", "path": str(dest.relative_to(run_dir))}
    else:
        rows = data.setdefault("rows", {})
        rows[args.row] = {**rows.get(args.row, {}), "status": "decoded", "decoded_path": str(dest.relative_to(run_dir))}
    petio.write_manifest(manifest_path, data)

    print(str(dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_record.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/record.py tests/test_record.py
git commit -m "feat(record): ingest image_gen output and update manifest"
```

---

## Task 8: matte.py — rembg + alpha matting

**Files:**
- Create: `scripts/matte.py`
- Test: `tests/test_matte.py`

The fix for the user's main complaint. Wraps `rembg.remove(...)` per Section 5.1, processes every PNG in `decoded/<row>.png` (skipping `base.png` — base is identity reference, not for the atlas), writes to `matte/<row>.png`. Skips work that's already done (resume). The rembg session is reused across rows for performance.

- [ ] **Step 1: Write the failing test**

`tests/test_matte.py`:
```python
from __future__ import annotations

import json
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
    # paint a solid blob in each cell so rembg has something to find
    pixels = img.load()
    for cell in range(6):
        cx = cell * 192 + 96
        for y in range(40, 168):
            for x in range(cx - 40, cx + 40):
                pixels[x, y] = shape_color
    target = run_dir / "decoded" / f"{row}.png"
    img.save(target)
    return target


def test_matte_skips_when_no_decoded(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.matte", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr


@pytest.mark.slow
def test_matte_writes_rgba_outputs(tmp_path: Path, monkeypatch):
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


def _has_rembg_smoke() -> bool:
    import os
    return os.environ.get("REMBG_SMOKE") == "1"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_matte.py -v`
Expected: collection ok, first test fails with module-not-found.

- [ ] **Step 3: Implement `scripts/matte.py`**

```python
"""Background removal with rembg + alpha matting."""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

from scripts import petio


def _matte_one(session, src: Path, dst: Path) -> None:
    import rembg

    raw = src.read_bytes()
    out_bytes = rembg.remove(
        raw,
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=2,
    )
    with Image.open(io.BytesIO(out_bytes)) as im:
        im.convert("RGBA").save(dst, format="PNG")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove background from decoded row strips")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    decoded = run_dir / "decoded"
    matte_dir = run_dir / "matte"
    matte_dir.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, Path, Path]] = []
    for row in petio.ROW_NAMES:
        src = decoded / f"{row}.png"
        if not src.exists():
            continue
        dst = matte_dir / f"{row}.png"
        if dst.exists() and not args.force:
            continue
        targets.append((row, src, dst))

    if not targets:
        print("nothing to matte", file=sys.stderr)
        return 0

    try:
        from rembg import new_session
    except ImportError:
        print("rembg not installed; pip install rembg onnxruntime", file=sys.stderr)
        return 2

    session = new_session("u2net")
    manifest_path = run_dir / "manifest.json"
    for row, src, dst in targets:
        _matte_one(session, src, dst)
        petio.update_row(manifest_path, row, {"status": "matted", "matte_path": str(dst.relative_to(run_dir))})
        print(str(dst))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_matte.py -v`
Expected: 1 passed, 1 skipped (REMBG_SMOKE not set).

Optional manual smoke (downloads U2Net model):
```bash
REMBG_SMOKE=1 python -m pytest tests/test_matte.py -v -m slow
```

- [ ] **Step 5: Commit**

```bash
git add scripts/matte.py tests/test_matte.py
git commit -m "feat(matte): rembg + alpha matting; replaces chroma-key path"
```

---

## Task 9: extract.py — connected-component frame extraction

**Files:**
- Create: `scripts/extract.py`
- Test: `tests/test_extract.py`

For each row in `matte/<row>.png`: find connected components of non-transparent pixels, sort left-to-right, compare count to `frame_count`. On mismatch, mark row as "needs_retry" and exit 5 (the codex agent will rerun image_gen + record + matte for that row, then call extract again; on second mismatch, mark "failed" and exit 5 still — the row will be left fully transparent in the atlas).

Each frame is rescaled to fit inside a 192×208 cell (preserving aspect, centered, padded with transparent).

- [ ] **Step 1: Write the failing test**

`tests/test_extract.py`:
```python
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
    _make_strip(run_dir / "matte" / "idle.png", 5)  # spec wants 6
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_extract.py -v`

- [ ] **Step 3: Implement `scripts/extract.py`**

```python
"""Extract per-cell frames from matted row strips via connected-component analysis."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

from scripts import petio

ALPHA_THRESHOLD = 16
MIN_COMPONENT_AREA = 200  # pixels — filters orphan specks


def _components(alpha: Image.Image) -> list[tuple[int, int, int, int]]:
    """Return bounding boxes of non-transparent components, sorted left-to-right.

    Uses a flood-fill walker on a binary mask thresholded by ALPHA_THRESHOLD.
    """
    w, h = alpha.size
    px = alpha.load()
    visited = [[False] * w for _ in range(h)]
    boxes: list[tuple[int, int, int, int]] = []  # (x0, y0, x1, y1)

    for y in range(h):
        for x in range(w):
            if visited[y][x] or px[x, y] < ALPHA_THRESHOLD:
                continue
            stack = [(x, y)]
            min_x, min_y, max_x, max_y, area = x, y, x, y, 0
            while stack:
                cx, cy = stack.pop()
                if cx < 0 or cy < 0 or cx >= w or cy >= h or visited[cy][cx]:
                    continue
                if px[cx, cy] < ALPHA_THRESHOLD:
                    continue
                visited[cy][cx] = True
                area += 1
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                stack.extend(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)))
            if area >= MIN_COMPONENT_AREA:
                boxes.append((min_x, min_y, max_x + 1, max_y + 1))

    boxes.sort(key=lambda b: b[0])
    return boxes


def _fit_into_cell(crop: Image.Image, target_w: int = petio.CELL_W, target_h: int = petio.CELL_H) -> Image.Image:
    cw, ch = crop.size
    scale = min(target_w / cw, target_h / ch, 1.0)
    new_w = max(1, int(round(cw * scale)))
    new_h = max(1, int(round(ch * scale)))
    resized = crop.resize((new_w, new_h), Image.LANCZOS) if (new_w, new_h) != (cw, ch) else crop
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2), resized)
    return canvas


def _extract_row(run_dir: Path, row: str) -> int:
    src = run_dir / "matte" / f"{row}.png"
    if not src.exists():
        print(f"no matte for {row}", file=sys.stderr)
        return 2

    expected = petio.ROW_FRAME_COUNTS[row]
    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        alpha = rgba.split()[3]
        boxes = _components(alpha)

    manifest_path = run_dir / "manifest.json"
    manifest = petio.read_manifest(manifest_path)
    row_entry = manifest.setdefault("rows", {}).setdefault(row, {})

    if len(boxes) != expected:
        previous = row_entry.get("status")
        next_status = "failed" if previous == "needs_retry" else "needs_retry"
        petio.update_row(
            manifest_path,
            row,
            {"status": next_status, "detected_components": len(boxes), "expected": expected},
        )
        print(
            f"row {row}: {len(boxes)} components but expected {expected} → {next_status}",
            file=sys.stderr,
        )
        return 5

    out_dir = run_dir / "frames" / row
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        for idx, box in enumerate(boxes):
            crop = rgba.crop(box)
            cell = _fit_into_cell(crop)
            cell.save(out_dir / f"{idx:02d}.png", format="PNG")

    petio.update_row(
        manifest_path,
        row,
        {"status": "extracted", "detected_components": len(boxes), "frames_dir": str(out_dir.relative_to(run_dir))},
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract per-cell frames from matted strips")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--row", default=None, help="single row, otherwise all rows with matte present")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not (run_dir / "manifest.json").exists():
        print(f"not a run dir: {run_dir}", file=sys.stderr)
        return 2

    rows = [args.row] if args.row else list(petio.ROW_NAMES)
    if args.row and args.row not in petio.ROW_NAMES:
        print(f"unknown row: {args.row}", file=sys.stderr)
        return 2

    final_rc = 0
    for row in rows:
        if not args.row and not (run_dir / "matte" / f"{row}.png").exists():
            continue
        rc = _extract_row(run_dir, row)
        if rc == 5:
            final_rc = 5
        elif rc != 0:
            return rc
    return final_rc


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_extract.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract.py tests/test_extract.py
git commit -m "feat(extract): connected-component frame extraction with retry-once policy"
```

---

## Task 10: atlas.py — assemble 1536×1872 RGBA

**Files:**
- Create: `scripts/atlas.py`
- Test: `tests/test_atlas.py`

Reads `frames/<row>/NN.png` for each row, pastes into the correct (row, col) cell of a fully-transparent 1536×1872 RGBA canvas. Unused columns and missing rows stay transparent.

- [ ] **Step 1: Write the failing test**

`tests/test_atlas.py`:
```python
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
    _seed_frames(run_dir, "waving", 4)  # waving uses cols 0-3; cols 4-7 must stay transparent
    res = subprocess.run(
        [sys.executable, "-m", "scripts.atlas", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    with Image.open(run_dir / "final" / "spritesheet.png") as im:
        rgba = im.convert("RGBA")
        # waving is row 3 (idle=0, running-right=1, running-left=2, waving=3)
        for col in range(4, 8):
            x = col * 192 + 96
            y = 3 * 208 + 104
            assert rgba.getpixel((x, y))[3] == 0


def test_atlas_missing_row_leaves_transparent(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _seed_frames(run_dir, "idle", 6)  # only idle present
    res = subprocess.run(
        [sys.executable, "-m", "scripts.atlas", "--run-dir", str(run_dir)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    with Image.open(run_dir / "final" / "spritesheet.png") as im:
        rgba = im.convert("RGBA")
        # row 1 (running-right) should be fully transparent
        for col in range(8):
            x = col * 192 + 96
            y = 1 * 208 + 104
            assert rgba.getpixel((x, y))[3] == 0
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_atlas.py -v`

- [ ] **Step 3: Implement `scripts/atlas.py`**

```python
"""Assemble extracted frames into a 1536x1872 RGBA atlas."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from scripts import petio


def _paste_row(canvas: Image.Image, run_dir: Path, row: str) -> int:
    frames_dir = run_dir / "frames" / row
    if not frames_dir.is_dir():
        return 0
    expected = petio.ROW_FRAME_COUNTS[row]
    row_idx = petio.ROW_INDEX[row]
    placed = 0
    for col in range(expected):
        frame_path = frames_dir / f"{col:02d}.png"
        if not frame_path.exists():
            continue
        with Image.open(frame_path) as frame:
            cell = frame.convert("RGBA")
            if cell.size != (petio.CELL_W, petio.CELL_H):
                cell = cell.resize((petio.CELL_W, petio.CELL_H), Image.LANCZOS)
            canvas.paste(cell, (col * petio.CELL_W, row_idx * petio.CELL_H), cell)
            placed += 1
    return placed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble frames into the Codex pet atlas")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not (run_dir / "manifest.json").exists():
        print(f"not a run dir: {run_dir}", file=sys.stderr)
        return 2

    canvas = Image.new("RGBA", (petio.ATLAS_W, petio.ATLAS_H), (0, 0, 0, 0))
    placed_total = 0
    for row in petio.ROW_NAMES:
        placed_total += _paste_row(canvas, run_dir, row)

    out_dir = run_dir / "final"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "spritesheet.png"
    canvas.save(out_path, format="PNG")

    manifest_path = run_dir / "manifest.json"
    manifest = petio.read_manifest(manifest_path)
    manifest["atlas"] = {"path": str(out_path.relative_to(run_dir)), "frames_placed": placed_total}
    petio.write_manifest(manifest_path, manifest)

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_atlas.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/atlas.py tests/test_atlas.py
git commit -m "feat(atlas): assemble frames into 1536x1872 RGBA spritesheet"
```

---

## Task 11: qa.py — validation + contact sheet

**Files:**
- Create: `scripts/qa.py`
- Test: `tests/test_qa.py`

Hard checks per spec Section 7.1; soft checks reported in `qa/review.json`. Contact sheet is a labeled grid PNG for human review (`qa/contact-sheet.png`).

- [ ] **Step 1: Write the failing test**

`tests/test_qa.py`:
```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def _bootstrap_run_dir(tmp_path: Path) -> Path:
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "x", "references": []}))
    out = tmp_path / "runs"
    res = subprocess.run(
        [sys.executable, "-m", "scripts.prepare", "--request", str(req), "--output-dir", str(out)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    return Path(json.loads(res.stdout)["run_dir"])


def _make_atlas_with_full_idle(run_dir: Path) -> Path:
    canvas = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # row 0 (idle): paint cols 0..5 opaque; cols 6,7 stay transparent (correct)
    for col in range(6):
        x0 = col * 192 + 20
        y0 = 0 * 208 + 20
        draw.rectangle([x0, y0, x0 + 150, y0 + 150], fill=(120, 200, 255, 255))
    out = run_dir / "final" / "spritesheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scripts.qa", *args],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )


def test_qa_passes_on_well_formed_atlas(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _make_atlas_with_full_idle(run_dir)
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 0, res.stderr
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["dimensions"] == "pass"
    assert (run_dir / "qa" / "contact-sheet.png").exists()
    assert (run_dir / "final" / "validation.json").exists()


def test_qa_fails_on_wrong_dimensions(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)).save(
        run_dir / "final" / "spritesheet.png"
    )
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 6
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["dimensions"] == "fail"


def test_qa_fails_when_unused_cell_is_opaque(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    canvas = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # row 0 idle: paint correct 0..5
    for col in range(6):
        draw.rectangle(
            [col * 192 + 20, 0 + 20, col * 192 + 170, 170], fill=(120, 200, 255, 255)
        )
    # but also paint col 7 (must be transparent for idle)
    draw.rectangle([7 * 192 + 20, 20, 7 * 192 + 170, 170], fill=(255, 0, 0, 255))
    canvas.save(run_dir / "final" / "spritesheet.png")
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 6
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["unused_cells_transparent"] == "fail"


def test_qa_fails_when_used_cell_is_empty(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    canvas = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # row 0 idle: paint only 5 of 6 used cells; col 5 stays empty
    for col in range(5):
        draw.rectangle(
            [col * 192 + 20, 20, col * 192 + 170, 170], fill=(120, 200, 255, 255)
        )
    canvas.save(run_dir / "final" / "spritesheet.png")
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 6
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["used_cells_present"] == "fail"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_qa.py -v`

- [ ] **Step 3: Implement `scripts/qa.py`**

```python
"""Validate a codex-pet-maker atlas and emit a contact sheet for human review."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from scripts import petio


def _cell_has_alpha(rgba: Image.Image, row_idx: int, col: int) -> bool:
    box = (col * petio.CELL_W, row_idx * petio.CELL_H, (col + 1) * petio.CELL_W, (row_idx + 1) * petio.CELL_H)
    cell = rgba.crop(box)
    return cell.getextrema()[3][1] > 0


def _hard_checks(atlas_path: Path) -> dict:
    result = {
        "dimensions": "fail",
        "mode": "fail",
        "used_cells_present": "fail",
        "unused_cells_transparent": "fail",
        "webp_round_trip": "fail",
    }
    if not atlas_path.exists():
        result["dimensions_detail"] = "spritesheet.png not found"
        return result
    with Image.open(atlas_path) as im:
        rgba = im.convert("RGBA")
        result["dimensions"] = "pass" if rgba.size == (petio.ATLAS_W, petio.ATLAS_H) else "fail"
        result["mode"] = "pass" if im.mode == "RGBA" else "fail"

        used_ok = True
        unused_ok = True
        used_detail = []
        unused_detail = []
        for row in petio.ROW_NAMES:
            row_idx = petio.ROW_INDEX[row]
            count = petio.ROW_FRAME_COUNTS[row]
            for col in range(petio.GRID_COLS):
                has_alpha = _cell_has_alpha(rgba, row_idx, col)
                if col < count and not has_alpha:
                    used_ok = False
                    used_detail.append(f"{row}:{col} empty")
                elif col >= count and has_alpha:
                    unused_ok = False
                    unused_detail.append(f"{row}:{col} not transparent")
        result["used_cells_present"] = "pass" if used_ok else "fail"
        result["unused_cells_present_detail"] = used_detail
        result["unused_cells_transparent"] = "pass" if unused_ok else "fail"
        result["unused_cells_transparent_detail"] = unused_detail

        buf = io.BytesIO()
        rgba.save(buf, format="WEBP", lossless=True, quality=100, method=6)
        buf.seek(0)
        with Image.open(buf) as decoded:
            result["webp_round_trip"] = (
                "pass" if decoded.size == (petio.ATLAS_W, petio.ATLAS_H) else "fail"
            )
    return result


def _soft_checks(rgba: Image.Image, manifest: dict) -> list[str]:
    warnings: list[str] = []
    rows = manifest.get("rows", {})
    for row in petio.ROW_NAMES:
        entry = rows.get(row, {})
        if entry.get("status") == "failed":
            warnings.append(f"row {row} marked failed in manifest")
        elif entry.get("status") == "needs_retry":
            warnings.append(f"row {row} still flagged needs_retry")
    return warnings


def _contact_sheet(atlas: Image.Image) -> Image.Image:
    margin = 24
    label_h = 28
    cs_w = atlas.width + 2 * margin
    cs_h = atlas.height + 2 * margin + label_h * petio.GRID_ROWS
    canvas = Image.new("RGBA", (cs_w, cs_h), (32, 32, 32, 255))
    draw = ImageDraw.Draw(canvas)
    cursor_y = margin
    for row in petio.ROW_NAMES:
        idx = petio.ROW_INDEX[row]
        used = petio.ROW_FRAME_COUNTS[row]
        draw.text((margin, cursor_y), f"{idx}: {row} ({used} frames)", fill=(255, 255, 255, 255))
        cursor_y += label_h
        row_img = atlas.crop((0, idx * petio.CELL_H, atlas.width, (idx + 1) * petio.CELL_H))
        canvas.paste(row_img, (margin, cursor_y), row_img)
        for col in range(petio.GRID_COLS):
            x = margin + col * petio.CELL_W
            outline = (255, 255, 0, 255) if col < used else (96, 96, 96, 255)
            draw.rectangle([x, cursor_y, x + petio.CELL_W, cursor_y + petio.CELL_H], outline=outline, width=1)
        cursor_y += petio.CELL_H + 8
    return canvas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate atlas and emit contact sheet")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"not a run dir: {run_dir}", file=sys.stderr)
        return 2

    atlas_path = run_dir / "final" / "spritesheet.png"
    hard = _hard_checks(atlas_path)
    review = {"hard_checks": hard, "soft_warnings": []}
    qa_dir = run_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    if atlas_path.exists():
        with Image.open(atlas_path) as im:
            rgba = im.convert("RGBA")
            review["soft_warnings"] = _soft_checks(rgba, petio.read_manifest(manifest_path))
            _contact_sheet(rgba).save(qa_dir / "contact-sheet.png")

    (qa_dir / "review.json").write_text(json.dumps(review, indent=2, sort_keys=True))
    (run_dir / "final" / "validation.json").write_text(json.dumps(hard, indent=2, sort_keys=True))

    if any(v == "fail" for v in hard.values() if isinstance(v, str)):
        print(json.dumps(review, indent=2), file=sys.stderr)
        return 6

    manifest = petio.read_manifest(manifest_path)
    manifest["qa"] = {"status": "pass", "review_path": "qa/review.json"}
    petio.write_manifest(manifest_path, manifest)
    print(json.dumps(review, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_qa.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/qa.py tests/test_qa.py
git commit -m "feat(qa): hard checks, soft warnings, contact sheet"
```

---

## Task 12: package.py — WebP encode + pet.json

**Files:**
- Create: `scripts/package.py`
- Test: `tests/test_package.py`

Reads the validated atlas, encodes WebP per spec, writes both files into `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/`. Refuses to overwrite without `--force`. Validates that `qa/review.json` exists and has no failed hard checks.

- [ ] **Step 1: Write the failing test**

`tests/test_package.py`:
```python
from __future__ import annotations

import json
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


def test_package_writes_webp_and_petjson(tmp_path: Path, monkeypatch):
    run_dir = _bootstrap_run_dir(tmp_path)
    _seed_validated_atlas(run_dir)
    codex_home = tmp_path / "codex_home"
    import os
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
    import os
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
    import os
    env = {**os.environ, "CODEX_HOME": str(tmp_path / "codex_home")}
    res = _run(["--run-dir", str(run_dir)], env)
    assert res.returncode == 2
    assert "qa" in res.stderr.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_package.py -v`

- [ ] **Step 3: Implement `scripts/package.py`**

```python
"""Encode WebP and write pet.json into the Codex pets directory."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

from scripts import petio


def _qa_passed(qa_path: Path) -> bool:
    if not qa_path.exists():
        return False
    review = json.loads(qa_path.read_text())
    hard = review.get("hard_checks", {})
    return all(v != "fail" for v in hard.values() if isinstance(v, str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package codex-pet-maker output")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"not a run dir: {run_dir}", file=sys.stderr)
        return 2

    manifest = petio.read_manifest(manifest_path)
    slug = manifest["slug"]
    display_name = manifest["display_name"]
    description = manifest.get("description", "")

    atlas_path = run_dir / "final" / "spritesheet.png"
    qa_path = run_dir / "qa" / "review.json"
    if not atlas_path.exists():
        print(f"missing atlas: {atlas_path}", file=sys.stderr)
        return 2
    if not _qa_passed(qa_path):
        print(f"qa hard-checks not passing in {qa_path}", file=sys.stderr)
        return 2

    pet_dir = petio.codex_pets_dir() / slug
    target_webp = pet_dir / "spritesheet.webp"
    target_json = pet_dir / "pet.json"
    if pet_dir.exists() and target_webp.exists() and not args.force:
        print(f"pet already exists at {pet_dir}; pass --force to overwrite", file=sys.stderr)
        return 7

    pet_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(atlas_path) as im:
        rgba = im.convert("RGBA")
        rgba.save(target_webp, format="WEBP", lossless=True, quality=100, method=6)

    target_json.write_text(json.dumps(
        {
            "id": slug,
            "displayName": display_name,
            "description": description,
            "spritesheetPath": "spritesheet.webp",
        },
        indent=2,
    ))

    manifest["package"] = {"path": str(pet_dir), "spritesheet": "spritesheet.webp"}
    petio.write_manifest(manifest_path, manifest)

    print(json.dumps({"pet_dir": str(pet_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_package.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest -q`
Expected: all tests pass (matte slow test skipped).

- [ ] **Step 6: Commit**

```bash
git add scripts/package.py tests/test_package.py
git commit -m "feat(package): WebP encode + pet.json with collision guard"
```

---

## Task 13: SKILL.md — codex-facing workflow

**Files:**
- Create: `SKILL.md`

The codex agent's playbook. Tells it: read references, ask user for inputs, run prepare, call image_gen, call record, call matte/extract/atlas/qa/package, report. Includes resume guidance.

- [ ] **Step 1: Write `SKILL.md`** (target ≤ 250 lines)

```markdown
---
name: codex-pet-maker
description: |
  Build a Codex-app-compatible animated pet (1536×1872 atlas, 8×9 grid, pet.json + spritesheet.webp)
  from a name, a one-line description, and an optional reference image. Replaces hatch-pet's chroma-key
  matte with rembg + alpha matting (no green halo) and removes operational ceremony.
  Use this skill when the user asks to make, build, generate, or design a Codex desktop pet.
when_to_use: |
  Trigger when the user wants a new Codex desktop pet, or wants to redo an existing pet's atlas.
  Korean triggers: "코덱스 펫 만들어줘", "펫 만들어줘", "데스크탑 펫", "내 펫".
  English triggers: "make me a codex pet", "build a desktop pet", "redo my pet sprite".
---

# codex-pet-maker

You are the Codex agent driving a deterministic Python pipeline plus the built-in `image_gen` tool.
The skill produces `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/{pet.json, spritesheet.webp}`.

## Read first

- `references/codex-pet-contract.md` — the immutable atlas contract.
- `references/animation-rows.md` — the 9 row table.
- `references/qa-rubric.md` — what passes and what doesn't.

## Inputs to collect from the user

- **name** (required, e.g. "Foxy") — used as displayName; lowercased + slugified for the id.
- **description** (required, one short sentence — e.g. "A small orange fox with white belly and black-tipped tail.")
- **reference image(s)** (optional) — local PNG/JPG paths the user wants us to copy palette/silhouette from.

Save these to a JSON file before running `prepare.py`:

```json
{
  "name": "Foxy",
  "description": "A small orange fox with white belly and black-tipped tail.",
  "references": ["./fox-ref.png"]
}
```

## Pipeline

Run from the repo root. All scripts accept `--run-dir`. Default the run output under `./pet-runs/`.

### 1. prepare

```bash
python -m scripts.prepare --request ./pet_request.json --output-dir ./pet-runs
```

Records `run_dir`, prints status JSON. Reads `prompts/style.md`, `prompts/base.md`, `prompts/rows/*.md`,
substitutes `{{pet_name}}`, `{{pet_description}}`, `{{style_block}}`, writes rendered prompts into
`<run_dir>/prompts/`.

### 2. base.png (1 image_gen call)

Read `<run_dir>/prompts/base.md`. Call the built-in `image_gen` tool with that prompt and any user
reference images. Save the returned PNG to a temp path. Then ingest:

```bash
python -m scripts.record --run-dir <run_dir> --row base --source <tmp.png>
```

### 3. row strips (9 image_gen calls)

For each row in this order — `idle, running-right, running-left, waving, jumping, failed, waiting, running, review`:

1. Read `<run_dir>/prompts/rows/<row>.md`.
2. Call `image_gen` with the prompt AND attach `<run_dir>/decoded/base.png` as a reference. Request
   width that fits a horizontal strip (e.g. 1536×320 or larger; the matte pipeline rescales).
3. Save returned PNG to a temp path.
4. Ingest:
   ```bash
   python -m scripts.record --run-dir <run_dir> --row <row> --source <tmp.png>
   ```

You may parallelize rows via subagents if you need throughput; serial is fine.

### 4. matte (background removal)

```bash
python -m scripts.matte --run-dir <run_dir>
```

Skips rows whose `matte/<row>.png` already exists. To redo: pass `--force`.
First run downloads U2Net (~150 MB) into `~/.u2net/`.

### 5. extract (per-cell frames)

```bash
python -m scripts.extract --run-dir <run_dir>
```

Exit code 5 means a row's component count didn't match the expected frame count. The manifest will
mark that row `needs_retry` (or `failed` after the second miss).

When you see `needs_retry`:
- delete `<run_dir>/decoded/<row>.png` and `<run_dir>/matte/<row>.png` and `<run_dir>/frames/<row>/`
- regenerate just that row (image_gen + record + matte + extract again)

When you see `failed`: do NOT regenerate further. Continue to atlas; that row will be left fully
transparent. Mention the failed row in your final report so the user can rerun it later.

### 6. atlas

```bash
python -m scripts.atlas --run-dir <run_dir>
```

Always cheap — runs on every pass.

### 7. qa

```bash
python -m scripts.qa --run-dir <run_dir>
```

Exit code 6 means a hard check failed; do not proceed. Read `<run_dir>/qa/review.json` to see why.
Inspect `<run_dir>/qa/contact-sheet.png` to spot identity drift, halos, or wrong actions.

### 8. package

```bash
python -m scripts.package --run-dir <run_dir>
```

Writes `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/{pet.json, spritesheet.webp}`. Refuses to clobber
an existing pet — confirm with the user, then pass `--force`.

## Resume rules

The whole pipeline is resumable. Each script skips work that's already on disk. To regenerate one row:

```bash
rm <run_dir>/decoded/<row>.png <run_dir>/matte/<row>.png
rm -rf <run_dir>/frames/<row>
# … then redo image_gen + record + matte + extract for that row …
python -m scripts.atlas --run-dir <run_dir>
python -m scripts.qa --run-dir <run_dir>
python -m scripts.package --run-dir <run_dir> --force
```

To resume a previous run instead of starting fresh:

```bash
python -m scripts.prepare --request ./pet_request.json --output-dir ./pet-runs --resume <run_id>
```

## Errors you'll see

| Exit | Meaning | Action |
|---|---|---|
| 2 | usage / missing input / bad file | fix the input and retry |
| 5 | row frame-count mismatch (extract.py) | redo that row, then re-extract |
| 6 | atlas hard-check failed (qa.py) | inspect `qa/review.json`; usually means a row is empty or unused-cells aren't transparent — redo the offending row |
| 7 | pet already exists at output (package.py) | confirm with user, then `--force` |

## Final report to the user

When the pipeline completes, share:
- Pet path: `~/.codex/pets/<slug>/`
- Path to contact sheet for visual review
- Any rows in `failed` status (so user can request reruns)
- Total runtime (optional)
```

- [ ] **Step 2: Verify line count is ≤ 250**

Run: `wc -l SKILL.md`
Expected: ≤ 250.

- [ ] **Step 3: Commit**

```bash
git add SKILL.md
git commit -m "docs: SKILL.md — codex-facing workflow"
```

---

## Task 14: README.md — human install + example

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# codex-pet-maker

A lean Codex skill that builds Codex-app-compatible animated pet packages
(`${CODEX_HOME:-$HOME/.codex}/pets/<slug>/{pet.json, spritesheet.webp}`).

Replaces the chroma-key path of the original `hatch-pet` skill with `rembg` + alpha matting,
eliminating the green-halo failure mode at sprite edges.

## Install

1. Drop this folder under your Codex skills directory, e.g. `~/.codex/skills/codex-pet-maker/`.
2. Install Python deps:

   ```bash
   pip install -e .[dev]
   ```

   (or `pip install rembg onnxruntime Pillow` if you prefer the bare runtime deps.)

3. First run downloads the U2Net model (~150 MB) into `~/.u2net/`.

## Usage

In a Codex chat, ask: "make me a codex pet". The agent will pick up this skill, read `SKILL.md`,
and walk you through the 8-step pipeline.

To run by hand:

```bash
cat > pet_request.json <<EOF
{
  "name": "Foxy",
  "description": "A small orange fox with white belly and black-tipped tail.",
  "references": []
}
EOF

python -m scripts.prepare --request ./pet_request.json --output-dir ./pet-runs
# (codex agent calls image_gen 1+9 times; you ingest each result via scripts.record)
python -m scripts.matte --run-dir ./pet-runs/<run_id>
python -m scripts.extract --run-dir ./pet-runs/<run_id>
python -m scripts.atlas --run-dir ./pet-runs/<run_id>
python -m scripts.qa --run-dir ./pet-runs/<run_id>
python -m scripts.package --run-dir ./pet-runs/<run_id>
```

## Layout

- `SKILL.md` — codex agent playbook.
- `scripts/` — deterministic Python steps; each is independently invokable.
- `prompts/` — base + per-row image_gen prompts with explicit per-frame poses.
- `references/` — atlas contract, row table, QA rubric.
- `tests/` — pytest unit tests for each script.

## Tests

```bash
python -m pytest -q
# Optional rembg smoke (downloads model):
REMBG_SMOKE=1 python -m pytest -m slow
```

## Design

See `docs/superpowers/specs/2026-05-09-codex-pet-maker-design.md` for the full design discussion,
spike findings, and the rationale for each cut from the original hatch-pet.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with install and usage"
```

---

## Task 15: Final cross-check + LOC budget

- [ ] **Step 1: Verify all tests pass**

Run: `python -m pytest -q`
Expected: all green, slow test skipped.

- [ ] **Step 2: Verify Python LOC under budget**

Run: `find scripts -name '*.py' -not -name '__init__.py' | xargs wc -l`
Expected total: ≤ 1000 lines.

- [ ] **Step 3: Verify SKILL.md under budget**

Run: `wc -l SKILL.md`
Expected: ≤ 250.

- [ ] **Step 4: Verify acceptance criteria 5 + 6 (no API key, no responses-api-proxy)**

Run: `grep -RIn -e OPENAI_API_KEY -e responses-api-proxy scripts/ prompts/ SKILL.md`
Expected: no matches.

- [ ] **Step 5: Verify directory structure matches spec Section 3.2**

Run: `find . -maxdepth 3 -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/pet-runs/*' | sort`
Expected: spec layout (SKILL.md, README.md, scripts/, prompts/, references/, tests/, docs/, pyproject.toml).

- [ ] **Step 6: Tag a release**

```bash
git tag -a v0.1.0 -m "codex-pet-maker v0.1.0 — initial implementation"
```

- [ ] **Step 7: End-to-end manual smoke test (deferred)**

Document for human follow-up: run the skill inside a real codex session to generate one test pet
(e.g. "Foxy"), inspect `qa/contact-sheet.png` for green halo / identity drift, and confirm the pet
appears in the Codex desktop app.

This step is not automated because it requires:
- a real codex session for the OAuth-aware `image_gen` tool
- ~5–9 minutes of image-generation latency
- the U2Net model download
- visual judgment

---

## Self-review checklist results

- **Spec coverage**: every section of the spec maps to a task. Section 2 → Task 2 + petio constants;
  Section 3.2 layout → Task 1 + scaffolding; Section 4.1–4.5 → prompts in Tasks 4–5 + record/atlas;
  Section 5 → Task 8 (matte) and Task 9 (extract retry); Section 6 → prepare + manifest helpers;
  Section 7 → Task 11; Section 8 spike findings inform per-frame poses in Task 5; Section 9 + 10
  open questions deferred to Task 15 step 7.
- **Placeholder scan**: every code step contains real code. Where a row prompt repeats structure
  (e.g. `running-left.md`), the prompt body is fully written, not "similar to the previous task".
- **Type consistency**: `petio.ROW_NAMES`, `petio.ROW_FRAME_COUNTS`, `petio.ROW_INDEX`,
  `petio.CELL_W/CELL_H/ATLAS_W/ATLAS_H` are defined once in Task 3 and reused in Tasks 6–12 with
  the same names.
