from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def _bootstrap_run_dir(tmp_path: Path) -> Path:
    req = tmp_path / "req.json"
    req.write_text(json.dumps({"name": "Foxy", "description": "x", "references": []}))
    out = tmp_path / "runs"
    res = subprocess.run(
        [sys.executable, "-m", "scripts.prepare", "--request", str(req), "--output-dir", str(out)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    return Path(json.loads(res.stdout)["run_dir"])


_ROW_FRAME_COUNTS = {
    "idle": 6, "running-right": 8, "running-left": 8, "waving": 4,
    "jumping": 5, "failed": 8, "waiting": 6, "running": 6, "review": 6,
}
_ROW_NAMES = (
    "idle", "running-right", "running-left", "waving", "jumping",
    "failed", "waiting", "running", "review",
)


def _make_well_formed_atlas(run_dir: Path) -> Path:
    """Paint every used cell of every row; leave unused columns transparent."""
    canvas = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for row_idx, row in enumerate(_ROW_NAMES):
        used = _ROW_FRAME_COUNTS[row]
        for col in range(used):
            x0 = col * 192 + 20
            y0 = row_idx * 208 + 20
            draw.rectangle([x0, y0, x0 + 150, y0 + 150], fill=(120, 200, 255, 255))
    out = run_dir / "final" / "spritesheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scripts.qa", *args],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )


def test_qa_passes_on_well_formed_atlas(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    _make_well_formed_atlas(run_dir)
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 0, res.stderr
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["dimensions"] == "pass"
    assert (run_dir / "qa" / "contact-sheet.png").exists()
    assert (run_dir / "final" / "validation.json").exists()


def test_qa_fails_on_wrong_dimensions(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)).save(
        run_dir / "final" / "spritesheet.png"
    )
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 6
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["dimensions"] == "fail"


def test_qa_fails_when_unused_cell_is_opaque(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    canvas = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for col in range(6):
        draw.rectangle(
            [col * 192 + 20, 0 + 20, col * 192 + 170, 170], fill=(120, 200, 255, 255)
        )
    draw.rectangle([7 * 192 + 20, 20, 7 * 192 + 170, 170], fill=(255, 0, 0, 255))
    canvas.save(run_dir / "final" / "spritesheet.png")
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 6
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["unused_cells_transparent"] == "fail"


def test_qa_fails_when_used_cell_is_empty(tmp_path: Path):
    run_dir = _bootstrap_run_dir(tmp_path)
    canvas = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for col in range(5):
        draw.rectangle(
            [col * 192 + 20, 20, col * 192 + 170, 170], fill=(120, 200, 255, 255)
        )
    canvas.save(run_dir / "final" / "spritesheet.png")
    res = _run(["--run-dir", str(run_dir)])
    assert res.returncode == 6
    review = json.loads((run_dir / "qa" / "review.json").read_text())
    assert review["hard_checks"]["used_cells_present"] == "fail"
