# codex-pet-maker

A lean Codex skill that builds Codex-app-compatible animated pet packages
(`${CODEX_HOME:-$HOME/.codex}/pets/<slug>/{pet.json, spritesheet.webp}`).

Replaces the chroma-key path of the original `hatch-pet` skill with `rembg` + alpha matting,
eliminating the green-halo failure mode at sprite edges.

## Install

1. Drop this folder under your Codex skills directory, e.g. `~/.codex/skills/codex-pet-maker/`.
2. Install Python deps:

   ```bash
   pip install -e '.[dev]'
   ```

   (the quotes matter on zsh — `[dev]` is otherwise interpreted as a glob.
   Or `pip install rembg onnxruntime Pillow numpy` if you prefer the bare runtime deps.)

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
