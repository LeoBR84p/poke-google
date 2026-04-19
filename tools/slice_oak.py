"""Slice tools/profOak-source.png into 12 individual cell PNGs.

Run once after updating the source grid:
    python tools/slice_oak.py

Output:
    public/cells/oak_0.png  ...  public/cells/oak_11.png
Each cell ends up ~150 KB (resized to 50%) so the chat page loads
fast on mobile and every cell can be a regular static asset served
by the CDN — no canvas / crop math / FastAPI rewrites needed.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "profOak-source.png"
OUT = ROOT / "public" / "cells"
COLS, ROWS = 4, 3
RESIZE = 0.5  # half native cell resolution is plenty for the UI size


def main() -> None:
    img = Image.open(SRC)
    cw, ch = img.width // COLS, img.height // ROWS
    target = (int(cw * RESIZE), int(ch * RESIZE))
    for i in range(COLS * ROWS):
        c, r = i % COLS, i // COLS
        cell = img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
        cell = cell.resize(target, Image.LANCZOS)
        path = OUT / f"oak_{i}.png"
        cell.save(path, optimize=True)
        print(f"wrote {path} ({path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
