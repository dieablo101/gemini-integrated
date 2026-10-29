#!/usr/bin/env python3
"""
Nomad Link Live Bridge & Multi-Engine Study Daemon
--------------------------------------------------
Connects directly to Nomad Sculpt via Nomad Link wire protocol.
Performs:
1. Real-time Sculpting Process Telemetry (mesh_delta, mesh_attributes, sculpt_layers, camera orbit tracking)
2. Automated Headless Multi-Engine Intake:
   - Blender Headless: FBX & GLB generation, 12-angle turntable orthographic renders, lighting passes, curvature
   - Godot Headless: Kinetic envelope, bounding volume, convex hull reduction, collision metrics
   - 3DRealms Perception Engine: Mass distribution, symmetry, palette decomposition
"""

import os
import sys
import time
import math
import json
import struct
import argparse
import subprocess
import threading
from pathlib import Path

# Add nomad-link examples to path
NOMAD_LINK_DIR = Path(__file__).resolve().parents[3] / "nomad-link" / "examples"
if str(NOMAD_LINK_DIR) not in sys.path:
    sys.path.append(str(NOMAD_LINK_DIR))

try:
    import transport
except ImportError:
    transport = None

DEFAULT_HOST = "192.168.1.38"
DEFAULT_PORT = 48312
TOKEN_FILE = Path.home() / ".nomad_link_token"

STUDY_ENGINE_DIR = Path(__file__).resolve().parent
MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "nomad_intake"

CAPABILITIES = [
    "camera", "mesh_full", "mesh_attributes", "sculpt_layers", "mesh_delta",
    "mesh_delta_receive", "mesh_attributes_receive", "mesh_instance", "ngon",
    "hierarchy", "scene_batch", "skew", "selection_transfer", "scene_transfer",
    "scene_edits", "object_state", "material", "light", "camera_object",
    "session_config", "shading_config", "postprocess_config", "texture", "asset"
]

def get_saved_token() -> str:
    if TOKEN_FILE.exists():
        try:
            return TOKEN_FILE.read_text().strip()
        except Exception:
            pass
    # Fallback to the known approved token
    return "0616eb7d-f173-4de0-969c-578dbfb1b9edf8a98263-2053-4ad9-8aee-10cf3ab0f94d"

def save_token(token: str):
    try:
        TOKEN_FILE.write_text(token)
    except Exception as e:
        print(f"[Bridge] Warning: Failed to write token file: {e}")

class SculptSessionTelemetry:
    """Tracks live sculpting strokes, delta deformations, camera angles, and layering."""
    def __init__(self, sculpt_id: str, output_dir: Path):
        self.sculpt_id = sculpt_id
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.telemetry_path = self.output_dir / "sculpt_process_telemetry.json"
        
        self.start_time = time.time()
        self.stroke_count = 0
        self.total_delta_vertices = 0
        self.max_stroke_displacement = 0.0
        self.strokes = []
        self.layer_history = []
        self.camera_vantage_history = []
        self.current_mesh_state = {}
        self.last_save_time = time.time()

    def record_delta(self, header: dict, binary: bytes):
        now = time.time()
        self.stroke_count += 1
        vert_count = int(header.get("count", 0))
        self.total_delta_vertices += vert_count
        
        displacement = 0.0
        if binary and len(binary) >= vert_count * 12:
            # Estimate displacement magnitude from packed float3 vectors
            try:
                import numpy as np
                displacements = np.frombuffer(binary[:vert_count * 12], dtype="<f4").reshape(-1, 3)
                mags = np.linalg.norm(displacements, axis=1)
                displacement = float(np.max(mags)) if len(mags) > 0 else 0.0
            except Exception:
                pass
                
        self.max_stroke_displacement = max(self.max_stroke_displacement, displacement)
        
        stroke_entry = {
            "stroke_id": self.stroke_count,
            "timestamp": round(now - self.start_time, 2),
            "modified_vertices": vert_count,
            "max_displacement": round(displacement, 4),
            "mesh_id": header.get("mesh_id", "")[:8]
        }
        self.strokes.append(stroke_entry)
        
        # Periodic auto-flush every 5 seconds
        if now - self.last_save_time > 5.0:
            self.flush()

    def record_camera(self, header: dict):
        now = time.time()
        # Sample camera movements (throttle to max 2/sec)
        if self.camera_vantage_history and (now - self.camera_vantage_history[-1]["t"] < 0.5):
            return
            
        entry = {
            "t": round(now - self.start_time, 2),
            "fov": header.get("fov_y", 0),
            "matrix": header.get("world_matrix", [])
        }
        self.camera_vantage_history.append(entry)
        if len(self.camera_vantage_history) > 500:
            self.camera_vantage_history.pop(0)

    def record_layer(self, header: dict):
        self.layer_history.append({
            "timestamp": round(time.time() - self.start_time, 2),
            "event": header.get("type"),
            "data": header
        })
        self.flush()

    def flush(self):
        data = {
            "sculpt_id": self.sculpt_id,
            "session_duration_seconds": round(time.time() - self.start_time, 1),
            "stroke_count": self.stroke_count,
            "total_delta_vertices": self.total_delta_vertices,
            "max_stroke_displacement": round(self.max_stroke_displacement, 4),
            "strokes_recent": self.strokes[-100:],  # keep last 100 in file
            "layer_events": len(self.layer_history),
            "camera_samples": len(self.camera_vantage_history)
        }
        try:
            with open(self.telemetry_path, "w") as f:
                json.dump(data, f, indent=2)
            self.last_save_time = time.time()
        except Exception as e:
            print(f"[Telemetry] Save error: {e}")

class NomadLiveBridge:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.token = get_saved_token()
        self.conn = None
        self.active_mesh_data = None
        self.active_mesh_header = None
        self.telemetry = None
        self.running = False

    def connect(self, timeout=10.0) -> bool:
        if transport is None:
            raise RuntimeError("transport.py not available in nomad-link/examples")
            
        print(f"[Bridge] Connecting to Nomad Link at {self.host}:{self.port}...")
        self.conn = transport.Connection(client_name="Gemini Studio & Perception Bridge", capabilities=CAPABILITIES)
        self.conn.connect(self.host, self.port, self.token, transport.VERSION, 1)
        
        start = time.time()
        while time.time() - start < timeout:
            for header, binary in self.conn.poll():
                kind = header.get("type")
                if kind == "pairing_pending":
                    print("[Bridge] Awaiting pairing approval on Nomad...")
                elif kind == "hello":
                    new_token = header.get("pair_token")
                    if new_token:
                        self.token = new_token
                        save_token(new_token)
                    print(f"[Bridge] Connected! Nomad Version: {header.get('nomad_version', 'Unknown')}")
                    return True
                elif kind == "error":
                    print(f"[Bridge] Error from Nomad: {header.get('message')}")
                    return False
            time.sleep(0.1)
        return False

    def request_and_pull_mesh(self, timeout=10.0) -> bool:
        print("[Bridge] Requesting complete 3D scene from Nomad...")
        self.conn.send({"type": "request_scene"})
        
        start = time.time()
        while time.time() - start < timeout:
            for header, binary in self.conn.poll():
                kind = header.get("type")
                if kind == "mesh_full":
                    self.active_mesh_header = header
                    self.active_mesh_data = binary
                    name = header.get("name", "NomadSculpt")
                    vert_count = header.get("vertex_count", 0)
                    face_count = header.get("face_count", 0)
                    print(f"[Bridge] Received mesh '{name}' with {vert_count:,} vertices, {face_count:,} faces ({len(binary):,} bytes)")
                    return True
            time.sleep(0.05)
        print("[Bridge] Timed out waiting for mesh_full.")
        return False

    def export_intermediate_json(self, target_dir: Path) -> Path:
        """Extracts positions, faces, and vertex colors into numpy arrays and writes JSON."""
        import numpy as np
        h = self.active_mesh_header
        b = self.active_mesh_data
        
        vert_count = int(h["vertex_count"])
        face_count = int(h["face_count"])
        
        # Read vertices (float3)
        pos_offset = int(h.get("position_offset", 0))
        positions = np.frombuffer(b[pos_offset : pos_offset + vert_count * 12], dtype="<f4").reshape(-1, 3)
        
        # Read faces
        faces = []
        if h.get("face_format") == "corners":
            corner_count = int(h.get("corner_count", 0))
            face_size_offset = int(h.get("face_size_offset", 0))
            corner_vert_offset = int(h.get("corner_vertex_offset", 0))
            face_sizes = np.frombuffer(b[face_size_offset : face_size_offset + face_count * 4], dtype="<i4")
            corner_verts = np.frombuffer(b[corner_vert_offset : corner_vert_offset + corner_count * 4], dtype="<i4")
            idx = 0
            for sz in face_sizes:
                faces.append(corner_verts[idx : idx + sz].tolist())
                idx += sz
        else:
            face_offset = int(h.get("face_offset", 0))
            raw_faces = np.frombuffer(b[face_offset : face_offset + face_count * 16], dtype="<i4").reshape(-1, 4)
            for f in raw_faces:
                if f[3] >= 0:
                    faces.append([int(f[0]), int(f[1]), int(f[2]), int(f[3])])
                else:
                    faces.append([int(f[0]), int(f[1]), int(f[2])])
                    
        # Read vertex colors if available
        colors = None
        color_offset = h.get("base_color_offset")
        color_format = h.get("base_color_format")
        if color_offset is not None and color_format == "rgb8":
            raw_cols = np.frombuffer(b[color_offset : color_offset + vert_count * 3], dtype=np.uint8).reshape(-1, 3)
            colors = (raw_cols / 255.0).astype(np.float32).tolist()
            
        mesh_name = h.get("name", "sculpt").replace(" ", "_").lower()
        sculpt_payload = {
            "sculpt_id": mesh_name,
            "vertices": positions.tolist(),
            "faces": faces,
            "colors": colors,
            "vertex_count": vert_count,
            "face_count": face_count
        }
        
        target_dir.mkdir(parents=True, exist_ok=True)
        intermediate_path = target_dir / f"{mesh_name}_raw.json"
        with open(intermediate_path, "w") as f:
            json.dump(sculpt_payload, f)
            
        print(f"[Bridge] Staged raw mesh JSON ({vert_count:,} verts) -> {intermediate_path}")
        return intermediate_path

    def run_multi_engine_pipeline(self, raw_json_path: Path, output_dir: Path) -> dict:
        """Executes Blender Headless, Godot Headless, and Study Engine across the asset."""
        print("\n" + "=" * 65)
        print("  LAUNCHING MULTI-ENGINE STUDY & RENDER PIPELINE")
        print("=" * 65)
        
        # 1. Blender Headless Studio Run (FBX, GLB, 12 Ortho Renders)
        print("\n[Stage 1/3] Blender Headless Studio Rig...")
        blender_cmd = [
            "/home/kidlucrid/.local/bin/blender",
            "--background",
            "--python", str(STUDY_ENGINE_DIR / "blender_study_rig.py"),
            "--",
            str(raw_json_path),
            str(output_dir)
        ]
        res = subprocess.run(blender_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            print(f"[Blender] Error running studio rig:\n{res.stderr[-500:]}")
        else:
            print("[Blender] Studio rig complete! 12 orthographic turntable renders & FBX/GLB generated.")

        # Locate generated GLB
        sculpt_id = raw_json_path.stem.replace("_raw", "")
        glb_path = output_dir / f"{sculpt_id}.glb"
        fbx_path = output_dir / f"{sculpt_id}.fbx"
        
        # 2. Godot Headless Holodeck Ingestion
        print("\n[Stage 2/3] Godot 4.8 Headless Holodeck Rig...")
        if glb_path.exists():
            godot_cmd = [
                "/home/kidlucrid/.local/bin/godot",
                "--headless",
                "--script", str(STUDY_ENGINE_DIR / "godot_study_rig.gd"),
                "--",
                "--glb", str(glb_path),
                "--out", str(output_dir)
            ]
            gres = subprocess.run(godot_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if gres.returncode != 0:
                print(f"[Godot] Warning: {gres.stderr[-300:]}")
            else:
                print("[Godot] Kinetic envelope & collision geometry analyzed.")
        else:
            print(f"[Godot] GLB not found at {glb_path}, skipping Godot stage.")

        # 3. 3DRealms Perception Study Engine
        print("\n[Stage 3/3] 3DRealms Perception & Measurement Engine...")
        study_engine_script = STUDY_ENGINE_DIR / "sculpt_study_engine.py"
        engine_cmd = [
            sys.executable,
            str(study_engine_script),
            "--json", str(raw_json_path),
            "--out", str(output_dir)
        ]
        eres = subprocess.run(engine_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(eres.stdout)

        # Aggregate master dossier
        master_dossier = {
            "sculpt_id": sculpt_id,
            "timestamp": time.time(),
            "source": f"Nomad Link ({self.host}:{self.port})",
            "fbx_path": str(fbx_path) if fbx_path.exists() else None,
            "glb_path": str(glb_path) if glb_path.exists() else None,
        }
        
        for name in ["blender_study.json", "godot_study.json", "sculpt_study_results.json"]:
            p = output_dir / name
            if p.exists():
                try:
                    with open(p) as f:
                        master_dossier[name.replace(".json", "")] = json.load(f)
                except Exception:
                    pass

        dossier_path = output_dir / "master_study_dossier.json"
        with open(dossier_path, "w") as f:
            json.dump(master_dossier, f, indent=2)
            
        print("\n" + "=" * 65)
        print(f"  STUDY COMPLETE -> Master Dossier: {dossier_path}")
        print("=" * 65)
        return master_dossier

    def monitor_live_sculpting(self, sculpt_id="active_sculpt"):
        """Continuous listener for live stroke deltas, layer edits, and camera viewpoints."""
        out_dir = MODELS_DIR / sculpt_id
        self.telemetry = SculptSessionTelemetry(sculpt_id, out_dir)
        print(f"\n[LiveMonitor] Telemetry active for '{sculpt_id}'")
        print(f"[LiveMonitor] Listening for stroke deltas, layering, and camera vantage points...")
        print("[LiveMonitor] Sculpt freely on your iPad. Press Ctrl+C to snapshot and finish.\n")
        
        self.running = True
        last_heartbeat = time.time()
        try:
            while self.running:
                for header, binary in self.conn.poll():
                    kind = header.get("type")
                    if kind == "mesh_delta":
                        self.telemetry.record_delta(header, binary)
                        print(f"  -> [Stroke #{self.telemetry.stroke_count}] Deformed {header.get('count')} vertices (Max Disp: {self.telemetry.max_stroke_displacement:.3f})")
                    elif kind == "camera":
                        self.telemetry.record_camera(header)
                    elif kind in ("sculpt_layers", "mesh_attributes"):
                        self.telemetry.record_layer(header)
                        print(f"  -> [Layer/Paint Event] {kind}")
                    elif kind == "error":
                        print(f"[LiveMonitor] Remote error: {header.get('message')}")
                        
                # Heartbeat ping every 10 seconds
                if time.time() - last_heartbeat > 10.0:
                    self.conn.send({"type": "ping"})
                    last_heartbeat = time.time()
                    
                time.sleep(0.02)
        except KeyboardInterrupt:
            print("\n[LiveMonitor] Stopping live session listener...")
        finally:
            if self.telemetry:
                self.telemetry.flush()
                print(f"[LiveMonitor] Session flushed: {self.telemetry.stroke_count} strokes logged.")

def main():
    parser = argparse.ArgumentParser(description="Nomad Link Multi-Engine Bridge & Telemetry")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Nomad IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Nomad Link port")
    parser.add_argument("--action", choices=["intake", "monitor", "both"], default="intake", help="Action to execute")
    parser.add_argument("--name", default="alien1", help="Sculpt project name")
    args = parser.parse_args()

    bridge = NomadLiveBridge(host=args.host, port=args.port)
    if not bridge.connect():
        print("[Bridge] Failed to connect.")
        sys.exit(1)

    output_dir = MODELS_DIR / args.name

    if args.action in ("intake", "both"):
        if bridge.request_and_pull_mesh():
            raw_path = bridge.export_intermediate_json(output_dir)
            bridge.run_multi_engine_pipeline(raw_path, output_dir)
            
    if args.action in ("monitor", "both"):
        bridge.monitor_live_sculpting(args.name)

    if bridge.conn:
        bridge.conn.disconnect()

if __name__ == "__main__":
    main()
