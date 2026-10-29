#!/usr/bin/env python3
"""
run_cone_radiance_pipeline.py
Orchestrates rendering frames with Blender and stitching them into high-quality GIFs with PIL.
"""

import subprocess
import os
import sys
import glob
from PIL import Image

def main():
    print("==========================================================")
    print(">>> LAUNCHING CONE TYPE RADIANCE PIPELINE (BLENDER 5.4) <<<")
    print("==========================================================")
    
    blender_script = "/home/kidlucrid/Projects/3drealms/scripts/render_cone_radiance_suite.py"
    cmd = ["blender", "-b", "-P", blender_script]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print("BLENDER ERROR:", res.stderr)
        sys.exit(res.returncode)
        
    print(">>> Stitching Turntable GIF...")
    turntable_frames = sorted(glob.glob("/tmp/cone_turntable_frames/frame_*.png"))
    if turntable_frames:
        images = [Image.open(p).convert("RGBA") for p in turntable_frames]
        # Quantize with palette for crisp GIF rendering
        quantized = [im.convert("P", palette=Image.ADAPTIVE, colors=256) for im in images]
        out_gif = "/home/kidlucrid/Projects/3drealms/renders/cone_radiance_turntable.gif"
        quantized[0].save(
            out_gif,
            save_all=True,
            append_images=quantized[1:],
            duration=80,
            loop=0,
            optimize=True
        )
        print(f">>> [SUCCESS] Turntable GIF created: {out_gif} ({os.path.getsize(out_gif)//1024} KB, {len(images)} frames)")
    else:
        print("ERROR: No turntable frames found!")

    print(">>> Stitching Auric Pulse GIF...")
    pulse_frames = sorted(glob.glob("/tmp/cone_pulse_frames/frame_*.png"))
    if pulse_frames:
        images = [Image.open(p).convert("RGBA") for p in pulse_frames]
        quantized = [im.convert("P", palette=Image.ADAPTIVE, colors=256) for im in images]
        out_gif = "/home/kidlucrid/Projects/3drealms/renders/cone_radiance_auric_pulse.gif"
        quantized[0].save(
            out_gif,
            save_all=True,
            append_images=quantized[1:],
            duration=75,
            loop=0,
            optimize=True
        )
        print(f">>> [SUCCESS] Auric Pulse GIF created: {out_gif} ({os.path.getsize(out_gif)//1024} KB, {len(images)} frames)")
    else:
        print("ERROR: No pulse frames found!")

if __name__ == "__main__":
    main()
