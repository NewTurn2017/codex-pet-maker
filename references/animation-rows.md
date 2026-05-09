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
