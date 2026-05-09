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
