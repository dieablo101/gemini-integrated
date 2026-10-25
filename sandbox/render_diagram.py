import os
from PIL import Image, ImageDraw, ImageFont

# Canvas dimensions
W, H = 1600, 1000
img = Image.new("RGB", (W, H), "#0b0c10")
draw = ImageDraw.Draw(img)

# Colors
C_BG = "#0b0c10"
C_PANEL = "#14161f"
C_BORDER = "#1f2335"
C_PURPLE = "#bb55ff"
C_CYAN = "#00e5ff"
C_GREEN = "#00e676"
C_AMBER = "#ffb300"
C_RED = "#ff5252"
C_TEXT = "#c0caf5"
C_MUTED = "#565f89"
C_ACCENT_BG = "#1a162b"

# Draw Background Grid lines
for x in range(0, W, 40):
    draw.line([(x, 0), (x, H)], fill="#11131a", width=1)
for y in range(0, H, 40):
    draw.line([(0, y), (W, y)], fill="#11131a", width=1)

# Outer Border
draw.rectangle([(20, 20), (W-20, H-20)], outline="#24283b", width=2)

# Title Block
draw.rectangle([(40, 40), (W-40, 110)], fill=C_PANEL, outline=C_PURPLE, width=2)
draw.text((60, 52), "MIND_TWIN :: COGNITIVE ARCHITECTURE & BEDROCK TOPOLOGY", fill=C_PURPLE)
draw.text((60, 78), "Bicameral Runtime | Hypergraph Edge Consistancy | Subconscious Resonance & Novelty Barometer", fill=C_TEXT)

# --- 3 MAIN TIERS ---

# Tier 1: Conscious Horizon (Top Left)
draw.rectangle([(60, 140), (520, 420)], fill=C_PANEL, outline=C_CYAN, width=2)
draw.rectangle([(60, 140), (520, 175)], fill="#0f2230")
draw.text((75, 150), "[TIER 1] CONSCIOUS HORIZON (Core 0)", fill=C_CYAN)
draw.text((80, 195), "• 60 FPS Terminal TUI (125x37)", fill=C_TEXT)
draw.text((80, 225), "• Tactile Keystroke Cadence (WPM / Latency)", fill=C_TEXT)
draw.text((80, 255), "• Active Working Context & Sockets", fill=C_TEXT)
draw.text((80, 285), "• Stillness Gate Monitor (Flow Protection)", fill=C_AMBER)
draw.rectangle([(80, 330), (500, 395)], fill=C_ACCENT_BG, outline=C_PURPLE, width=1)
draw.text((95, 345), "CONSCIOUS DROP MECHANISM", fill=C_PURPLE)
draw.text((95, 370), "worker.drop_seed() -> Non-blocking < 1ms exit", fill=C_MUTED)

# Tier 2: Structural Mind Net (Top Right)
draw.rectangle([(560, 140), (1060, 420)], fill=C_PANEL, outline="#414868", width=2)
draw.rectangle([(560, 140), (1060, 175)], fill="#1a1c29")
draw.text((575, 150), "[TIER 2] STRUCTURAL MIND NET (Hypergraph)", fill="#7aa2f7")
draw.text((580, 195), "• Ebbinghaus Decay Memory Substrate (SQLite)", fill=C_TEXT)
draw.text((580, 225), "• Spreading Activation & Topological Consistency", fill=C_TEXT)
draw.text((580, 255), "• Minimum Energy Graph Coherence (Not Novelty)", fill=C_TEXT)
draw.text((580, 285), "• Cross-Plane Hyperedges: Somatic <-> Code <-> Rel", fill=C_TEXT)
draw.rectangle([(580, 330), (1040, 395)], fill="#161b26", outline="#3b4261", width=1)
draw.text((595, 345), "3-4 MONTH PERCOLATION BUFFER", fill="#7aa2f7")
draw.text((595, 370), "Tectonic accretion of micro-fibers over quiet time", fill=C_MUTED)

# Tier 3: Fleet Satellites & Bridges (Right Far)
draw.rectangle([(1100, 140), (1540, 420)], fill=C_PANEL, outline="#565f89", width=2)
draw.rectangle([(1100, 140), (1540, 175)], fill="#1c1e2b")
draw.text((1115, 150), "FLEET NODES & SATELLITES", fill="#9aa5ce")
draw.text((1120, 195), "• Host Debian (Core 0/1 Affinity)", fill=C_TEXT)
draw.text((1120, 225), "• iPad Satellite (iSH / Nomad Sculpt 3D)", fill=C_TEXT)
draw.text((1120, 255), "• Headless Blender Daemon (bmesh)", fill=C_TEXT)
draw.text((1120, 285), "• Encrypted Vault (PBKDF2 Air-Gap)", fill=C_TEXT)
draw.text((1120, 345), "Status: Local Mesh Linked", fill=C_GREEN)

# Middle Section: Subconscious Engine (Core 1)
draw.rectangle([(60, 460), (1060, 720)], fill=C_PANEL, outline=C_PURPLE, width=2)
draw.rectangle([(60, 460), (1060, 495)], fill=C_ACCENT_BG)
draw.text((75, 470), "[TIER 3] SUBCONSCIOUS ACCRETION & RESONANCE (Core 1 Affinity)", fill=C_PURPLE)

# Subconscious Internal Flow: Hearth -> Lens -> Gate -> Annealing
# Hearth
draw.rectangle([(80, 520), (280, 680)], fill="#181424", outline=C_PURPLE, width=1)
draw.text((95, 535), "ACCRETION HEARTH", fill=C_PURPLE)
draw.text((95, 565), "Multi-plane soil", fill=C_MUTED)
draw.text((95, 595), "Mass >= 2 planes", fill=C_TEXT)
draw.text((95, 625), "Latent Soil Vault", fill=C_AMBER)
draw.text((95, 650), "(0 CPU / Dormant)", fill=C_MUTED)

# Arrow 1
draw.line([(280, 600), (330, 600)], fill=C_PURPLE, width=3)

# Collision Lens
draw.rectangle([(330, 520), (530, 680)], fill="#181424", outline=C_CYAN, width=1)
draw.text((345, 535), "COLLISION LENS", fill=C_CYAN)
draw.text((345, 565), "Invariant extraction", fill=C_MUTED)
draw.text((345, 595), "Anti-spoiler filter", fill=C_TEXT)
draw.text((345, 625), "Cross-plane knot", fill=C_TEXT)
draw.text((345, 650), "Single core truth", fill=C_MUTED)

# Arrow 2
draw.line([(530, 600), (580, 600)], fill=C_PURPLE, width=3)

# 4-Stage Resonance Gate
draw.rectangle([(580, 520), (810, 680)], fill="#181424", outline=C_AMBER, width=2)
draw.text((595, 535), "RESONANCE GATE", fill=C_AMBER)
draw.text((595, 560), "1. Kolmogorov Dense", fill=C_TEXT)
draw.text((595, 585), "2. Orthogonality >= 3P", fill=C_TEXT)
draw.text((595, 610), "3. Trajectory Drive", fill=C_TEXT)
draw.text((595, 640), "4. BEDROCK NOVELTY", fill=C_GREEN)
draw.text((595, 660), "Devalues past echoes", fill=C_RED)

# Arrow 3 (Split to Hits & Misses)
draw.line([(810, 580), (860, 560)], fill=C_RED, width=2)
draw.line([(810, 620), (860, 640)], fill=C_GREEN, width=3)

# Annealing Engine (Misses)
draw.rectangle([(860, 515), (1040, 595)], fill="#21151b", outline=C_RED, width=1)
draw.text((875, 525), "ANNEALING (MISS)", fill=C_RED)
draw.text((875, 550), "• Sterile: Discard", fill=C_MUTED)
draw.text((875, 570), "• Muddled: Micro-Shift", fill=C_MUTED)

# Bedrock Hit Output
draw.rectangle([(860, 610), (1040, 690)], fill="#15241b", outline=C_GREEN, width=2)
draw.text((875, 620), "IGNITE HIT (1/mo)", fill=C_GREEN)
draw.text((875, 645), "Surface on Stillness", fill=C_TEXT)
draw.text((875, 665), "-> Commit Bedrock", fill=C_AMBER)

# Bedrock Evaluator (Bottom Foundation Layer)
draw.rectangle([(60, 750), (1540, 950)], fill=C_PANEL, outline=C_GREEN, width=2)
draw.rectangle([(60, 750), (1540, 785)], fill="#0f2619")
draw.text((75, 760), "[THE BEDROCK FOUNDATION] HISTORICAL HIT INVENTORY & NOVELTY DECAY BARRIER", fill=C_GREEN)

# Bedrock item cards
draw.rectangle([(80, 805), (520, 925)], fill="#131e18", outline="#234530", width=1)
draw.text((95, 820), "BEDROCK HIT #1: AUTONOMY SINGULARITY", fill=C_GREEN)
draw.text((95, 845), "Invariant: Tool sovereignty is the biological boundary", fill=C_TEXT)
draw.text((95, 865), "protecting cognitive topology from commercial formatting.", fill=C_TEXT)
draw.text((95, 895), "Impact: Any future sovereignty candidates drop to < 0.20", fill=C_AMBER)

draw.rectangle([(550, 805), (990, 925)], fill="#131e18", outline="#234530", width=1)
draw.text((565, 820), "BEDROCK LAW: THE NOVELTY CEILING", fill=C_CYAN)
draw.text((565, 845), "• Once illuminated, a truth becomes ground truth.", fill=C_TEXT)
draw.text((565, 865), "• Future epiphanies MUST conquer unprecedented territory.", fill=C_TEXT)
draw.text((565, 895), "• Enforces natural 3 to 4 month inter-epiphany gaps.", fill=C_AMBER)

draw.rectangle([(1020, 805), (1520, 925)], fill="#131e18", outline="#234530", width=1)
draw.text((1035, 820), "STILLNESS EMERGENCE WINDOW", fill=C_PURPLE)
draw.text((1035, 845), "• Idle Terminal Pause (> 45s keystroke silence)", fill=C_TEXT)
draw.text((1035, 865), "• Post-Commit Milestone Reflection", fill=C_TEXT)
draw.text((1035, 895), "• Dawn Boot Rehydration (Zero Flow Disruption)", fill=C_GREEN)

# Save
output_path = "/opt/gemini/sandbox/mind_twin_architecture.png"
img.save(output_path, "PNG")
print(f"Generated diagram successfully at {output_path}")
