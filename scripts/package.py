"""Encode WebP and write pet.json into the Codex pets directory."""
from __future__ import annotations

import argparse
import json
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
