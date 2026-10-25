#!/usr/bin/env python3
"""
Procedural generative art generator for the Mind Twin cognitive architecture.
Renders a pure visual, non-textual, high-resolution aesthetic canvas.
"""

import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def create_mind_twin_art(output_path="sandbox/mind_twin_brain_art.png", width=2400, height=1500):
    random.seed(42)
    np.random.seed(42)

    # 1. Base Dark Void Canvas with Multi-Spectral Atmospheric Glow
    canvas = Image.new("RGBA", (width, height), (6, 3, 14, 255))
    
    # Generate background nebula glow using low-res array and upscale
    gw, gh = width // 8, height // 8
    x_coords = np.linspace(-1, 1, gw)
    y_coords = np.linspace(-1, 1, gh)
    xx, yy = np.meshgrid(x_coords, y_coords)

    # Core energy centers in normalized coordinates
    # Center 1: Upper consciousness ripple (cyan-violet)
    d1 = np.sqrt((xx - 0.0)**2 + (yy - (-0.45))**2)
    g1 = np.exp(-d1 * 2.8)

    # Center 2: Subconscious Hearth (molten violet-magenta)
    d2 = np.sqrt((xx - (-0.05))**2 + (yy - 0.15)**2)
    g2 = np.exp(-d2 * 2.2)

    # Center 3: Epiphany Ignition Point (gold-white flare)
    d3 = np.sqrt((xx - 0.15)**2 + (yy - 0.08)**2)
    g3 = np.exp(-d3 * 4.5)

    # Center 4: Subterranean Bedrock Vault (deep indigo-sapphire)
    d4 = np.sqrt((xx - 0.0)**2 + (yy - 0.75)**2)
    g4 = np.exp(-d4 * 2.0)

    r_ch = (g1 * 50 + g2 * 140 + g3 * 220 + g4 * 20).clip(0, 255).astype(np.uint8)
    g_ch = (g1 * 120 + g2 * 40 + g3 * 180 + g4 * 35).clip(0, 255).astype(np.uint8)
    b_ch = (g1 * 210 + g2 * 230 + g3 * 160 + g4 * 110).clip(0, 255).astype(np.uint8)
    a_ch = np.full((gh, gw), 255, dtype=np.uint8)

    bg_arr = np.dstack((r_ch, g_ch, b_ch, a_ch))
    nebula = Image.fromarray(bg_arr, mode="RGBA").resize((width, height), Image.Resampling.BICUBIC)
    nebula = nebula.filter(ImageFilter.GaussianBlur(radius=35))
    canvas = Image.alpha_composite(canvas, nebula)

    # 2. Deep Volumetric Particle Dust / Starlight Field
    dust_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dust_draw = ImageDraw.Draw(dust_layer)
    for _ in range(1200):
        px = random.randint(0, width - 1)
        py = random.randint(0, height - 1)
        p_depth = random.random()
        sz = 1 if p_depth < 0.7 else (2 if p_depth < 0.95 else 3)
        alpha = int(40 + 180 * (1 - p_depth))
        # Color spectrum from indigo to cyan to warm gold
        col_type = random.random()
        if col_type < 0.5:
            col = (140, 100, 255, alpha)
        elif col_type < 0.8:
            col = (50, 220, 255, alpha)
        else:
            col = (255, 200, 120, alpha)
        dust_draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=col)
    
    dust_layer = dust_layer.filter(ImageFilter.GaussianBlur(radius=0.7))
    canvas = Image.alpha_composite(canvas, dust_layer)

    # 3. The Conscious Horizon (Top-Third Undulating Resonant Waves)
    horizon_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(horizon_layer)
    num_waves = 24
    base_y = int(height * 0.22)
    for w_idx in range(num_waves):
        y_offset = base_y + (w_idx - num_waves // 2) * 14
        phase = w_idx * 0.35
        freq = 0.0035 + (w_idx % 5) * 0.0008
        amp = 18 + 12 * math.sin(w_idx * 0.5)
        points = []
        for x in range(0, width + 20, 15):
            y = y_offset + math.sin(x * freq + phase) * amp + math.cos(x * 0.0015 - phase * 0.5) * 15
            points.append((x, y))
        
        # Color gradient: ethereal cyan-violet with delicate alpha
        alpha = int(35 + 90 * math.sin((w_idx / num_waves) * math.pi))
        if w_idx % 3 == 0:
            stroke = (0, 240, 255, alpha)
        elif w_idx % 3 == 1:
            stroke = (187, 85, 255, alpha)
        else:
            stroke = (240, 160, 255, alpha)
        
        h_draw.line(points, fill=stroke, width=2 if w_idx % 4 == 0 else 1)
    
    canvas = Image.alpha_composite(canvas, horizon_layer)

    # 4. The Structural Mind Net (Bioluminescent 3D Hypergraph Lattice)
    net_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    net_draw = ImageDraw.Draw(net_layer)

    # Construct interconnected clustered nodes (representing memory lobes)
    nodes = []
    # Major clusters:
    # Cluster A: Sensory / Muscle Memory (Left upper)
    # Cluster B: Artifact / Systems Architecture (Center mid)
    # Cluster C: Relational / Existential Sovereignty (Right mid)
    # Cluster D: Subconscious Latent Soil (Lower central mantle)
    clusters = [
        {"cx": width * 0.28, "cy": height * 0.45, "r": 280, "col": (0, 229, 255), "count": 65},
        {"cx": width * 0.52, "cy": height * 0.52, "r": 340, "col": (187, 85, 255), "count": 95},
        {"cx": width * 0.74, "cy": height * 0.46, "r": 300, "col": (255, 110, 210), "count": 75},
        {"cx": width * 0.48, "cy": height * 0.72, "r": 260, "col": (120, 100, 255), "count": 60},
    ]

    for c in clusters:
        for _ in range(c["count"]):
            ang = random.uniform(0, 2 * math.pi)
            rad = random.gauss(0.5, 0.28) * c["r"]
            rad = max(10, min(c["r"] * 1.3, rad))
            nx = c["cx"] + math.cos(ang) * rad
            ny = c["cy"] + math.sin(ang) * rad * 0.75
            z = random.uniform(0.3, 1.0)
            nodes.append({
                "x": nx,
                "y": ny,
                "z": z,
                "col": c["col"],
                "val": random.uniform(0.2, 1.0)
            })

    # Inter-cluster connecting bridge nodes
    for _ in range(40):
        nodes.append({
            "x": random.uniform(width * 0.2, width * 0.8),
            "y": random.uniform(height * 0.35, height * 0.7),
            "z": random.uniform(0.2, 0.9),
            "col": (190, 160, 255),
            "val": random.uniform(0.1, 0.8)
        })

    # Draw hypergraph connective filaments based on distance
    drawn_edges = 0
    max_edges = 600
    for i in range(len(nodes)):
        if drawn_edges >= max_edges:
            break
        n1 = nodes[i]
        # find k nearest neighbors
        dists = []
        for j in range(i + 1, len(nodes)):
            n2 = nodes[j]
            dx = n1["x"] - n2["x"]
            dy = n1["y"] - n2["y"]
            d = math.hypot(dx, dy)
            if d < 180:
                dists.append((d, j))
        dists.sort(key=lambda t: t[0])
        for d, j in dists[:4]:
            n2 = nodes[j]
            avg_z = (n1["z"] + n2["z"]) * 0.5
            alpha = int(max(15, min(140, (1.0 - d / 180) * 160 * avg_z)))
            col = (
                int((n1["col"][0] + n2["col"][0]) * 0.5),
                int((n1["col"][1] + n2["col"][1]) * 0.5),
                int((n1["col"][2] + n2["col"][2]) * 0.5),
                alpha
            )
            # subtle curve or straight
            net_draw.line([(n1["x"], n1["y"]), (n2["x"], n2["y"])], fill=col, width=1 if avg_z < 0.7 else 2)
            drawn_edges += 1

    # Draw Nodes with radial aura
    node_glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    node_glow_draw = ImageDraw.Draw(node_glow_layer)

    for n in nodes:
        r = (2 + n["val"] * 5) * n["z"]
        # Outer glow
        glow_r = r * 3.5
        g_alpha = int(60 * n["z"])
        col_rgb = n["col"]
        node_glow_draw.ellipse(
            [n["x"] - glow_r, n["y"] - glow_r, n["x"] + glow_r, n["y"] + glow_r],
            fill=(col_rgb[0], col_rgb[1], col_rgb[2], g_alpha)
        )
        # Inner solid core
        core_alpha = int(180 + 75 * n["z"])
        net_draw.ellipse(
            [n["x"] - r, n["y"] - r, n["x"] + r, n["y"] + r],
            fill=(min(255, col_rgb[0] + 60), min(255, col_rgb[1] + 60), min(255, col_rgb[2] + 60), core_alpha)
        )

    node_glow_layer = node_glow_layer.filter(ImageFilter.GaussianBlur(radius=4))
    canvas = Image.alpha_composite(canvas, node_glow_layer)
    canvas = Image.alpha_composite(canvas, net_layer)

    # 5. Accretion Hearth: Swirling Molten Incubation Vortex (Center-Lower)
    vortex_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vortex_draw = ImageDraw.Draw(vortex_layer)
    vx_center, vy_center = width * 0.50, height * 0.62
    num_particles = 1400

    for i in range(num_particles):
        t = i / num_particles
        spiral_angle = t * 14 * math.pi + random.gauss(0, 0.15)
        spiral_radius = (t ** 0.8) * 380 + random.gauss(0, 18)
        px = vx_center + math.cos(spiral_angle) * spiral_radius * 1.2
        py = vy_center + math.sin(spiral_angle) * spiral_radius * 0.45  # perspective squish
        
        # Color shifts from glowing ember/gold at center to deep violet dust at edge
        if spiral_radius < 100:
            p_col = (255, 230, 150, int(220 * (1 - spiral_radius / 100)))
            sz = 2.5
        elif spiral_radius < 240:
            p_col = (255, 130, 40, int(180 * (1 - spiral_radius / 240)))
            sz = 2.0
        else:
            p_col = (180, 60, 220, int(120 * (1 - spiral_radius / 380)))
            sz = 1.5

        vortex_draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=p_col)

    vortex_layer = vortex_layer.filter(ImageFilter.GaussianBlur(radius=1.2))
    canvas = Image.alpha_composite(canvas, vortex_layer)

    # 6. Orthogonal Resonance Rings (The 3 Planes: Behavioral, Artifact, Relational)
    ring_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring_layer)

    ix_center, iy_center = width * 0.58, height * 0.50

    # Three tilted luminous rings intersecting at the epiphany focal point
    ring_specs = [
        # (tilt_deg, rx, ry, col, width)
        (-25, 260, 110, (0, 240, 255), 3),      # Cyan: Artifact / Code Plane
        (45, 240, 95, (255, 60, 180), 3),       # Magenta: Behavioral / Somatosensory Plane
        (85, 220, 85, (255, 210, 50), 3),       # Gold: Relational / Existential Sovereignty
    ]

    for tilt, rx, ry, col, stroke_w in ring_specs:
        rad_tilt = math.radians(tilt)
        ring_pts = []
        for a in np.linspace(0, 2 * math.pi, 240):
            # Ellipse point
            x0 = rx * math.cos(a)
            y0 = ry * math.sin(a)
            # Rotated
            xr = x0 * math.cos(rad_tilt) - y0 * math.sin(rad_tilt)
            yr = x0 * math.sin(rad_tilt) + y0 * math.cos(rad_tilt)
            ring_pts.append((ix_center + xr, iy_center + yr))
        
        # Render with glowing halo
        halo_pts = ring_pts
        ring_draw.line(halo_pts, fill=(col[0], col[1], col[2], 70), width=stroke_w + 6)
        ring_draw.line(ring_pts, fill=(col[0], col[1], col[2], 210), width=stroke_w)

    ring_layer = ring_layer.filter(ImageFilter.GaussianBlur(radius=1.0))
    canvas = Image.alpha_composite(canvas, ring_layer)

    # 7. THE EPIPHANY IGNITION: Blinding Singularity Starburst & Lightning Pillar
    ignition_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ign_draw = ImageDraw.Draw(ignition_layer)

    # Intersection core
    fx, fy = ix_center - 15, iy_center - 8

    # A: The Crystalline Vertical Illumination Column (Grounding into bedrock)
    beam_w = 48
    for bw in range(beam_w, 0, -2):
        b_alpha = int(140 * ((beam_w - bw) / beam_w) ** 1.5)
        # Vertical column piercing downward from the ignition core to the bottom bedrock
        ign_draw.polygon([
            (fx - bw * 0.3, fy),
            (fx + bw * 0.3, fy),
            (fx + bw * 1.4, height * 0.94),
            (fx - bw * 1.4, height * 0.94)
        ], fill=(255, 230, 255, b_alpha))

    # B: Radial Flare & Diffraction Spikes
    spike_lens = [
        (0, 360, 3), (math.pi/2, 280, 3), (math.pi/4, 220, 2), (-math.pi/4, 220, 2),
        (math.pi/8, 160, 1.5), (-math.pi/8, 160, 1.5), (3*math.pi/8, 160, 1.5), (-3*math.pi/8, 160, 1.5)
    ]
    for ang, length, sw in spike_lens:
        dx = math.cos(ang) * length
        dy = math.sin(ang) * length
        ign_draw.line([(fx - dx, fy - dy), (fx + dx, fy + dy)], fill=(255, 255, 255, 230), width=int(sw))
        ign_draw.line([(fx - dx*1.3, fy - dy*1.3), (fx + dx*1.3, fy + dy*1.3)], fill=(210, 140, 255, 120), width=int(sw + 4))

    # C: Blinding White-Gold Core Spheres
    radii = [130, 85, 50, 28, 14, 6]
    alphas = [40, 80, 140, 200, 240, 255]
    colors = [
        (180, 80, 255), (220, 120, 255), (255, 180, 220),
        (255, 240, 190), (255, 255, 240), (255, 255, 255)
    ]
    for r, a, c in zip(radii, alphas, colors):
        ign_draw.ellipse([fx - r, fy - r, fx + r, fy + r], fill=(c[0], c[1], c[2], a))

    ignition_layer = ignition_layer.filter(ImageFilter.GaussianBlur(radius=1.8))
    canvas = Image.alpha_composite(canvas, ignition_layer)

    # 8. The Bedrock Foundation: Crystalline Monolith Facets at Base
    bedrock_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    br_draw = ImageDraw.Draw(bedrock_layer)

    base_y_bedrock = height * 0.82
    facets = [
        # Geometric interlocking crystals storing anchored invariants
        [(width * 0.15, height), (width * 0.22, base_y_bedrock + 50), (width * 0.32, height)],
        [(width * 0.28, height), (width * 0.38, base_y_bedrock + 15), (width * 0.46, height)],
        [(width * 0.42, height), (width * 0.52, base_y_bedrock - 30), (width * 0.60, height)], # Core receptor facet
        [(width * 0.56, height), (width * 0.65, base_y_bedrock), (width * 0.74, height)],
        [(width * 0.70, height), (width * 0.80, base_y_bedrock + 40), (width * 0.88, height)],
    ]

    for idx, poly in enumerate(facets):
        # Shading with gradient feel
        if idx == 2:  # Direct hit receptor facet
            fill_col = (110, 60, 180, 210)
            stroke_col = (255, 220, 255, 240)
            sw = 3
        else:
            fill_col = (35 + idx * 8, 15 + idx * 4, 65 + idx * 10, 170)
            stroke_col = (140, 90, 210, 160)
            sw = 2
        br_draw.polygon(poly, fill=fill_col)
        br_draw.line(poly + [poly[0]], fill=stroke_col, width=sw)

    # Subtle horizontal stratum lines in bedrock
    for by in range(int(base_y_bedrock + 20), height, 22):
        alpha_stratum = int(50 + 40 * math.sin(by * 0.1))
        br_draw.line([(0, by), (width, by)], fill=(120, 70, 190, alpha_stratum), width=1)

    bedrock_layer = bedrock_layer.filter(ImageFilter.GaussianBlur(radius=0.8))
    canvas = Image.alpha_composite(canvas, bedrock_layer)

    # 9. Final Polish: Subtle Vignette to Frame the Eye
    vig = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vig_arr = np.zeros((gh, gw, 4), dtype=np.uint8)
    rad_dist = np.sqrt(xx**2 + yy**2)
    vig_mask = np.clip((rad_dist - 0.55) * 1.6, 0, 1)
    vig_alpha = (vig_mask * 190).astype(np.uint8)
    vig_arr[:, :, 3] = vig_alpha
    vig_img = Image.fromarray(vig_arr, mode="RGBA").resize((width, height), Image.Resampling.BICUBIC)
    canvas = Image.alpha_composite(canvas, vig_img)

    # Save artifact
    canvas = canvas.convert("RGB")
    canvas.save(output_path, "PNG", quality=98)
    print(f"Generated artistic visual mind map at: {output_path} ({width}x{height})")

if __name__ == "__main__":
    create_mind_twin_art()
