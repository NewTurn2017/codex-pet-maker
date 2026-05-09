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

You are the Codex agent driving a deterministic Python pipeline plus the built-in Codex `image_gen` tool.
The skill produces `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/{pet.json, spritesheet.webp}`.

## Image generation authority

- Use **Codex's built-in `image_gen` tool** for every creative image in the pet pipeline: the base character, all row strips, and any temporary visual check image.
- Do **not** satisfy a pet request with a hand-drawn/vector/script-generated/manual placeholder sheet. Python scripts are only for deterministic post-processing: recording outputs, alpha matting, frame extraction, atlas assembly, QA, and packaging.
- Do **not** require or assume the separate `gpt-image` skill. It is not installed by this skill's `install.sh` / `install.ps1` flow. If a user explicitly asks for `gpt-image` and that skill is available, it may be used as an external override, but the default and self-contained workflow remains built-in `image_gen`.
- If you need a quick identity preview before creating all 9 rows, generate the preview with built-in `image_gen`, record it as `base`, and continue or regenerate from there. Never switch to manual drawing as a shortcut.

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

If the skill was installed with `./install.sh`, prefer the bundled virtualenv Python:

```bash
PY=./.venv/bin/python
[ -x "$PY" ] || PY=python
```

### 1. prepare

```bash
$PY -m scripts.prepare --request ./pet_request.json --output-dir ./pet-runs
```

Records `run_dir`, prints status JSON. Reads `prompts/style.md`, `prompts/base.md`, `prompts/rows/*.md`,
substitutes `{{pet_name}}`, `{{pet_description}}`, `{{style_block}}`, writes rendered prompts into
`<run_dir>/prompts/`.

### 2. base.png (1 built-in image_gen call)

Read `<run_dir>/prompts/base.md`. Call the built-in `image_gen` tool with that prompt and any user
reference images. Save the returned PNG to a temp path. Then ingest:

```bash
$PY -m scripts.record --run-dir <run_dir> --row base --source <tmp.png>
```

### 3. row strips (9 built-in image_gen calls)

For each row in this order — `idle, running-right, running-left, waving, jumping, failed, waiting, running, review`:

1. Read `<run_dir>/prompts/rows/<row>.md`.
2. Call `image_gen` with the prompt AND attach `<run_dir>/decoded/base.png` as a reference. Request
   width that fits a horizontal strip (e.g. 1536×320 or larger; the matte pipeline rescales).
3. Save returned PNG to a temp path.
4. Ingest:
   ```bash
   $PY -m scripts.record --run-dir <run_dir> --row <row> --source <tmp.png>
   ```

You may parallelize rows via subagents if you need throughput; serial is fine.

### 4. matte (background removal)

```bash
$PY -m scripts.matte --run-dir <run_dir>
```

Skips rows whose `matte/<row>.png` already exists. To redo: pass `--force`.
First run downloads U2Net (~150 MB) into `~/.u2net/`.

### 5. extract (per-cell frames)

```bash
$PY -m scripts.extract --run-dir <run_dir>
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
$PY -m scripts.atlas --run-dir <run_dir>
```

Always cheap — runs on every pass.

### 7. qa

```bash
$PY -m scripts.qa --run-dir <run_dir>
```

Exit code 6 means a hard check failed; do not proceed. Read `<run_dir>/qa/review.json` to see why.
Inspect `<run_dir>/qa/contact-sheet.png` to spot identity drift, halos, or wrong actions.

### 8. package

```bash
$PY -m scripts.package --run-dir <run_dir>
```

Writes `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/{pet.json, spritesheet.webp}`. Refuses to clobber
an existing pet — confirm with the user, then pass `--force`.

## Resume rules

The whole pipeline is resumable. Each script skips work that's already on disk. To regenerate one row:

```bash
rm <run_dir>/decoded/<row>.png <run_dir>/matte/<row>.png
rm -rf <run_dir>/frames/<row>
# … then redo image_gen + record + matte + extract for that row …
$PY -m scripts.atlas --run-dir <run_dir>
$PY -m scripts.qa --run-dir <run_dir>
$PY -m scripts.package --run-dir <run_dir> --force
```

To resume a previous run instead of starting fresh:

```bash
$PY -m scripts.prepare --request ./pet_request.json --output-dir ./pet-runs --resume <run_id>
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
