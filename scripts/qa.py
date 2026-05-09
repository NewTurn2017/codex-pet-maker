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
    result: dict = {
        "dimensions": "fail",
        "mode": "fail",
        "used_cells_present": "fail",
        "unused_cells_transparent": "fail",
        "webp_round_trip": "fail",
    }
    if not atlas_path.exists():
        result["detail"] = "spritesheet.png not found"
        return result
    with Image.open(atlas_path) as im:
        rgba = im.convert("RGBA")
        result["dimensions"] = "pass" if rgba.size == (petio.ATLAS_W, petio.ATLAS_H) else "fail"
        result["mode"] = "pass" if im.mode == "RGBA" else "fail"

        used_ok = True
        unused_ok = True
        used_detail: list[str] = []
        unused_detail: list[str] = []
        if rgba.size == (petio.ATLAS_W, petio.ATLAS_H):
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
        else:
            used_ok = False
            unused_ok = False
        result["used_cells_present"] = "pass" if used_ok else "fail"
        result["used_cells_present_detail"] = used_detail
        result["unused_cells_transparent"] = "pass" if unused_ok else "fail"
        result["unused_cells_transparent_detail"] = unused_detail

        buf = io.BytesIO()
        rgba.save(buf, format="WEBP", lossless=True, quality=100, method=6)
        buf.seek(0)
        with Image.open(buf) as decoded:
            result["webp_round_trip"] = (
                "pass" if decoded.size == rgba.size and rgba.size == (petio.ATLAS_W, petio.ATLAS_H) else "fail"
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
    review: dict = {"hard_checks": hard, "soft_warnings": []}
    qa_dir = run_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    if atlas_path.exists():
        with Image.open(atlas_path) as im:
            rgba = im.convert("RGBA")
            review["soft_warnings"] = _soft_checks(rgba, petio.read_manifest(manifest_path))
            if rgba.size == (petio.ATLAS_W, petio.ATLAS_H):
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
