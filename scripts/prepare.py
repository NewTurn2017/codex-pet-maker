"""Initialize a codex-pet-maker run directory from a pet request."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from scripts import petio

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _render(template: str, *, style: str, pet_name: str, pet_description: str) -> str:
    return (
        template.replace("{{style_block}}", style.strip())
        .replace("{{pet_name}}", pet_name)
        .replace("{{pet_description}}", pet_description)
    )


def _ensure_dirs(run_dir: Path) -> None:
    for sub in ("decoded", "matte", "frames", "final", "qa", "references", "prompts/rows"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)


def _copy_references(srcs: list[str], run_dir: Path) -> list[str]:
    copied: list[str] = []
    for src in srcs:
        src_path = Path(src).expanduser().resolve()
        if not src_path.exists():
            raise SystemExit(f"reference not found: {src}")
        dest = run_dir / "references" / src_path.name
        shutil.copy2(src_path, dest)
        copied.append(str(dest))
    return copied


def _render_prompts(run_dir: Path, pet_name: str, pet_description: str) -> None:
    style = (PROMPTS_DIR / "style.md").read_text()
    base_template = (PROMPTS_DIR / "base.md").read_text()
    (run_dir / "prompts" / "base.md").write_text(
        _render(base_template, style=style, pet_name=pet_name, pet_description=pet_description)
    )
    rows_dir = PROMPTS_DIR / "rows"
    out_rows = run_dir / "prompts" / "rows"
    for row in petio.ROW_NAMES:
        template = (rows_dir / f"{row}.md").read_text()
        (out_rows / f"{row}.md").write_text(
            _render(template, style=style, pet_name=pet_name, pet_description=pet_description)
        )


def _initial_manifest(run_id: str, slug: str, display_name: str, description: str, references: list[str]) -> dict:
    return {
        "run_id": run_id,
        "slug": slug,
        "display_name": display_name,
        "description": description,
        "references": references,
        "rows": {row: {"status": "pending", "frame_count": petio.ROW_FRAME_COUNTS[row]} for row in petio.ROW_NAMES},
        "base": {"status": "pending"},
    }


def _existing_run_dir(parent: Path, run_id: str) -> Path | None:
    candidate = parent / run_id
    return candidate if candidate.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a codex-pet-maker run directory")
    parser.add_argument("--request", required=True, help="path to pet request JSON")
    parser.add_argument("--output-dir", required=True, help="parent directory for runs (e.g. ./pet-runs)")
    parser.add_argument("--resume", default=None, help="existing run id under --output-dir")
    args = parser.parse_args(argv)

    request_path = Path(args.request)
    if not request_path.exists():
        print(f"request file not found: {request_path}", file=sys.stderr)
        return 2

    try:
        request = json.loads(request_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"invalid request JSON: {exc}", file=sys.stderr)
        return 2

    name = request.get("name")
    description = request.get("description", "")
    references = list(request.get("references", []))

    if not isinstance(name, str) or not name.strip():
        print("request.name must be a non-empty string", file=sys.stderr)
        return 2
    if not isinstance(description, str):
        print("request.description must be a string", file=sys.stderr)
        return 2

    try:
        slug = petio.slugify(name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.resume:
        run_dir = _existing_run_dir(output_dir, args.resume)
        if run_dir is None:
            print(f"resume target not found: {args.resume}", file=sys.stderr)
            return 2
        run_id = args.resume
    else:
        run_id = petio.new_run_id(slug)
        run_dir = output_dir / run_id
        run_dir.mkdir()

    _ensure_dirs(run_dir)
    shutil.copy2(request_path, run_dir / "pet_request.json")
    refs = _copy_references(references, run_dir)
    _render_prompts(run_dir, pet_name=name, pet_description=description)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        petio.write_manifest(
            manifest_path,
            _initial_manifest(run_id, slug, name, description, refs),
        )

    status = {
        "run_id": run_id,
        "run_dir": str(run_dir.resolve()),
        "slug": slug,
        "display_name": name,
        "rows": list(petio.ROW_NAMES),
        "frame_counts": petio.ROW_FRAME_COUNTS,
        "next_action": "use built-in Codex image_gen for base.png and per-row strips",
    }
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
