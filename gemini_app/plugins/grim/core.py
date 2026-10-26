"""Core audio engine implementation for Grim DAW."""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
from typing import Any, Dict, List, Optional
import wave


@dataclass
class GrimStemConfig:
    name: str
    volume_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    solo: bool = False


@dataclass
class GrimProjectManifest:
    theme_name: str
    bpm: float = 120.0
    time_signature: str = "4/4"
    beats_per_bar: int = 4
    total_bars: int = 8
    stems: List[str] = field(default_factory=lambda: ["ambient", "bass", "drums", "lead"])
    created_by: str = "Grim DAW (gemini-integrated)"


class GrimEngine:
    """Unified DAW engine conductor for gemini-integrated and external audio workspaces."""

    DEFAULT_REAPER_PATHS = [
        "/usr/local/bin/reaper",
        os.path.expanduser("~/.local/bin/reaper"),
        "/opt/REAPER/reaper",
    ]

    STANDALONE_WORKSPACE_CANDIDATES = [
        Path(os.path.expanduser("~/Projects/grim")),
        Path("/opt/grim"),
    ]

    GAMES_WORKSPACE_CANDIDATES = [
        Path(os.path.expanduser("~/Projects/games/scripts/grim")),
        Path(os.path.expanduser("~/Projects/games")),
    ]

    def __init__(self, reaper_path: Optional[str] = None):
        self._reaper_bin = self._resolve_reaper_binary(reaper_path)
        self._workspace_path, self._workspace_type = self._resolve_workspace()
        self._bridge_script = self._resolve_bridge_script()

    def _resolve_workspace(self) -> tuple[Optional[Path], str]:
        """Resolves active Grim audio workspace with strict priority hierarchy:
        1. Standalone DAW workspace (~/Projects/grim)
        2. In-game audio scripts (~/Projects/games/scripts/grim)
        3. Embedded standard-library fallback
        """
        for candidate in self.STANDALONE_WORKSPACE_CANDIDATES:
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve(), "standalone"
        for candidate in self.GAMES_WORKSPACE_CANDIDATES:
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve(), "games"
        return None, "embedded"

    def _resolve_bridge_script(self) -> Optional[Path]:
        """Finds grim_reaper DAW bridge script adhering to workspace priority."""
        if self._workspace_path:
            # 1. Standalone tools
            t1 = self._workspace_path / "tools" / "grim_reaper.py"
            if t1.exists():
                return t1.resolve()
            # 2. Standalone root
            t2 = self._workspace_path / "grim_reaper.py"
            if t2.exists():
                return t2.resolve()
        # Fallback check games
        for candidate in self.GAMES_WORKSPACE_CANDIDATES:
            t3 = candidate / "grim_reaper.py"
            if t3.exists():
                return t3.resolve()
        return None

    @property
    def workspace_path(self) -> Optional[Path]:
        return self._workspace_path

    @property
    def workspace_type(self) -> str:
        return self._workspace_type

    @property
    def bridge_script(self) -> Optional[Path]:
        return self._bridge_script

    def _resolve_reaper_binary(self, custom_path: Optional[str] = None) -> Optional[str]:

        if custom_path and os.path.exists(custom_path):
            return custom_path
        which_reaper = shutil.which("reaper")
        if which_reaper and os.path.exists(which_reaper):
            return which_reaper
        for p in self.DEFAULT_REAPER_PATHS:
            if os.path.exists(p):
                return p
        return None

    @property
    def reaper_path(self) -> Optional[str]:
        return self._reaper_bin

    @property
    def is_reaper_available(self) -> bool:
        return self._reaper_bin is not None and os.path.exists(self._reaper_bin)

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry of Grim DAW environment."""
        plugins: List[str] = []
        fx_dir = Path("/opt/REAPER/Plugins/FX")
        if fx_dir.exists():
            plugins = sorted([f.name for f in fx_dir.glob("*.so")])

        reaper_ver = "Unknown"
        if self.is_reaper_available and self._reaper_bin:
            try:
                res = subprocess.run([self._reaper_bin, "-help"], capture_output=True, text=True, timeout=5)
                first_line = (res.stdout or "").strip().split("\n")[0]
                reaper_ver = first_line or "Cockos REAPER CLI"
            except Exception as e:
                reaper_ver = f"Available ({e})"

        return {
            "daw": "Grim Audio Subsystem",
            "workspace_type": self._workspace_type,
            "workspace_path": str(self._workspace_path) if self._workspace_path else None,
            "bridge_script": str(self._bridge_script) if self._bridge_script else None,
            "reaper_available": self.is_reaper_available,
            "reaper_binary": self._reaper_bin,
            "reaper_version": reaper_ver,
            "stock_fx_count": len(plugins),
            "stock_fx": plugins,
            "default_sample_rate": 44100,
            "supported_formats": ["wav", "ogg", "flac"],
        }

    def create_project_template(
        self,
        name: str,
        output_rpp: str,
        bpm: float = 120.0,
        beats_per_bar: int = 4,
        bars: int = 8,
        stems: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generates a multi-track REAPER Project (.rpp) configured for stem rendering."""
        stems = stems or ["ambient", "bass", "drums", "lead"]
        seconds_per_beat = 60.0 / max(20.0, bpm)
        total_duration = seconds_per_beat * beats_per_bar * bars
        out_path = Path(output_rpp).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        tracks_rpp: List[str] = []
        for idx, stem in enumerate(stems, start=1):
            guid = f"{idx:08d}-0000-0000-0000-{idx:012d}"
            tracks_rpp.append(
                f"""  <TRACK {{{guid}}}
    NAME "{stem}"
    PEAKCOL 16576
    BEAT -1
    AUTOMODE 0
    VOLPAN 1.00000000000000 0.00000000000000 -1 -1 1
    MUTESOLO 0 0 0
    IPHASE 0
    ISBUS 0 0
    BUSCOMP 0 0 0 0 0
    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0
    REC 0 0 0 0 0 0 0 0
    VU 2
    TRACKHEIGHT 0 0 0 0 0 0
    INQ 0 0 0 0.5 100 0 0 100
    NCHAN 2
    FX 1
    TRACKID {{{guid}}}
    PERF 0
    MIDIOUT -1
    MAINSEND 1 0
  >"""
            )

        rpp_content = f"""<REAPER_PROJECT 0.1 "7.83/linux-x86_64"
  SAMPLERATE 44100 0 0
  TEMPO {bpm:.6f} {beats_per_bar} 4
  <RENDER_CFG
    ZXZhdgEAAAA=
  >
  RENDER_FILE "{out_path.parent}/stems/{name}/stem_$track.wav"
  RENDER_RANGE 1 0.0 {total_duration:.3f} 0 0
{os.linesep.join(tracks_rpp)}
>
"""
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rpp_content)

        manifest = {
            "name": name,
            "bpm": bpm,
            "beats_per_bar": beats_per_bar,
            "bars": bars,
            "duration_seconds": round(total_duration, 4),
            "stems": stems,
            "rpp_path": str(out_path),
        }
        manifest_path = out_path.parent / f"{name}_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        return {
            "status": "success",
            "project_name": name,
            "rpp_path": str(out_path),
            "manifest_path": str(manifest_path),
            "bpm": bpm,
            "duration": total_duration,
            "stems": stems,
        }

    def render_project_headless(self, rpp_path: str) -> Dict[str, Any]:
        """Renders an .rpp project headlessly using REAPER batch processor."""
        if not self.is_reaper_available or not self._reaper_bin:
            return {"status": "error", "message": "REAPER binary not found in environment."}

        target = Path(rpp_path).resolve()
        if not target.exists():
            return {"status": "error", "message": f"RPP file not found: {target}"}

        cmd = [self._reaper_bin, "-nosplash", "-renderproject", str(target)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return {
                "status": "success" if res.returncode == 0 else "error",
                "return_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "rpp_path": str(target),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def synthesize_dsp_sample(
        self,
        output_wav: str,
        kind: str = "impact",
        duration: float = 0.5,
        freq: float = 440.0,
        sample_rate: int = 44100,
    ) -> Dict[str, Any]:
        """Synthesizes procedural wave audio without external asset files."""
        out_path = Path(output_wav).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        total_samples = int(sample_rate * duration)
        samples = []

        for i in range(total_samples):
            t = float(i) / sample_rate
            val = 0.0
            if kind == "impact":
                # 65Hz heavy bass thump with exponential decay
                env = math.exp(-t * 14.0)
                pitch = 65.0 * (1.0 + math.exp(-t * 30.0) * 1.5)
                val = math.sin(2.0 * math.pi * pitch * t) * env
            elif kind == "slash":
                # Frequency sweep 880Hz down to 220Hz with soft band noise
                env = math.exp(-t * 9.0)
                pitch = 220.0 + (660.0 * math.exp(-t * 16.0))
                val = math.sin(2.0 * math.pi * pitch * t) * env
            elif kind == "parry":
                # High resonant steel ping (1420Hz + 2360Hz)
                env = math.exp(-t * 6.5)
                val = (
                    0.6 * math.sin(2.0 * math.pi * 1420.0 * t)
                    + 0.4 * math.sin(2.0 * math.pi * 2360.0 * t)
                ) * env
            elif kind == "drone":
                # Low 55Hz subterranean ambient drone
                env = 0.8
                lfo = 0.5 + 0.5 * math.sin(2.0 * math.pi * 0.25 * t)
                val = math.sin(2.0 * math.pi * 55.0 * t) * env * (0.8 + 0.2 * lfo)
            else:
                # Standard sine wave
                env = math.exp(-t * 3.0)
                val = math.sin(2.0 * math.pi * freq * t) * env

            clamped = max(-1.0, min(1.0, val * 0.85))
            samples.append(int(clamped * 32767.0))

        with wave.open(str(out_path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(struct.pack(f"<{len(samples)}h", *samples))

        return {
            "status": "success",
            "path": str(out_path),
            "kind": kind,
            "duration": duration,
            "sample_rate": sample_rate,
        }


grim_engine = GrimEngine()
