#!/usr/bin/env python3
"""
Grim DAW Engine & REAPER Audio Pipeline Tool
Standalone Digital Audio Workstation bridge, batch stem renderer,
and procedural manifest generator for Grim DAW and connected engines.
"""

import sys
import os
import json
import subprocess
import argparse
from pathlib import Path

# Resolve REAPER binary
REAPER_BIN = os.path.expanduser("~/.local/bin/reaper")
if not os.path.exists(REAPER_BIN):
    REAPER_BIN = "/opt/REAPER/reaper"
if not os.path.exists(REAPER_BIN):
    import shutil
    which_reaper = shutil.which("reaper")
    if which_reaper:
        REAPER_BIN = which_reaper

# Path resolution hierarchy
GRIM_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRIM_ASSETS = GRIM_ROOT / "stems"
DEFAULT_GAMES_ASSETS = Path("/home/kidlucrid/Projects/dieablo/assets/audio/grim")


def get_default_assets_dir() -> Path:
    """Prioritizes ~/Projects/grim/stems, falling back to game assets if configured."""
    if DEFAULT_GRIM_ASSETS.exists():
        return DEFAULT_GRIM_ASSETS
    if DEFAULT_GAMES_ASSETS.exists():
        return DEFAULT_GAMES_ASSETS
    return GRIM_ROOT / "stems"


def inspect_environment():
    print("=" * 60)
    print("GRIM STANDALONE DAW & AUDIO PIPELINE INSPECTOR")
    print("=" * 60)
    print(f"Grim Workspace: {GRIM_ROOT}")
    assets_dir = get_default_assets_dir()
    print(f"Active Output:  {assets_dir}")

    if os.path.exists(REAPER_BIN):
        print(f"[✓] Cockos REAPER binary found: {REAPER_BIN}")
        try:
            res = subprocess.run([REAPER_BIN, "-help"], capture_output=True, text=True, timeout=5)
            first_line = res.stdout.strip().split("\n")[0] if res.stdout else "Available"
            print(f"[✓] REAPER CLI Ready: {first_line}")
        except Exception as e:
            print(f"[!] Warning checking reaper: {e}")
    else:
        print(f"[✗] REAPER binary not found at {REAPER_BIN}")

    fx_dir = "/opt/REAPER/Plugins/FX"
    if os.path.exists(fx_dir):
        plugins = [f for f in os.listdir(fx_dir) if f.endswith(".so")]
        print(f"[✓] Stock Cockos VST/ReaPlugs detected ({len(plugins)} found):")
        for p in sorted(plugins)[:8]:
            print(f"    • {p}")
        if len(plugins) > 8:
            print(f"    ... and {len(plugins) - 8} more.")

    print("=" * 60)


def generate_rpp_project(theme_name: str, bpm: float = 120.0, output_path: str = None, target_dir: str = None):
    if not output_path:
        templates_dir = GRIM_ROOT / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(templates_dir / f"{theme_name}.rpp")

    dest_dir = Path(target_dir) if target_dir else get_default_assets_dir()
    stem_render_path = dest_dir / theme_name / "stem_$track.wav"

    rpp_content = f"""<REAPER_PROJECT 0.1 "7.83/linux-x86_64"
  SAMPLERATE 44100 0 0
  TEMPO {bpm:.6f} 4 4
  <RENDER_CFG
    ZXZhdgEAAAA=
  >
  RENDER_FILE "{stem_render_path}"
  RENDER_RANGE 1 0.0 16.0 0 0
  <TRACK {{11111111-0000-0000-0000-000000000001}}
    NAME "ambient"
    PEAKCOL 16576
    VOLPAN 1.0 0 0 -1
  >
  <TRACK {{22222222-0000-0000-0000-000000000002}}
    NAME "bass"
    PEAKCOL 32768
    VOLPAN 1.0 0 0 -1
  >
  <TRACK {{33333333-0000-0000-0000-000000000003}}
    NAME "drums"
    PEAKCOL 65535
    VOLPAN 1.0 0 0 -1
  >
  <TRACK {{44444444-0000-0000-0000-000000000004}}
    NAME "lead"
    PEAKCOL 255
    VOLPAN 1.0 0 0 -1
  >
>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rpp_content)

    print(f"[✓] Generated REAPER project template: {output_path} (BPM: {bpm})")
    return output_path


def generate_manifest(theme_name: str, bpm: float = 120.0, beats_per_bar: int = 4, target_dir: str = None):
    manifest_dir = Path(target_dir) if target_dir else (GRIM_ROOT / "manifests")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = manifest_dir / f"{theme_name}.json"

    manifest = {
        "theme_name": theme_name,
        "bpm": bpm,
        "beats_per_bar": beats_per_bar,
        "loop_start_bar": 1,
        "loop_end_bar": 17,
        "stems": {
            "ambient": f"stems/{theme_name}/ambient.ogg",
            "bass": f"stems/{theme_name}/bass.ogg",
            "drums": f"stems/{theme_name}/drums.ogg",
            "lead": f"stems/{theme_name}/lead.ogg"
        }
    }

    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[✓] Emitted Grim manifest: {manifest_file}")
    return str(manifest_file)


def render_project(rpp_path: str):
    if not os.path.exists(rpp_path):
        print(f"[✗] Error: File not found: {rpp_path}")
        return False

    print(f"[*] Invoking headless REAPER render on: {rpp_path} ...")
    cmd = [REAPER_BIN, "-nosplash", "-renderproject", rpp_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"[✓] REAPER render finished with exit code {res.returncode}")
        return res.returncode == 0
    except Exception as e:
        print(f"[✗] REAPER render failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Grim DAW REAPER Bridge & Stem Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("inspect", help="Inspect DAW install, REAPER & VST plugins")

    gen_p = subparsers.add_parser("create-project", help="Create REAPER project template")
    gen_p.add_argument("theme_name", help="Theme name (e.g. sanctuary_depths)")
    gen_p.add_argument("--bpm", type=float, default=120.0, help="Theme BPM")
    gen_p.add_argument("--out", type=str, default=None, help="Output .rpp path")
    gen_p.add_argument("--target-dir", type=str, default=None, help="Target audio directory")

    man_p = subparsers.add_parser("manifest", help="Generate Grim JSON manifest")
    man_p.add_argument("theme_name", help="Theme name")
    man_p.add_argument("--bpm", type=float, default=120.0, help="Theme BPM")
    man_p.add_argument("--target-dir", type=str, default=None, help="Target manifest directory")

    ren_p = subparsers.add_parser("render", help="Render a REAPER project headlessly")
    ren_p.add_argument("rpp_file", help="Path to .rpp project")

    args = parser.parse_args()

    if args.command == "inspect" or not args.command:
        inspect_environment()
    elif args.command == "create-project":
        generate_rpp_project(args.theme_name, args.bpm, args.out, getattr(args, "target_dir", None))
    elif args.command == "manifest":
        generate_manifest(args.theme_name, args.bpm, target_dir=getattr(args, "target_dir", None))
    elif args.command == "render":
        render_project(args.rpp_file)


if __name__ == "__main__":
    main()
