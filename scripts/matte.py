"""Background removal with rembg + alpha matting."""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

from scripts import petio


def _matte_one(session, src: Path, dst: Path) -> None:
    import rembg

    raw = src.read_bytes()
    out_bytes = rembg.remove(
        raw,
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=2,
    )
    with Image.open(io.BytesIO(out_bytes)) as im:
        im.convert("RGBA").save(dst, format="PNG")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove background from decoded row strips")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    decoded = run_dir / "decoded"
    matte_dir = run_dir / "matte"
    matte_dir.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, Path, Path]] = []
    for row in petio.ROW_NAMES:
        src = decoded / f"{row}.png"
        if not src.exists():
            continue
        dst = matte_dir / f"{row}.png"
        if dst.exists() and not args.force:
            continue
        targets.append((row, src, dst))

    if not targets:
        print("nothing to matte", file=sys.stderr)
        return 0

    try:
        from rembg import new_session
    except ImportError:
        print("rembg not installed; pip install rembg onnxruntime", file=sys.stderr)
        return 2

    session = new_session("u2net")
    manifest_path = run_dir / "manifest.json"
    for row, src, dst in targets:
        _matte_one(session, src, dst)
        petio.update_row(manifest_path, row, {"status": "matted", "matte_path": str(dst.relative_to(run_dir))})
        print(str(dst))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
