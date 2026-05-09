"""Extract per-cell frames from matted row strips via column-projection segmentation.

The Codex Pet prompt mandates that row strips are horizontal with no horizontally
overlapping frames, so a simple alpha-projection onto the x-axis is sufficient to
segment the strip into N frames. Connected-components flood-fill would also work,
but projection is faster, deterministic, and easier to reason about.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from scripts import petio

ALPHA_THRESHOLD = 16
MIN_RUN_WIDTH = 8  # px — drops orphan specks between frames


def _column_runs(alpha: np.ndarray) -> list[tuple[int, int]]:
    """Return [start, end) column ranges where each column has any pixel above threshold."""
    col_has = (alpha >= ALPHA_THRESHOLD).any(axis=0)
    runs: list[tuple[int, int]] = []
    in_run = False
    start = 0
    for i, v in enumerate(col_has):
        if v and not in_run:
            start = i
            in_run = True
        elif not v and in_run:
            if i - start >= MIN_RUN_WIDTH:
                runs.append((start, i))
            in_run = False
    if in_run and len(col_has) - start >= MIN_RUN_WIDTH:
        runs.append((start, len(col_has)))
    return runs


def _bbox_for_run(alpha: np.ndarray, x0: int, x1: int) -> tuple[int, int, int, int]:
    region = alpha[:, x0:x1]
    rows_with = (region >= ALPHA_THRESHOLD).any(axis=1)
    ys = np.where(rows_with)[0]
    if len(ys) == 0:
        return x0, 0, x1, alpha.shape[0]
    y0, y1 = int(ys[0]), int(ys[-1]) + 1
    return x0, y0, x1, y1


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
        alpha_arr = np.array(rgba.split()[3])
        runs = _column_runs(alpha_arr)
        boxes = [_bbox_for_run(alpha_arr, x0, x1) for x0, x1 in runs]

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

    if args.row and args.row not in petio.ROW_NAMES:
        print(f"unknown row: {args.row}", file=sys.stderr)
        return 2

    rows = [args.row] if args.row else list(petio.ROW_NAMES)

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
