#!/usr/bin/env python3
"""
LiveWire ANSI Snapshot Card Viewer
Renders the 3D clay matcap viewport card in full 24-bit truecolor Unicode half-blocks.
"""

import sys
from pathlib import Path
from PIL import Image
import numpy as np

def display_card(img_path: Path, title: str = "LIVEWIRE STUDY ENGINE: CLAY MATCAP TWIN", w: int = 48, h: int = 16):
    if not img_path.exists():
        print(f"Error: Preview file not found at {img_path}")
        sys.exit(1)

    im = Image.open(img_path)
    resized = im.resize((w, h * 2), Image.Resampling.LANCZOS)
    arr = np.array(resized)

    purple = "\x1b[1;35m"
    white = "\x1b[1;37m"
    dim = "\x1b[38;2;170;170;190m"
    reset = "\x1b[0m"

    border_top = "┌" + "─" * (w + 2) + "┐"
    border_mid = "├" + "─" * (w + 2) + "┤"
    border_bot = "└" + "─" * (w + 2) + "┘"

    header_title = f"{title[:w-2]}"
    sub_title = f"Session: testing/testing  | Verts: 98,306 | FOV: 25°"

    print(f"{purple}{border_top}{reset}")
    print(f"{purple}│ {white}{header_title:<{w}} {purple}│{reset}")
    print(f"{purple}│ {dim}{sub_title:<{w}} {purple}│{reset}")
    print(f"{purple}{border_mid}{reset}")

    for y in range(0, h * 2, 2):
        row = f"{purple}│ {reset}"
        for x in range(w):
            r1, g1, b1 = arr[y, x][:3]
            r2, g2, b2 = arr[y+1, x][:3] if y+1 < h * 2 else (16, 17, 24)
            row += f"\x1b[38;2;{r1};{g1};{b1}m\x1b[48;2;{r2};{g2};{b2}m▀"
        row += f"{reset}{purple} │{reset}"
        print(row)

    print(f"{purple}{border_bot}{reset}")

if __name__ == "__main__":
    default_preview = Path("Projects/3drealms/engines/study_engine/studies/testing/testing/snapshots/chkpt_001_preview.png")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default_preview
    display_card(target)
