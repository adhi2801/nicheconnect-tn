"""Turn the landing page's Blender renders into the images the website serves.

The renders are made by frontend/3d/temple/vimana.py (the turning tower, 48
frames) and frontend/3d/seal/seal.py (the bronze seal), at full size, as
PNG. The website serves WebP at the widths it shows (frontend.md section 4):
640, 960 and 1280 for the tower, 640 and 960 for the seal.

Usage, from frontend/:
    python scripts/export_landing.py <orbit frames dir> <seal png>

Needs Pillow with WebP (the repository's Python environment has it).
"""

import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "apps" / "web" / "public" / "landing"
ORBIT_WIDTHS = (640, 960, 1280)
SEAL_WIDTHS = (640, 960)
# Dark, smooth stone takes compression well; 72 keeps the carving's edges.
QUALITY = 72


def export(source: Path, target: Path, width: int) -> int:
    with Image.open(source) as image:
        rgb = image.convert("RGB")
        height = round(rgb.height * width / rgb.width)
        rgb.resize((width, height), Image.Resampling.LANCZOS).save(
            target, "WEBP", quality=QUALITY, method=6
        )
    return target.stat().st_size


def main(orbit_dir: Path, seal: Path) -> None:
    frames = sorted(orbit_dir.glob("f[0-9][0-9].png"))
    if len(frames) != 48:
        raise SystemExit(f"expected 48 frames in {orbit_dir}, found {len(frames)}")
    for width in ORBIT_WIDTHS:
        folder = OUT / "orbit" / str(width)
        folder.mkdir(parents=True, exist_ok=True)
        total = sum(export(f, folder / f"{f.stem}.webp", width) for f in frames)
        print(f"orbit {width}: {total / 1024:.0f} KB for 48 frames")
    for width in SEAL_WIDTHS:
        size = export(seal, OUT / f"seal-{width}.webp", width)
        print(f"seal {width}: {size / 1024:.0f} KB")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
