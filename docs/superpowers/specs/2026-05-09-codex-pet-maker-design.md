# codex-pet-maker — Design Spec

- **Date**: 2026-05-09
- **Project root**: `/Users/genie/dev/tools/skills/codex-pet-maker/`
- **Reference**: openai/skills `skills/.curated/hatch-pet/` (commit at `main` as of 2026-05-09)
- **Status**: design approved by user, ready for implementation planning

---

## 1. Problem

The original `hatch-pet` skill produces Codex-app-compatible animated pets (8×9 sprite atlas, `pet.json`), but has two concrete problems the user surfaced:

1. **Background removal leaves green halo pixels.** The chroma-key matte in `scripts/extract_strip_frames.py` uses a hard binary mask with no despill: pixels passing the threshold keep their full RGB (including anti-aliased green bleed at sprite edges); pixels failing get fully transparent. Result: visible green halo or jagged edges depending on threshold.
2. **The skill is operationally heavy.** 16 Python scripts, sha256 provenance tracking, subagent write-boundary contracts, layout-guide PNG attachments, manifest mutation rules, secondary CLI fallback, mirror-decision branching, preview MP4 generation. Most of this exists to constrain LLM behavior across a multi-step manual workflow.

The user wants a leaner skill (`codex-pet-maker`) that fixes the matte and removes operational ceremony, while still producing artifacts that exactly satisfy the Codex Pet contract.

## 2. Codex Pet Contract (CHECK-IN, immutable)

These values are dictated by the Codex desktop app's pet system. We do not redefine them.

### Atlas

| Property | Value |
|---|---|
| Format | PNG or WebP |
| Dimensions | exactly **1536 × 1872** pixels |
| Color | RGBA, transparent-capable |
| Grid | **8 columns × 9 rows** |
| Cell | exactly **192 × 208** pixels |
| Background | fully transparent |
| Unused cells | fully transparent (alpha == 0) |
| Forbidden | labels, gutters, borders, drawn grid lines, shadows outside cells, extra frames |

### WebP encoding (for `spritesheet.webp`)

```python
image.convert("RGBA").save(target, format="WEBP", lossless=True, quality=100, method=6)
```

(Identical to `package_custom_pet.py` in the original.)

### `pet.json` schema (exact, no extra keys)

```json
{
  "id": "pet-name",
  "displayName": "Pet Name",
  "description": "One short sentence.",
  "spritesheetPath": "spritesheet.webp"
}
```

### ID slug rule

```python
def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")
```

### Output package location

```
${CODEX_HOME:-$HOME/.codex}/pets/<pet-id>/
├── pet.json
└── spritesheet.webp
```

### Animation rows (FIXED — match `references/animation-rows.md`)

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

The Codex app reads cells by fixed (row, column) index and animates per these durations. Used cells in each row must be non-empty; cells in unused columns of each row must be fully transparent.

## 3. Architecture

### 3.1 Pattern: Codex skill + scripts (NOT standalone CLI)

The user requires OAuth-only authentication. After investigation:

- The official `imagegen` system skill at `${CODEX_HOME:-$HOME/.codex}/skills/.system/imagegen/` documents the only OAuth-aware path: a built-in `image_gen` tool exposed inside the codex agent's tool loop. This tool is **not callable from external subprocess**; it is only available when codex itself is the agent driving the work.
- The codex CLI 0.129's `responses-api-proxy` subcommand (the successor to the 0.123 `responses` subcommand) requires `OPENAI_API_KEY` fed via stdin. This breaks OAuth-only.
- Therefore a standalone CLI like `codex-sangpye` cannot satisfy the OAuth-only constraint on codex 0.129+.

The skill is therefore a `SKILL.md` + `scripts/` + `prompts/` + `references/` package. The codex agent reads `SKILL.md`, runs the deterministic Python scripts via subprocess, and invokes the built-in `image_gen` tool for the visual generation steps.

### 3.2 Directory layout

```
skills/codex-pet-maker/
  SKILL.md                          # ~200 lines, codex-facing workflow
  README.md                         # human-facing install + example
  scripts/
    prepare.py                      # ~150 lines
    record.py                       # ~80 lines
    matte.py                        # ~120 lines (NEW: rembg)
    extract.py                      # ~150 lines
    atlas.py                        # ~100 lines
    qa.py                           # ~150 lines
    package.py                      # ~80 lines (near-verbatim from original)
  prompts/
    base.md                         # base pet prompt template
    style.md                        # Codex digital pet style block (shared)
    rows/
      idle.md, running-right.md, running-left.md,
      waving.md, jumping.md, failed.md,
      waiting.md, running.md, review.md
  references/
    codex-pet-contract.md           # contract (Section 2 of this spec)
    animation-rows.md               # row table (Section 2 of this spec)
    qa-rubric.md                    # acceptance criteria (Section 7)
  docs/
    superpowers/
      specs/
        2026-05-09-codex-pet-maker-design.md   # this file
```

Total: ~830 lines of Python + ~200 lines of SKILL.md + ~500 lines of prompts. Roughly one third the size of the original hatch-pet.

### 3.3 What the original hatch-pet keeps

- `SKILL.md` + `scripts/` + `prompts/` + `references/` package shape
- `prepare → image_gen → record → finalize` step model
- `~/.codex/pets/<slug>/{pet.json, spritesheet.webp}` output location
- The verbatim "Codex Digital Pet Style" wording (proven good)
- Per-row "forbidden effects" wording (proven good — `idle` is calm, `jumping` has no shadows, `running` is busy-task not foot-running, etc.)
- Identity-lock pattern: generate `base.png` first, attach it to every row prompt
- `package_custom_pet.py` essentially as-is

### 3.4 What the original hatch-pet removes (lean cuts)

| Removed | Why |
|---|---|
| chroma-key matte path entirely | replaced by rembg + alpha matting (Section 4) |
| `references/layout-guides/*.png` (9 PNG files) | spike Section 8.3 confirmed `base.png` attach + per-frame pose descriptions in row prompts is sufficient |
| `derive_running_left_from_running_right.py` + mirror-decision branching | always generate `running-left` separately; small cost increase, large simplification |
| sha256 source/output hash provenance | optional manifest field, no validation enforcement |
| `imagegen-jobs.json` mutation rules + subagent write-boundary contract | manifest is informational; disk file existence is the truth (sangpye-style) |
| `generate_pet_images.py` secondary fallback (direct OpenAI API) | OAuth-only constraint forbids this anyway |
| `render_animation_videos.py` + `render_animation_videos.sh` (preview MP4s) | contact-sheet PNG is sufficient QA; ffmpeg dependency removed |
| `compose_atlas.py` + `validate_atlas.py` + `make_contact_sheet.py` + `inspect_frames.py` separate scripts | folded into `atlas.py` + `qa.py` |
| `queue_pet_repairs.py` separate script | folded into `extract.py` (mismatch retry policy) and `SKILL.md` (rerun guidance) |
| `pet_job_status.py` separate script | folded into `prepare.py` (status JSON output) |

### 3.5 What's new

- `matte.py` using `rembg` + alpha matting for background removal
- Per-frame pose descriptions in every row prompt (Section 4.3)
- Frame-count validation with single retry, then row-fail (Section 5.2)

## 4. Image generation

### 4.1 Path

The codex agent invokes the built-in `image_gen` tool. The skill never calls OpenAI's REST API directly. The skill never invokes `codex responses-api-proxy`. The skill never runs `scripts/image_gen.py` from the imagegen system skill.

### 4.2 Per-pet calls

| Call | Purpose | Inputs |
|---|---|---|
| 1 | base.png — pet identity image | base.md prompt + user reference (if provided) |
| 2–10 | row strips (9 rows, one each) | row-N.md prompt + base.png + user reference (if provided) |

Total: 10 `image_gen` calls per pet. The codex agent decides whether to parallelize via subagents or run serially. The skill imposes no requirement.

### 4.3 Row prompt template (mandatory shape)

Validated by spike Section 8.3: row prompts must include explicit per-frame pose descriptions, not just a frame count and an action verb. Without these, the model produces near-duplicate poses regardless of `frame_count`.

```
{{style_block}}

Identity lock (mandatory):
The attached image is the canonical {{pet_name}}. Match it EXACTLY — same head shape, face, markings, palette, outline weight, body proportions, silhouette.

Animation row: {{state_name}}
Frame count: produce EXACTLY {{frame_count}} distinct frames in a horizontal strip.

Per-frame poses:
  Frame 1: {{pose_1}}
  Frame 2: {{pose_2}}
  ...
  Frame N: {{pose_N}}

Layout: horizontal strip, all {{frame_count}} frames in a single row, equal
spacing, each frame the same size, safe padding around each, no frame
touching another. Background pure white #FFFFFF everywhere.

Action: {{state_action}}

Forbidden in this row: {{state_forbids}}, plus everywhere: text, labels,
frame numbers, borders, grid lines, shadows outside character, scenery,
fewer than {{frame_count}} frames, more than {{frame_count}} frames.
```

### 4.4 Per-row pose lists (initial draft, may iterate during implementation)

Each row has explicit per-frame poses. Example for `running-right` (8 frames):

```
Frame 1: contact — right paw planted forward, left paw lifting back
Frame 2: down — right paw planted, body slightly lowered, left paw mid-air swinging forward
Frame 3: passing — both paws crossing, body at lowest point
Frame 4: up — left paw planted forward, right paw pushing off, body rising
Frame 5: contact — left paw planted forward, right paw lifting back (mirror of frame 1)
Frame 6: down — left paw planted, body lowered, right paw mid-air swinging forward
Frame 7: passing — both paws crossing, body at lowest point
Frame 8: up — right paw planted forward, left paw pushing off, body rising
```

Equivalent per-frame lists must exist for all 9 rows. Implementation phase will draft and refine these against test pet runs.

### 4.5 Background spec change (chroma → white)

Original prompts said "render on a removable chroma-key background (default green)". New prompts say "background pure white #FFFFFF everywhere". rembg handles arbitrary clean backgrounds; white was empirically chosen because:
- model produces cleanest white background among neutral colors
- white avoids confusion with any in-character color
- rembg's default U2Net model performs well on white-background subjects

## 5. Background removal (matte)

### 5.1 Algorithm

```python
import rembg
output = rembg.remove(
    raw_image,
    alpha_matting=True,
    alpha_matting_foreground_threshold=240,
    alpha_matting_background_threshold=10,
    alpha_matting_erode_size=2,
)
```

- Background-color-agnostic: works regardless of which non-character color the model produced
- Soft alpha at edges: no jagged binary mask
- No despill needed: rembg's foreground model emits clean RGB inside the silhouette
- Eliminates the "green halo" failure mode entirely

### 5.2 Frame-count validation policy

Run `connected_components` on the matted strip. Compare component count to `frame_count`.

| Condition | Action |
|---|---|
| count == frame_count | accept |
| count != frame_count, first failure | regenerate the row (single retry, with even stronger frame-count language) |
| count != frame_count, retry failed | mark this row as failed in `manifest.json`, leave its row in the atlas fully transparent, exit with code 5 |

The skill **never falls back to fixed-slot extraction** when components don't match. Slot extraction was the original's escape hatch but produces visually broken cells (partial sprites, empty cells), which is a different flavor of the user's "inefficient" complaint.

### 5.3 Dependencies

```toml
# pyproject.toml or requirements.txt for the scripts/
rembg = "*"
onnxruntime = "*"
Pillow = "*"
```

First run downloads U2Net model (~150 MB) into `~/.u2net/`. Subsequent runs are fast.

The codex agent's environment must satisfy these. `SKILL.md` instructs the user to run `pip install rembg onnxruntime Pillow` before first use, or include a `setup.sh` that does it.

## 6. Manifest and resume

### 6.1 Run directory layout

```
./pet-runs/<run-id>/
  pet_request.json           # user input snapshot (name, description, references, ...)
  manifest.json              # per-step status (informational)
  references/                # copies of user-provided reference images
  prompts/                   # rendered prompt files per step
  decoded/                   # ingested image_gen outputs
    base.png
    idle.png, running-right.png, ..., review.png
  matte/                     # post-rembg PNGs
    idle.png, ..., review.png
  frames/                    # extracted per-cell frames
    idle/00.png ... 05.png
    running-right/00.png ... 07.png
    ...
  final/
    spritesheet.png          # 1536x1872 RGBA
    validation.json
  qa/
    contact-sheet.png
    review.json
```

Default location: `./pet-runs/<run-id>/` in the user's current working directory. Override via `--output-dir` argument to `prepare.py`.

### 6.2 Resume model

Each script checks for the existence of its outputs and skips work that's already done. Manifest is informational, not authoritative. Hash verification is not enforced.

```
matte.py:    matte/<row>.png exists → skip
extract.py:  frames/<row>/ has frame_count PNGs → skip
atlas.py:    final/spritesheet.png always rebuilt (cheap)
qa.py:       always rebuilt
package.py:  always rebuilt
```

Force regeneration by deleting the relevant directory or passing `--force` to the relevant script.

To regenerate one row: delete `decoded/<row>.png`, `matte/<row>.png`, `frames/<row>/`. The next codex agent step will detect the gap and re-call `image_gen` for that row.

## 7. QA and validation

### 7.1 Deterministic validation (`qa.py` writes `qa/review.json` and `final/validation.json`)

Hard checks (failures → exit 6, no package written):
- `final/spritesheet.png` size == (1536, 1872)
- mode == RGBA
- For each row, used-column cells have non-zero alpha somewhere
- For each row, unused-column cells have alpha == 0 everywhere
- After WebP encode + decode, dimensions still (1536, 1872)
- `pet.json` has exactly `{id, displayName, description, spritesheetPath}` keys, no others
- `id == slugify(displayName)`

Soft checks (failures → reported as warnings in review.json, package still written):
- frame_count detected per row matches expected count (already enforced by extract.py retry policy)
- chroma-key-adjacent pixels (warn only, since rembg should remove all background)
- per-frame pixel-area outliers within a row (warn — likely identity drift)

### 7.2 Contact sheet (`qa/contact-sheet.png`)

Single PNG showing all 9 rows × 8 columns labeled with row name, frame index, and visible cell boundaries (this PNG is for human inspection only — never confused with `spritesheet.png`). Failed cells (from exit 5 path) are marked with a red "FAILED" overlay.

### 7.3 Acceptance rubric (encoded in `references/qa-rubric.md`)

Adapts original `qa-rubric.md`, replacing chroma-key wording with rembg-equivalent:

```
- Atlas geometry: pass
- Identity consistency across rows: visual review of contact-sheet
- No background bleed (no halo, no transparent islands inside character): visual review
- Per-row action distinguishable from idle: visual review
- Directional rows actually directional: visual review
- Idle/waiting/review distinguishable from each other: visual review
- No motion lines, dust, shadows, text: validation.json + visual review
```

Visual review is performed by the codex agent (or user) inspecting `qa/contact-sheet.png`. The skill does not attempt automated identity-drift detection.

## 8. Spike findings (informing the design)

### 8.1 Codex CLI 0.129 surface change

- The `responses` subcommand from codex 0.123 (which `codex-sangpye` uses) is renamed to `responses-api-proxy` in 0.129.
- The new proxy listens on an HTTP port and requires `OPENAI_API_KEY` fed via stdin.
- The `codex-sangpye` skill's claim "uses your Codex OAuth session — no API key" is broken on codex 0.129+.
- The OAuth-aware path on 0.129+ is the codex agent's built-in `image_gen` tool, accessible only inside a codex session — not from external subprocess.

This finding is what forced the architecture pivot from "standalone CLI" to "skill + scripts orchestrated by codex agent".

### 8.2 1-call full atlas attempt

Generated a single 1024×1536 PNG asking for 8×9 grid with 9 distinct row actions and per-row frame counts.

| Criterion | Result |
|---|---|
| Grid (requested 8×9) | failed — produced 5×7 |
| Identity (35 cells of one Foxy) | excellent — every cell same character |
| Row action separation | failed — all rows render walk/idle variants |
| Frame count compliance | failed — uniform 5 per row |

Score: 1/4. Confirms 1-call atlas is not feasible; per-row generation is required.

### 8.3 Per-row generation tests

| Variant | Frame variation | Frame count | Identity |
|---|---|---|---|
| Row prompt only, no base attached | poor (near-duplicate poses) | 5/8 | OK |
| Row prompt + base.png attached + per-frame pose descriptions | good (real walk cycle) | 6/8 | excellent |

Per-row generation works only when:
1. base.png is generated first and attached to every row call
2. row prompts include explicit per-frame pose descriptions

Frame count is still off by 1–2 even at best — hence the retry-once-then-fail policy in Section 5.2.

### 8.4 Timing data (from spike, codex 0.129, gpt-5.5, OAuth path was unavailable so used API key proxy)

| Operation | Time |
|---|---|
| base.png at 1024×1024 high quality | ~33 s |
| row strip at 1536×1024 high quality | ~55 s |
| Full pet, serial (1 base + 9 rows) | ~530 s = 8.8 min |
| Full pet, codex parallelism = 2 (subagents) | ~310 s = 5.2 min |

Performance via the OAuth path inside a codex agent is expected to be similar (image generation latency dominates network/CLI overhead).

## 9. Out of scope

- Pet concept brainstorming (user provides name, description, optional reference)
- Generic sprite-sheet generation (this skill is hard-coded to the Codex Pet contract)
- Atlas dimensions or row layouts other than the contract values
- API-key-based execution (out of scope by user constraint)
- ChatGPT-tier subscription troubleshooting (surface error, do not retry)
- Webview rendering of the pet (Codex app handles this)
- Editing existing pets (delete the pet folder and re-run from scratch)

## 10. Open questions for implementation phase

1. **rembg parameter tuning**: are the alpha-matting thresholds (240/10) optimal for the chibi pixel-art style, or do they erode pixel-perfect outline edges? Test against generated chibi sprites; if outlines are damaged, lower foreground threshold to ~220.
2. **Per-frame pose lists**: 9 row-specific lists need to be drafted and validated against ≥2 different pet styles (e.g., a fox and a robot). Some rows (`waiting`, `review`, `running` busy-task) need particular care because their actions are non-obvious.
3. **First-run UX**: codex agent should detect missing rembg/onnxruntime and instruct user to install; should the skill ship a `setup.sh` that handles this in one command?
4. **Existing pet collision**: what happens when `~/.codex/pets/foxy/` already exists from a previous run? Original uses `--force` flag on `package.py`. Mirror that behavior; codex agent asks user before passing `--force`.
5. **Multi-pet runs**: a user asking "make me 3 pets" — does the codex agent run them serially, or in parallel via subagents? `SKILL.md` should give explicit guidance here.

## 11. Acceptance criteria (for the spec, not for runtime pets)

The implementation is done when:
1. Running the skill end-to-end via codex chat against a sample reference image produces `~/.codex/pets/<slug>/{pet.json, spritesheet.webp}` with all hard checks in Section 7.1 passing.
2. Visual inspection of `qa/contact-sheet.png` shows no green halo or background bleed (the user-reported failure mode is gone).
3. Total Python LOC ≤ 1000 lines (vs. ~3000 in original hatch-pet).
4. SKILL.md ≤ 250 lines (vs. ~322 in original).
5. The skill works under codex >= 0.121 (sangpye-tested baseline) and codex >= 0.129 (current) without code change.
6. The skill never invokes `OPENAI_API_KEY` and never calls `codex responses-api-proxy`.
