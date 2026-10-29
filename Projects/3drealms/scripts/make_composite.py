from PIL import Image, ImageDraw, ImageFont
import os

files = [
    ("pass1_direct_zero_bounce.png", "Pass 1: Direct Illum (0 Bounces)"),
    ("pass2_screen_raytracing_one_bounce.png", "Pass 2: Screen-Space Raytracing (1 Bounce)"),
    ("pass3_multi_bounce_fast_gi.png", "Pass 3: Multi-Bounce Fast GI (3 Bounces)"),
    ("pass4_irradiance_probe_volume_flood.png", "Pass 4: Light Probe Volume Flood"),
    ("pass5_volumetric_fog_godrays.png", "Pass 5: Volumetric Fog & God Rays")
]

base_dir = "/home/kidlucrid/Projects/3drealms/renders/lighting_tests"
imgs = []
for fname, title in files:
    fpath = os.path.join(base_dir, fname)
    im = Image.open(fpath).resize((640, 360), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(im)
    # Draw title banner
    draw.rectangle([0, 0, 640, 32], fill=(12, 10, 18, 220))
    draw.text((12, 8), title, fill=(240, 240, 255))
    imgs.append(im)

# Grid layout: 3 on top, 2 on bottom (centered)
grid_w = 640 * 3
grid_h = 360 * 2
canvas = Image.new("RGB", (grid_w, grid_h), (8, 6, 12))

# Row 1 (Pass 1, 2, 3)
canvas.paste(imgs[0], (0, 0))
canvas.paste(imgs[1], (640, 0))
canvas.paste(imgs[2], (1280, 0))

# Row 2 (Pass 4, 5 centered)
canvas.paste(imgs[3], (320, 360))
canvas.paste(imgs[4], (960, 360))

composite_path = os.path.join(base_dir, "lighting_passes_composite.png")
canvas.save(composite_path, quality=95)
print(f"Saved composite to {composite_path}")
