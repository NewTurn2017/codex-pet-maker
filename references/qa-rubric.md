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
