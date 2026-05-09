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
