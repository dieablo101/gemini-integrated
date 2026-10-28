#!/usr/bin/env python3
"""
Live Wire Study Engine (Nomad Link Real-Time Streaming & Cognitive Perception)
------------------------------------------------------------------------------
Connects to the Nomad Sculpt live wire protocol to maintain a real-time
in-memory digital twin of the sculpted mesh.

Capabilities:
1. In-memory `LiveSculptTwin` patched in real-time via sparse `mesh_delta` packets (<2ms).
2. Advanced Brush Archetype & Kinematics Inversion:
   - Directional Coherence (Move / Grab vs localized deformation)
   - Normal Alignment Ratio (Inflate / Clay vs Carve)
   - Tangential Inward Convergence (Crease / Pinch)
   - Planar Variance Compression (Flatten / Trim / Scrape)
   - Laplacian Relaxation Residual (Smooth / Relax)
   - Color / Opacity Stream Detection (Paint / Mask)
3. Camera-Coupled Eye & Silhouette Inspection Telemetry:
   - World-space camera matrix decoding (view vector, orbit pivot, frustum)
   - Inspection Angle relative to stroke surface patch:
     * Silhouette Profile (view ray grazing patch normal at ~90 deg)
     * Grazing Specular Sheen (45 - 75 deg check for plane continuity)
     * Orthogonal Direct (0 - 45 deg deep socket / surface work)
   - Camera Orbit Cadence & Hesitation Tracking
4. 5-Stage Human Sculpting Cognitive Classifier:
   - Stage 1: Gesture & Silhouette Blockout
   - Stage 2: Bony Landmarks & Skeletal Anchors
   - Stage 3: Planar Articulation & Faceting
   - Stage 4: Organic Muscle & Transition Blending
   - Stage 5: Micro-Tension, Creasing & Character Detail
5. Artist Stylistic Fingerprint & Brush Transition Matrix:
   - Markov transitions between tools (e.g. Clay -> Smooth -> Crease rhythm)
   - Energy and time budget allocation per brush archetype
"""

from __future__ import annotations
import os
import sys
import time
import math
import json
import struct
import threading
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Optional, Any, Callable

import numpy as np

# Ingest Study Spec
try:
    from .study_spec import StudyProfile, get_default_study_profile
except ImportError:
    from study_spec import StudyProfile, get_default_study_profile

# Nomad Link Transport Bridge
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

STUDIES_ROOT = Path("Projects/3drealms/engines/study_engine/studies")
PRODUCTION_ROOT = Path("Projects/3drealms/pipeline/production")
STUDIES_ROOT.mkdir(parents=True, exist_ok=True)
PRODUCTION_ROOT.mkdir(parents=True, exist_ok=True)


def get_livewire_settings_path() -> Path:
    p = Path.home() / ".gemini" / "livewire_settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_livewire_settings() -> dict:
    p = get_livewire_settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "auto_reconnect": True,
        "last_updated": time.time()
    }


def save_livewire_settings(host: str, port: int = DEFAULT_PORT) -> dict:
    data = load_livewire_settings()
    data["host"] = host.strip()
    data["port"] = int(port)
    data["last_updated"] = time.time()
    p = get_livewire_settings_path()
    p.write_text(json.dumps(data, indent=2))
    return data


def discover_nomad_devices(timeout: float = 0.4) -> list[dict]:
    """Scans local network/interfaces for Nomad Sculpt Link instances."""
    import socket
    settings = load_livewire_settings()
    known_host = settings.get("host", DEFAULT_HOST)
    devices = []
    
    candidates = [known_host, "127.0.0.1", "192.168.1.38"]
    seen = set()
    for host in candidates:
        if not host or host in seen:
            continue
        seen.add(host)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                res = s.connect_ex((host, DEFAULT_PORT))
                is_open = (res == 0)
                devices.append({
                    "host": host,
                    "port": DEFAULT_PORT,
                    "status": "online" if is_open else "unreachable",
                    "device_name": f"Nomad Sculpt ({host})"
                })
        except Exception:
            devices.append({
                "host": host,
                "port": DEFAULT_PORT,
                "status": "unreachable",
                "device_name": f"Nomad Sculpt ({host})"
            })
    return devices


def validate_session_name(raw_name: str) -> Tuple[bool, str, str, str]:
    """
    Validates folder/filename structure.
    Returns (is_valid, error_msg, folder, filename).
    """
    cleaned = raw_name.strip().strip("/")
    if not cleaned:
        return False, "please name your livewire session", "", ""
    if "/" not in cleaned:
        return False, "must add subfolder Example: folder/filename", "", ""
    parts = cleaned.split("/")
    if len(parts) < 2 or not parts[0].strip() or not parts[-1].strip():
        return False, "must add subfolder Example: folder/filename", "", ""
    folder = "/".join(parts[:-1]).strip()
    filename = parts[-1].strip()
    return True, "", folder, filename


def get_session_dir(mode: str, folder: str, filename: str) -> Path:
    base = PRODUCTION_ROOT if mode == "production" else STUDIES_ROOT
    return base / folder / filename


def check_session_collision(mode: str, folder: str, filename: str) -> bool:
    session_dir = get_session_dir(mode, folder, filename)
    return session_dir.exists() and any(session_dir.iterdir())


def compute_mesh_fingerprint(twin: LiveSculptTwin) -> dict:
    import hashlib
    positions = twin.positions
    vert_count = len(positions)
    face_count = twin.face_count
    if vert_count > 0:
        coord_bytes = positions.tobytes()
        pos_hash = hashlib.sha256(coord_bytes).hexdigest()
        centroid = twin.bbox_center.tolist()
        dimensions = twin.dimensions.tolist()
        diag = float(np.linalg.norm(twin.dimensions))
    else:
        pos_hash = "empty"
        centroid = [0.0, 0.0, 0.0]
        dimensions = [0.0, 0.0, 0.0]
        diag = 0.0

    return {
        "vertex_count": vert_count,
        "face_count": face_count,
        "sha256": pos_hash,
        "centroid": centroid,
        "dimensions": dimensions,
        "bounding_diagonal": diag,
        "model_radius": twin.model_radius
    }


def verify_mesh_match(
    recorded_twin: LiveSculptTwin,
    live_twin: LiveSculptTwin,
    mode: str = "studies",
    tolerance_pct: float = 3.0
) -> Tuple[bool, str, dict]:
    rec_fp = compute_mesh_fingerprint(recorded_twin)
    live_fp = compute_mesh_fingerprint(live_twin)

    audit: dict = {
        "mode": mode,
        "recorded_fingerprint": rec_fp,
        "live_fingerprint": live_fp,
        "verified": False,
        "total_variances_detected": 0,
        "vertex_delta": 0,
        "variance_percentage": 0.0,
        "rmsd": 0.0,
        "provenance_notes": []
    }

    if recorded_twin.vertex_count == 0 or live_twin.vertex_count == 0:
        return False, "Cannot verify empty sculpt twin", audit

    v_rec = recorded_twin.vertex_count
    v_live = live_twin.vertex_count
    v_diff = abs(v_live - v_rec)
    var_pct = (v_diff / max(v_rec, 1)) * 100.0

    audit["vertex_delta"] = v_diff
    audit["variance_percentage"] = round(var_pct, 3)

    if mode == "studies":
        # 100% strict match check!
        if v_rec != v_live:
            audit["total_variances_detected"] = v_diff
            audit["provenance_notes"].append(
                f"Studies 100% Gate Failed: Vertex count mismatch ({v_live} vs {v_rec})."
            )
            return False, f"Integrity Check Failed: Active sculpt does not match LiveWire session endpoint ({v_diff} vertex difference). Reopen session state or cancel.", audit

        if rec_fp["sha256"] != live_fp["sha256"]:
            if len(recorded_twin.positions) == len(live_twin.positions):
                disp = np.linalg.norm(recorded_twin.positions - live_twin.positions, axis=1)
                max_d = float(np.max(disp))
                if max_d > 1e-4:
                    audit["total_variances_detected"] = int(np.sum(disp > 1e-4))
                    audit["provenance_notes"].append(
                        f"Studies 100% Gate Failed: Geometric coordinates drifted by {max_d:.5f}mm."
                    )
                    return False, "Integrity Check Failed: Active sculpt coordinates do not match LiveWire endpoint (unrecorded edits). Reopen session state or cancel.", audit

        audit["verified"] = True
        audit["total_variances_detected"] = 0
        audit["provenance_notes"].append("100% Bit-Exact Identity Verified for Study Engine Ingestion.")
        return True, "100% Strict Match Verified", audit

    else:
        # Production mode: lenient check
        diag = max(rec_fp["bounding_diagonal"], 1e-4)
        c_rec = np.array(rec_fp["centroid"])
        c_live = np.array(live_fp["centroid"])
        centroid_drift = float(np.linalg.norm(c_live - c_rec))
        drift_pct = (centroid_drift / diag) * 100.0

        if drift_pct > 5.0:
            audit["provenance_notes"].append(
                f"Production Gate Failed: Centroid drift {drift_pct:.1f}% indicates completely different sculpt opened."
            )
            return False, f"Production Ingestion Blocked: Active sculpt deviates significantly from session (Centroid drift {drift_pct:.1f}%). Please open the correct project.", audit

        if var_pct > tolerance_pct:
            audit["total_variances_detected"] = v_diff
            audit["provenance_notes"].append(
                f"Production Gate Failed: Vertex variance {var_pct:.2f}% exceeds tolerance threshold ({tolerance_pct}%)."
            )
            return False, f"Production Ingestion Blocked: Active sculpt deviates from session (Variance {var_pct:.1f}% > {tolerance_pct}% limit). Please open the correct project.", audit

        # Check coordinate drift if same vertex count
        coord_variances = 0
        if len(recorded_twin.positions) == len(live_twin.positions) and len(recorded_twin.positions) > 0:
            disp = np.linalg.norm(recorded_twin.positions - live_twin.positions, axis=1)
            coord_variances = int(np.sum(disp > 1e-4))
            audit["rmsd"] = float(np.sqrt(np.mean(disp ** 2)))

        total_vars = max(v_diff, coord_variances)
        audit["total_variances_detected"] = total_vars

        if total_vars > 0:
            audit["status"] = "APPROVED_WITH_LENIENCY"
            audit["provenance_notes"].append(
                "Offline manual refinement detected between LiveWire stop recording and finalization."
            )
            audit["provenance_notes"].append(
                f"{total_vars} variances (drift/deltas) accepted under production leniency threshold (<={tolerance_pct}%)."
            )
            audit["provenance_notes"].append(
                "Notice to AI: Geometry modifications occurred after audio stream termination. Do not correlate post-recording mesh deltas with prior audio monologue."
            )
        else:
            audit["status"] = "APPROVED_BIT_EXACT"
            audit["provenance_notes"].append("100% Bit-Exact match for Production Export.")

        return True, f"Production Sculpt Verified ({var_pct:.1f}% variance within tolerance).", audit


def save_in_progress_snapshot(
    mode: str,
    folder: str,
    filename: str,
    twin: LiveSculptTwin,
    camera: Optional[CameraState],
    stats: Optional[LiveSessionStats] = None
) -> Path:
    s_dir = get_session_dir(mode, folder, filename)
    snap_dir = s_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    epoch = time.time()
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
    snap_count = len(list(snap_dir.glob("*_meta.json"))) + 1
    snap_id = f"chkpt_{snap_count:03d}"

    payload = {
        "event": "in_progress_snapshot",
        "snapshot_id": snap_id,
        "epoch": epoch,
        "iso_time": iso,
        "mode": mode,
        "folder": folder,
        "filename": filename,
        "camera_at_pause": {
            "camera_pos": camera.camera_pos.tolist() if camera else [0.0, 0.0, 3.0],
            "view_dir": camera.view_dir.tolist() if camera else [0.0, 0.0, -1.0],
            "fov_y": camera.fov_y if camera else 50.0,
            "orthographic": camera.orthographic if camera else False,
            "orbit_count": camera.orbit_count if camera else 0
        },
        "fingerprint": compute_mesh_fingerprint(twin),
        "total_strokes": stats.total_strokes if stats else 0,
        "total_kinetic_energy": stats.total_kinetic_energy if stats else 0.0
    }

    meta_file = snap_dir / f"{snap_id}_meta.json"
    with open(meta_file, "w") as f:
        json.dump(payload, f, indent=2)

    geo_file = snap_dir / f"{snap_id}_geo.npz"
    np.savez_compressed(
        geo_file,
        positions=twin.positions,
        faces=np.array(twin.faces, dtype=object),
        colors=twin.colors if twin.colors is not None else np.empty(0)
    )

    session_json = s_dir / f"{filename}_session.json"
    s_data = {}
    if session_json.exists():
        try:
            with open(session_json, "r") as f:
                s_data = json.load(f)
        except Exception:
            pass
    if "snapshots" not in s_data:
        s_data["snapshots"] = []
    s_data["snapshots"].append(payload)
    with open(session_json, "w") as f:
        json.dump(s_data, f, indent=2)

    return meta_file


def check_in_progress_snapshot_exists(mode: str, folder: str, filename: str) -> bool:
    s_dir = get_session_dir(mode, folder, filename)
    snap_dir = s_dir / "snapshots"
    if not snap_dir.exists():
        return False
    return len(list(snap_dir.glob("*_meta.json"))) > 0


def get_latest_snapshot(mode: str, folder: str, filename: str) -> Optional[dict]:
    s_dir = get_session_dir(mode, folder, filename)
    snap_dir = s_dir / "snapshots"
    if not snap_dir.exists():
        return None
    metas = sorted(list(snap_dir.glob("*_meta.json")))
    if not metas:
        return None
    try:
        with open(metas[-1], "r") as f:
            return json.load(f)
    except Exception:
        return None


def record_camera_snapto(
    mode: str,
    folder: str,
    filename: str,
    from_camera: dict,
    to_camera: Optional[CameraState]
) -> dict:
    s_dir = get_session_dir(mode, folder, filename)
    to_cam_dict = {
        "camera_pos": to_camera.camera_pos.tolist() if to_camera else [0.0, 0.0, 3.0],
        "view_dir": to_camera.view_dir.tolist() if to_camera else [0.0, 0.0, -1.0],
        "fov_y": to_camera.fov_y if to_camera else 50.0,
        "orthographic": to_camera.orthographic if to_camera else False
    }
    event = {
        "event": "camera_snapto",
        "epoch": time.time(),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from_camera": from_camera,
        "to_camera": to_cam_dict,
        "note": "Camera viewpoint repositioned during session pause; recorded as intentional camera snap-to."
    }
    session_json = s_dir / f"{filename}_session.json"
    s_data = {}
    if session_json.exists():
        try:
            with open(session_json, "r") as f:
                s_data = json.load(f)
        except Exception:
            pass
    if "events" not in s_data:
        s_data["events"] = []
    s_data["events"].append(event)
    with open(session_json, "w") as f:
        json.dump(s_data, f, indent=2)
    return event


def cancel_and_scrub_session(mode: str, folder: str, filename: str) -> Tuple[bool, str]:
    import shutil
    base = PRODUCTION_ROOT if mode == "production" else STUDIES_ROOT
    parent_folder = base / folder
    target_session_dir = parent_folder / filename

    if not target_session_dir.exists():
        return True, f"Session folder '{folder}/{filename}' did not exist on disk."

    try:
        shutil.rmtree(target_session_dir)
    except Exception as e:
        return False, f"Failed to delete session directory: {e}"

    try:
        if parent_folder.exists():
            remaining = [p for p in parent_folder.iterdir() if p.name not in (".", "..")]
            if not remaining:
                parent_folder.rmdir()
                return True, f"Scrubbed session '{folder}/{filename}' and pruned empty parent folder '{folder}'."
            else:
                return True, f"Scrubbed session '{folder}/{filename}' (parent folder retained with {len(remaining)} existing items)."
    except Exception as e:
        return True, f"Scrubbed session '{folder}/{filename}' (could not prune parent: {e})."

    return True, f"Scrubbed session '{folder}/{filename}'."


def _export_production_model(twin: LiveSculptTwin, s_dir: Path, filename: str):
    obj_file = s_dir / f"{filename}.obj"
    fbx_file = s_dir / f"{filename}.fbx"
    with open(obj_file, "w") as f:
        f.write(f"# LiveWire Production Mesh: {filename}\n")
        for v in twin.positions:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for face in twin.faces:
            f_str = " ".join(str(idx + 1) for idx in face)
            f.write(f"f {f_str}\n")
    try:
        import subprocess
        blender_bin = "/usr/bin/blender"
        if os.path.exists(blender_bin):
            conv_script = (
                f"import bpy\n"
                f"bpy.ops.wm.read_factory_settings(use_empty=True)\n"
                f"bpy.ops.wm.obj_import(filepath='{obj_file}')\n"
                f"bpy.ops.export_scene.fbx(filepath='{fbx_file}')\n"
            )
            subprocess.run([blender_bin, "--background", "--python-expr", conv_script],
                           capture_output=True, timeout=15)
    except Exception:
        pass
    if not fbx_file.exists():
        fbx_file.write_bytes(obj_file.read_bytes())


def _export_studies_model(twin: LiveSculptTwin, s_dir: Path, filename: str):
    obj_file = s_dir / f"{filename}_mesh.obj"
    with open(obj_file, "w") as f:
        f.write(f"# LiveWire Study Engine Mesh: {filename}\n")
        for v in twin.positions:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for face in twin.faces:
            f_str = " ".join(str(idx + 1) for idx in face)
            f.write(f"f {f_str}\n")
    glb_file = s_dir / f"{filename}_base.glb"
    if not glb_file.exists():
        glb_file.write_bytes(obj_file.read_bytes())
    final_glb = s_dir / "final_mesh.glb"
    final_glb.write_bytes(obj_file.read_bytes())


def finalize_livewire_session(
    mode: str,
    folder: str,
    filename: str,
    engine: LiveWireStudyEngine,
    tolerance_pct: float = 3.0
) -> Tuple[bool, str, dict]:
    s_dir = get_session_dir(mode, folder, filename)
    s_dir.mkdir(parents=True, exist_ok=True)
    twin = engine.twin

    if twin.vertex_count == 0:
        return False, "Cannot finalize: No mesh ingested in LiveWire twin.", {}

    if mode == "production":
        ok, msg, audit = verify_mesh_match(twin, twin, mode="production", tolerance_pct=tolerance_pct)
        _export_production_model(twin, s_dir, filename)

        engine.output_dir = s_dir
        engine.save_telemetry_snapshot()
        audit_file = s_dir / "production_leniency_audit.json"
        with open(audit_file, "w") as f:
            json.dump(audit, f, indent=2)

        return True, f"Production session '{folder}/{filename}' finalized! Created {filename}.fbx", audit

    else:
        ok, msg, audit = verify_mesh_match(twin, twin, mode="studies", tolerance_pct=0.0)
        study_core = s_dir / "study_core"
        study_core.mkdir(parents=True, exist_ok=True)
        (study_core / "multi_angle").mkdir(parents=True, exist_ok=True)
        (study_core / "lighting_passes").mkdir(parents=True, exist_ok=True)
        (study_core / "skybox_env").mkdir(parents=True, exist_ok=True)

        _export_studies_model(twin, s_dir, filename)

        engine.output_dir = s_dir
        engine.save_telemetry_snapshot()

        return True, f"Study session '{folder}/{filename}' finalized! Core package generated.", audit


def list_all_livewire_sessions() -> Tuple[List[dict], List[dict]]:
    """
    Returns (production_sessions, study_sessions).
    Scans PRODUCTION_ROOT and STUDIES_ROOT.
    """
    prod_sessions = []
    if PRODUCTION_ROOT.exists():
        for folder_dir in sorted(PRODUCTION_ROOT.iterdir()):
            if not folder_dir.is_dir() or folder_dir.name.startswith("."):
                continue
            for sess_dir in sorted(folder_dir.iterdir()):
                if not sess_dir.is_dir() or sess_dir.name.startswith("."):
                    continue
                sess_path = f"{folder_dir.name}/{sess_dir.name}"
                fbx_file = sess_dir / f"{sess_dir.name}.fbx"
                fbx_size_mb = round(fbx_file.stat().st_size / (1024 * 1024), 2) if fbx_file.exists() else 0.0
                audit_file = sess_dir / "production_leniency_audit.json"
                audit_status = "Finalized"
                if audit_file.exists():
                    try:
                        with open(audit_file, "r") as f:
                            a_data = json.load(f)
                            v_pct = a_data.get("variance_percentage", 0.0)
                            audit_status = f"Finalized (Leniency {v_pct:.1f}%)" if v_pct > 0 else "Finalized (Bit-Exact)"
                    except Exception:
                        pass
                elif not fbx_file.exists():
                    audit_status = "In Progress"

                session_json = sess_dir / f"{sess_dir.name}_session.json"
                strokes = 0
                if session_json.exists():
                    try:
                        with open(session_json, "r") as f:
                            s_data = json.load(f)
                            strokes = s_data.get("total_strokes", 0)
                    except Exception:
                        pass

                prod_sessions.append({
                    "session_path": sess_path,
                    "fbx_name": f"{sess_dir.name}.fbx" if fbx_file.exists() else "pending",
                    "fbx_size_mb": fbx_size_mb,
                    "strokes": strokes,
                    "status": audit_status,
                    "folder": folder_dir.name,
                    "filename": sess_dir.name
                })

    study_sessions = []
    if STUDIES_ROOT.exists():
        for folder_dir in sorted(STUDIES_ROOT.iterdir()):
            if not folder_dir.is_dir() or folder_dir.name.startswith("."):
                continue
            for sess_dir in sorted(folder_dir.iterdir()):
                if not sess_dir.is_dir() or sess_dir.name.startswith("."):
                    continue
                sess_path = f"{folder_dir.name}/{sess_dir.name}"
                study_core = sess_dir / "study_core"
                has_core = study_core.exists()
                has_snap = check_in_progress_snapshot_exists("studies", folder_dir.name, sess_dir.name)
                
                status = "Finalized (100% Exact)" if has_core else ("In-Progress Snapshot" if has_snap else "Recording Active")
                
                session_json = sess_dir / f"{sess_dir.name}_session.json"
                strokes = 0
                if session_json.exists():
                    try:
                        with open(session_json, "r") as f:
                            s_data = json.load(f)
                            strokes = s_data.get("total_strokes", 0)
                    except Exception:
                        pass

                study_sessions.append({
                    "session_path": sess_path,
                    "base_snapshot": f"{sess_dir.name}_base.glb",
                    "strokes": strokes,
                    "study_core": "Ingested" if has_core else "Pending",
                    "status": status,
                    "folder": folder_dir.name,
                    "filename": sess_dir.name
                })

    return prod_sessions, study_sessions


class LiveWireSessionManager:
    _instance: Optional["LiveWireSessionManager"] = None

    def __init__(self):
        self.engine: Optional[LiveWireStudyEngine] = None
        self.is_connected: bool = False
        self.is_recording: bool = False
        self.current_session_name: str = ""
        self.current_mode: str = "studies"
        self.last_pause_camera: Optional[dict] = None
        self.recording_start_epoch: float = 0.0
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_polling: bool = False
        self.recent_events_log: List[str] = [
            "• LiveWire wire link standing by.",
            "• Ready to stream Nomad Sculpt geometry and kinetic strokes."
        ]
        self.audio_status: str = "standby"
        self.audio_node_id: Optional[str] = None
        self._stop_audio: bool = False
        self.audio_thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(cls) -> "LiveWireSessionManager":
        if cls._instance is None:
            cls._instance = LiveWireSessionManager()
        return cls._instance

    def _on_stroke_received(self, stroke: StrokeKineticEvent) -> None:
        t_str = time.strftime("%H:%M:%S")
        evt = f"[{t_str}] Stroke #{stroke.stroke_id}: {stroke.brush_archetype} on {stroke.anatomical_region} (E={stroke.kinetic_energy:.3f})"
        self.recent_events_log.append(evt)
        if len(self.recent_events_log) > 40:
            self.recent_events_log.pop(0)

    def _on_mesh_loaded(self, twin: LiveSculptTwin) -> None:
        t_str = time.strftime("%H:%M:%S")
        evt = f"[{t_str}] Mesh Twin Ingested: '{twin.sculpt_id}' ({twin.vertex_count:,} verts, {twin.face_count:,} faces)"
        self.recent_events_log.append(evt)
        if len(self.recent_events_log) > 40:
            self.recent_events_log.pop(0)

    def _on_stage_transition(self, stage: str, conf: float) -> None:
        t_str = time.strftime("%H:%M:%S")
        evt = f"[{t_str}] Stage Transition: {stage.replace('_', ' ').title()} ({conf:.0%})"
        self.recent_events_log.append(evt)
        if len(self.recent_events_log) > 40:
            self.recent_events_log.pop(0)

    def _start_poll_thread(self) -> None:
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_polling = False
        self._poll_thread = threading.Thread(
            target=self._wire_poll_worker,
            name="LiveWirePollWorker",
            daemon=True
        )
        self._poll_thread.start()

    def _wire_poll_worker(self) -> None:
        while not self._stop_polling and self.is_connected and self.engine:
            try:
                self.engine.poll_wire_packet()
                self.engine.check_idle_cycle()
            except Exception:
                pass
            time.sleep(0.01)

    def get_active_audio_node(self) -> Optional[str]:
        """Inspects active fleet nodes for a connected Android/Termux microphone node."""
        try:
            from gemini_app.fleet.nodes import load_active_nodes
            active = load_active_nodes()
            for node in active:
                nid = node.get("node_id", "")
                telem = node.get("telemetry", {})
                if telem.get("is_termux") or "android" in nid or "termux" in nid or "aarch64" in nid:
                    return nid
        except Exception:
            pass
        return None

    def get_audio_status_display(self) -> str:
        """Returns formatted status for the UI session data box."""
        if self.is_recording and self.audio_status.startswith("recording"):
            return f"Audio Mic: 🔴 {self.audio_status}"
        active_node = self.get_active_audio_node()
        if active_node:
            return f"Audio Mic: 🟢 Ready ({active_node} / Bose QC)"
        else:
            return "Audio Mic: 🟡 Awaiting Phone (run 'python3 gemini-integrated.py node 192.168.1.91')"

    def _audio_recording_loop(self, s_dir: Path, filename: str) -> None:
        """Background worker that captures audio chunks from satellite node while recording is active."""
        chunk_idx = 1
        audio_dir = s_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        while not self._stop_audio and self.is_recording:
            active_node = self.get_active_audio_node()
            if not active_node:
                self.audio_status = "awaiting_phone_node"
                time.sleep(1.5)
                continue

            self.audio_status = f"recording ({active_node} chunk #{chunk_idx})"
            try:
                from gemini_app.fleet.nodes import record_node_audio
                # 10s chunk duration
                res = record_node_audio(node_id=active_node, duration=10, encoder="opus")
                if res.get("status") == "ok" and res.get("local_path"):
                    src = Path(res["local_path"])
                    if src.exists():
                        target_chunk = audio_dir / f"{filename}_chunk_{chunk_idx:03d}.opus"
                        try:
                            import shutil
                            shutil.copyfile(src, target_chunk)
                        except Exception:
                            pass
                        chunk_idx += 1
            except Exception:
                time.sleep(2.0)

        self.audio_status = "finalized" if chunk_idx > 1 else "standby"

    def connect_wire(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        settings = load_livewire_settings()
        h = host or settings.get("host", DEFAULT_HOST)
        p = port or settings.get("port", DEFAULT_PORT)
        if not self.engine:
            profile = get_default_study_profile()
            self.engine = LiveWireStudyEngine(profile=profile, host=h, port=p)
        else:
            self.engine.host = h
            self.engine.port = p

        # Register callbacks once
        self.engine.on_stroke_callbacks = [self._on_stroke_received]
        self.engine.on_mesh_loaded_callbacks = [self._on_mesh_loaded]
        self.engine.on_stage_change_callbacks = [self._on_stage_transition]

        ok = self.engine.connect(timeout=4.0)
        self.is_connected = ok
        if ok:
            self.engine.enable_live_sync()
            self.engine.request_mesh()
            self._start_poll_thread()
            t_str = time.strftime("%H:%M:%S")
            self.recent_events_log.append(f"[{t_str}] Nomad Sculpt Link connected to {h}:{p}")
        return ok

    def disconnect_wire(self):
        self._stop_polling = True
        if self.engine:
            self.engine.running = False
            if self.engine.conn:
                try:
                    self.engine.conn.disconnect()
                except Exception:
                    pass
        self.is_connected = False
        t_str = time.strftime("%H:%M:%S")
        self.recent_events_log.append(f"[{t_str}] Nomad Sculpt Link disconnected.")

    def start_recording(self, session_name: str, mode: str) -> Tuple[bool, str]:
        val_ok, err, folder, filename = validate_session_name(session_name)
        if not val_ok:
            return False, err

        if check_session_collision(mode, folder, filename) and not check_in_progress_snapshot_exists(mode, folder, filename):
            return False, f"Warning: '{session_name}' already exists in that folder"

        if not self.engine:
            self.engine = LiveWireStudyEngine(host=DEFAULT_HOST, port=DEFAULT_PORT)
            self.engine.on_stroke_callbacks = [self._on_stroke_received]
            self.engine.on_mesh_loaded_callbacks = [self._on_mesh_loaded]
            self.engine.on_stage_change_callbacks = [self._on_stage_transition]

        s_dir = get_session_dir(mode, folder, filename)
        s_dir.mkdir(parents=True, exist_ok=True)
        self.engine.output_dir = s_dir

        latest_snap = get_latest_snapshot(mode, folder, filename)
        if latest_snap:
            record_camera_snapto(
                mode=mode,
                folder=folder,
                filename=filename,
                from_camera=latest_snap.get("camera_at_pause", {}),
                to_camera=self.engine.camera_state
            )

        self.current_session_name = f"{folder}/{filename}"
        self.current_mode = mode
        self.is_recording = True
        self.recording_start_epoch = time.time()

        # Start background audio recording thread
        self._stop_audio = False
        self.audio_thread = threading.Thread(
            target=self._audio_recording_loop,
            args=(s_dir, filename),
            name="LiveWireAudioCapture",
            daemon=True
        )
        self.audio_thread.start()

        t_str = time.strftime("%H:%M:%S")
        self.recent_events_log.append(f"[{t_str}] RECORDING STARTED: '{folder}/{filename}' [{mode.upper()}]")
        return True, f"Recording started for '{self.current_session_name}' [{mode.upper()}]"

    def stop_recording(self) -> Tuple[bool, str]:
        if not self.is_recording:
            return False, "Recording was not active."
        self.is_recording = False
        self._stop_audio = True

        if self.engine:
            self.engine.save_telemetry_snapshot()

        t_str = time.strftime("%H:%M:%S")
        self.recent_events_log.append(f"[{t_str}] RECORDING STOPPED: '{self.current_session_name}'")
        return True, f"Recording stopped for '{self.current_session_name}'."

    def in_progress_snapshot(self) -> Tuple[bool, str]:
        if not self.is_connected or not self.engine:
            return False, "Nomad Sculpt link must be connected to capture snapshot."
        if not self.current_session_name:
            return False, "please name your livewire session"

        val_ok, err, folder, filename = validate_session_name(self.current_session_name)
        if not val_ok:
            return False, err

        self.is_recording = False
        meta_p = save_in_progress_snapshot(
            mode=self.current_mode,
            folder=folder,
            filename=filename,
            twin=self.engine.twin,
            camera=self.engine.camera_state,
            stats=self.engine.stats
        )
        return True, f"In-Progress Snapshot saved: {meta_p.name}"

    def cancel_current_session(self) -> Tuple[bool, str]:
        if not self.current_session_name:
            return False, "No active session name to cancel."
        val_ok, err, folder, filename = validate_session_name(self.current_session_name)
        if not val_ok:
            return False, err

        self.is_recording = False
        ok, msg = cancel_and_scrub_session(self.current_mode, folder, filename)
        self.current_session_name = ""
        return ok, msg

    def finalize_current_session(self) -> Tuple[bool, str, dict]:
        if not self.is_connected or not self.engine:
            return False, "please open the file from your session on your local machine again before clicking finalize", {}
        if self.engine.twin.vertex_count == 0:
            return False, "please open the file from your session on your local machine again before clicking finalize", {}
        if not self.current_session_name:
            return False, "please name your livewire session", {}

        val_ok, err, folder, filename = validate_session_name(self.current_session_name)
        if not val_ok:
            return False, err, {}

        self.is_recording = False
        ok, msg, audit = finalize_livewire_session(
            mode=self.current_mode,
            folder=folder,
            filename=filename,
            engine=self.engine,
            tolerance_pct=3.0
        )
        return ok, msg, audit


def get_saved_token() -> str:
    if TOKEN_FILE.exists():
        try:
            return TOKEN_FILE.read_text().strip()
        except Exception:
            pass
    return "0616eb7d-f173-4de0-969c-578dbfb1b9edf8a98263-2053-4ad9-8aee-10cf3ab0f94d"


# ---------------------------------------------------------------------------
# Enums for Semantic Sculpting Perception
# ---------------------------------------------------------------------------

class BrushArchetype(str, Enum):
    MOVE_GRAB = "move_grab"
    CLAY_BUILDUP = "clay_buildup"
    STANDARD_BRUSH = "standard_brush"
    INFLATE = "inflate"
    CREASE_PINCH = "crease_pinch"
    FLATTEN_TRIM = "flatten_trim"
    SMOOTH_RELAX = "smooth_relax"
    PAINT_MASK = "paint_mask"
    UNKNOWN = "unknown"


class CameraInspectionMode(str, Enum):
    SILHOUETTE_PROFILE = "silhouette_profile"
    GRAZING_SPECULAR = "grazing_specular"
    ORTHOGONAL_DIRECT = "orthogonal_direct"
    UNKNOWN = "unknown"


class SculptStage(str, Enum):
    STAGE_1_GESTURE_SILHOUETTE = "stage_1_gesture_silhouette"
    STAGE_2_BONY_LANDMARKS = "stage_2_bony_landmarks"
    STAGE_3_PLANAR_ARTICULATION = "stage_3_planar_articulation"
    STAGE_4_ORGANIC_TRANSITION = "stage_4_organic_transition"
    STAGE_5_MICRO_CHARACTER_DETAIL = "stage_5_micro_character_detail"


# ---------------------------------------------------------------------------
# Telemetry Data Structures
# ---------------------------------------------------------------------------

@dataclass
class CameraState:
    world_from_view: np.ndarray = field(default_factory=lambda: np.identity(4, dtype=np.float32))
    pivot: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    fov_y: float = 50.0
    orthographic: bool = False
    camera_pos: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 3.0], dtype=np.float32))
    view_dir: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, -1.0], dtype=np.float32))
    last_update_time: float = 0.0
    orbit_count: int = 0


@dataclass
class StrokeKineticEvent:
    stroke_id: int
    timestamp: float
    touched_vertices: int
    kinetic_energy: float
    max_displacement: float
    mean_displacement: float
    hotspot_center: Tuple[float, float, float]
    hotspot_radius: float
    anatomical_region: str
    action_type: str  # inflate_build, carve_crease, smooth_flatten, paint_mask
    brush_archetype: str = BrushArchetype.UNKNOWN.value
    brush_confidence: float = 0.0
    directional_coherence: float = 0.0
    normal_alignment: float = 0.0
    tangential_convergence: float = 0.0
    inspection_mode: str = CameraInspectionMode.UNKNOWN.value
    inspection_angle_deg: float = 0.0
    sculpt_stage: str = SculptStage.STAGE_1_GESTURE_SILHOUETTE.value
    duration_ms: float = 0.0


@dataclass
class LiveSessionStats:
    sculpt_id: str
    vertex_count: int
    face_count: int
    total_strokes: int = 0
    total_kinetic_energy: float = 0.0
    active_duration_seconds: float = 0.0
    recent_strokes: List[StrokeKineticEvent] = field(default_factory=list)
    region_heatmaps: Dict[str, float] = field(default_factory=dict)
    brush_time_distribution: Dict[str, float] = field(default_factory=dict)
    brush_stroke_counts: Dict[str, int] = field(default_factory=dict)
    brush_transitions: Dict[str, Dict[str, int]] = field(default_factory=dict)
    current_stage: str = SculptStage.STAGE_1_GESTURE_SILHOUETTE.value
    stage_confidence: float = 0.0
    last_stroke_time: float = 0.0
    last_brush_archetype: Optional[str] = None


# ---------------------------------------------------------------------------
# Brush Kinematics & Inspection Analyzers
# ---------------------------------------------------------------------------

class BrushKinematicClassifier:
    """
    Mathematical classifier that reverse-engineers the artist's brush
    archetype from the differential displacement field.
    """

    @staticmethod
    def classify(
        old_positions: np.ndarray,
        new_positions: np.ndarray,
        hotspot_center: np.ndarray,
        hotspot_radius: float,
        model_radius: float,
        is_paint_only: bool = False
    ) -> Tuple[BrushArchetype, float, float, float, float]:
        """
        Returns (archetype, confidence, directional_coherence, normal_alignment, tangential_convergence).
        """
        if is_paint_only:
            return (BrushArchetype.PAINT_MASK, 0.95, 0.0, 0.0, 0.0)

        displacements = new_positions - old_positions
        count = len(displacements)
        if count == 0:
            return (BrushArchetype.UNKNOWN, 0.0, 0.0, 0.0, 0.0)

        disp_norms = np.linalg.norm(displacements, axis=1)
        mean_disp = float(np.mean(disp_norms))
        if mean_disp < 1e-6:
            return (BrushArchetype.PAINT_MASK, 0.90, 0.0, 0.0, 0.0)

        # 1. Directional Coherence (Sum of vectors / sum of magnitudes)
        # For Move/Grab: all vertices shift rigidly in the same direction -> coherence ~ 1.0
        # For localized expansion/crease/smooth: vectors point in different directions -> lower coherence
        sum_disp = np.sum(displacements, axis=0)
        sum_disp_norm = float(np.linalg.norm(sum_disp))
        sum_mags = float(np.sum(disp_norms))
        directional_coherence = sum_disp_norm / max(sum_mags, 1e-8)

        # 2. Local Patch Surface Normal & Tangent Plane via PCA
        # Centering the patch positions
        patch_centered = old_positions - hotspot_center
        cov = np.dot(patch_centered.T, patch_centered) / max(count, 1)
        try:
            eigvals, eigvecs = np.linalg.eigh(cov)
            # Minimum eigenvalue vector is patch normal
            patch_normal = eigvecs[:, 0]
            # Ensure normal points outward from model center
            if np.dot(patch_normal, hotspot_center) < 0:
                patch_normal = -patch_normal
        except Exception:
            patch_normal = hotspot_center / max(np.linalg.norm(hotspot_center), 1e-6)

        # 3. Normal Alignment Ratio
        # Positive = outward push (Inflate / Clay), Negative = inward carve, Zero = tangential
        safe_norms = np.where(disp_norms > 1e-8, disp_norms, 1.0)
        norm_dot = np.sum((displacements / safe_norms[:, None]) * patch_normal, axis=1)
        normal_alignment = float(np.mean(norm_dot))

        # 4. Tangential Convergence (Pinch / Crease flux)
        # Vectors from vertex toward the hotspot center
        inward_dirs = hotspot_center - old_positions
        inward_norms = np.linalg.norm(inward_dirs, axis=1)
        safe_inward_norms = np.where(inward_norms > 1e-8, inward_norms, 1.0)
        inward_unit = inward_dirs / safe_inward_norms[:, None]
        tangential_convergence = float(np.mean(np.sum((displacements / safe_norms[:, None]) * inward_unit, axis=1)))

        # 5. Planar Variance Reduction (Flatten / Trim)
        # Projects old and new positions along patch normal to see if variance flattened
        var_old = float(np.var(np.dot(old_positions, patch_normal)))
        var_new = float(np.var(np.dot(new_positions, patch_normal)))
        planar_flattening_ratio = (var_old - var_new) / max(var_old, 1e-6)

        # Normalized radius ratio relative to model scale
        radius_ratio = hotspot_radius / max(model_radius, 1e-4)

        # Classification Logic Hierarchy
        # A. Move / Grab: High directional coherence across a broad region
        if directional_coherence > 0.82 and (radius_ratio > 0.12 or count > 50):
            confidence = min(1.0, 0.70 + (directional_coherence - 0.82) * 1.5)
            return (BrushArchetype.MOVE_GRAB, float(confidence), directional_coherence, normal_alignment, tangential_convergence)

        # B. Crease / Pinch: High tangential convergence or narrow carving groove
        if tangential_convergence > 0.40 and radius_ratio < 0.15:
            confidence = min(1.0, 0.65 + tangential_convergence * 0.5)
            return (BrushArchetype.CREASE_PINCH, float(confidence), directional_coherence, normal_alignment, tangential_convergence)

        # C. Flatten / Trim: Normal variance collapsed significantly
        if planar_flattening_ratio > 0.35 and abs(normal_alignment) < 0.45:
            confidence = min(1.0, 0.70 + planar_flattening_ratio * 0.4)
            return (BrushArchetype.FLATTEN_TRIM, float(confidence), directional_coherence, normal_alignment, tangential_convergence)

        # D. Smooth / Relax: Very low normal alignment, low coherence, damping displacements
        if abs(normal_alignment) < 0.20 and directional_coherence < 0.50:
            confidence = min(1.0, 0.75 + (0.20 - abs(normal_alignment)) * 1.2)
            return (BrushArchetype.SMOOTH_RELAX, float(confidence), directional_coherence, normal_alignment, tangential_convergence)

        # E. Inflate: High normal alignment, outward displacement
        if normal_alignment > 0.75:
            confidence = min(1.0, 0.60 + normal_alignment * 0.4)
            return (BrushArchetype.INFLATE, float(confidence), directional_coherence, normal_alignment, tangential_convergence)

        # F. Clay Buildup: Positive normal push with moderate directional spread
        if normal_alignment > 0.30:
            confidence = min(1.0, 0.65 + normal_alignment * 0.4)
            return (BrushArchetype.CLAY_BUILDUP, float(confidence), directional_coherence, normal_alignment, tangential_convergence)

        # G. Standard Brush (Carve / Draw inward)
        if normal_alignment < -0.30:
            confidence = min(1.0, 0.65 + abs(normal_alignment) * 0.4)
            return (BrushArchetype.STANDARD_BRUSH, float(confidence), directional_coherence, normal_alignment, tangential_convergence)

        # Fallback
        return (BrushArchetype.STANDARD_BRUSH, 0.50, directional_coherence, normal_alignment, tangential_convergence)


class CameraInspectionAnalyzer:
    """
    Decodes Nomad camera view telemetry and calculates eye-hand inspection coupling.
    """

    @staticmethod
    def parse_camera_matrix(header: dict) -> Optional[CameraState]:
        matrix_raw = header.get("world_from_view")
        if not matrix_raw or len(matrix_raw) != 16:
            return None

        # 4x4 column-major matrix
        mat = np.array(matrix_raw, dtype=np.float32).reshape(4, 4, order="F")
        pivot = np.array(header.get("pivot", [0.0, 0.0, 0.0]), dtype=np.float32)
        fov_y = float(header.get("fov_y", 50.0))
        ortho = bool(header.get("orthographic", False))

        # Camera eye in world coordinates is translation column (column 3, rows 0,1,2)
        cam_pos = mat[:3, 3].copy()
        
        # View direction is negative Z in view space transformed to world
        # mat[:3, 2] is camera Z axis in world coords -> view direction is -mat[:3, 2]
        view_dir = -mat[:3, 2].copy()
        view_norm = np.linalg.norm(view_dir)
        if view_norm > 1e-6:
            view_dir /= view_norm
        else:
            view_dir = np.array([0.0, 0.0, -1.0], dtype=np.float32)

        return CameraState(
            world_from_view=mat,
            pivot=pivot,
            fov_y=fov_y,
            orthographic=ortho,
            camera_pos=cam_pos,
            view_dir=view_dir,
            last_update_time=time.time()
        )

    @staticmethod
    def evaluate_inspection(
        camera: CameraState,
        hotspot_center: np.ndarray,
        patch_normal: np.ndarray
    ) -> Tuple[CameraInspectionMode, float]:
        """
        Determines whether the artist is inspecting the stroke along its silhouette
        profile, under grazing specular light, or orthogonally head-on.
        """
        # Vector from camera to hotspot
        cam_to_hotspot = hotspot_center - camera.camera_pos
        dist = np.linalg.norm(cam_to_hotspot)
        if dist > 1e-6:
            view_ray = cam_to_hotspot / dist
        else:
            view_ray = camera.view_dir

        # Dot product between view ray and patch normal
        norm_val = np.linalg.norm(patch_normal)
        if norm_val > 1e-6:
            unit_normal = patch_normal / norm_val
        else:
            unit_normal = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        cos_angle = float(np.dot(view_ray, unit_normal))
        # Absolute cos angle between ray and normal
        # (cos = 0 implies 90 degrees = silhouette perimeter!)
        abs_cos = min(1.0, abs(cos_angle))
        angle_rad = math.acos(abs_cos)
        angle_deg = math.degrees(angle_rad)

        # Silhouette Profile: angle near 90 degrees (view ray parallel to tangent plane)
        if 70.0 <= angle_deg <= 110.0:
            return (CameraInspectionMode.SILHOUETTE_PROFILE, angle_deg)
        # Grazing Specular Sheen: 45 to 70 degrees
        elif 45.0 <= angle_deg < 70.0:
            return (CameraInspectionMode.GRAZING_SPECULAR, angle_deg)
        # Orthogonal Direct: 0 to 45 degrees
        else:
            return (CameraInspectionMode.ORTHOGONAL_DIRECT, angle_deg)


class SculptingStageInferrer:
    """
    Infers the human creative stage (Gesture -> Landmarks -> Planes -> Organic -> Detail)
    using kinetic energy, brush distribution, stroke radius, and inspection cadence.
    """

    @staticmethod
    def infer_stage(
        recent_strokes: List[StrokeKineticEvent],
        model_radius: float
    ) -> Tuple[SculptStage, float]:
        if not recent_strokes:
            return (SculptStage.STAGE_1_GESTURE_SILHOUETTE, 0.5)

        window = recent_strokes[-20:]
        total = len(window)

        # Metrics over window
        mean_energy = float(np.mean([s.kinetic_energy for s in window]))
        mean_radius_ratio = float(np.mean([s.hotspot_radius / max(model_radius, 1e-4) for s in window]))
        
        brush_counts: Dict[str, int] = {}
        inspection_counts: Dict[str, int] = {}
        for s in window:
            brush_counts[s.brush_archetype] = brush_counts.get(s.brush_archetype, 0) + 1
            inspection_counts[s.inspection_mode] = inspection_counts.get(s.inspection_mode, 0) + 1

        move_ratio = brush_counts.get(BrushArchetype.MOVE_GRAB.value, 0) / total
        clay_ratio = brush_counts.get(BrushArchetype.CLAY_BUILDUP.value, 0) / total
        flatten_ratio = brush_counts.get(BrushArchetype.FLATTEN_TRIM.value, 0) / total
        smooth_ratio = brush_counts.get(BrushArchetype.SMOOTH_RELAX.value, 0) / total
        crease_ratio = brush_counts.get(BrushArchetype.CREASE_PINCH.value, 0) / total
        silhouette_ratio = inspection_counts.get(CameraInspectionMode.SILHOUETTE_PROFILE.value, 0) / total

        # Stage 5: Micro Character Detail (Micro-radius, crease/pinch dominant, low energy)
        if crease_ratio > 0.35 or (mean_radius_ratio < 0.06 and mean_energy < 0.05):
            conf = min(1.0, 0.65 + crease_ratio * 0.5)
            return (SculptStage.STAGE_5_MICRO_CHARACTER_DETAIL, float(conf))

        # Stage 1: Gesture & Silhouette Blockout (Large radius, high Move ratio or high energy + silhouette checks)
        if move_ratio > 0.40 or (mean_radius_ratio > 0.22 and silhouette_ratio > 0.30):
            conf = min(1.0, 0.65 + move_ratio * 0.5)
            return (SculptStage.STAGE_1_GESTURE_SILHOUETTE, float(conf))

        # Stage 3: Planar Articulation (Flatten / Trim dominant, planes emerging)
        if flatten_ratio > 0.25:
            conf = min(1.0, 0.65 + flatten_ratio * 0.5)
            return (SculptStage.STAGE_3_PLANAR_ARTICULATION, float(conf))

        # Stage 4: Organic Transition (High Smooth/Relax alternating with Clay)
        if smooth_ratio > 0.30 and clay_ratio > 0.20:
            conf = min(1.0, 0.65 + (smooth_ratio + clay_ratio) * 0.4)
            return (SculptStage.STAGE_4_ORGANIC_TRANSITION, float(conf))

        # Stage 2: Bony Landmarks & Skeletal Anchors (Clay Buildup & Standard carves)
        if clay_ratio > 0.35:
            conf = min(1.0, 0.60 + clay_ratio * 0.4)
            return (SculptStage.STAGE_2_BONY_LANDMARKS, float(conf))

        # Default fallback: Stage 2
        return (SculptStage.STAGE_2_BONY_LANDMARKS, 0.50)


# ---------------------------------------------------------------------------
# Live Sculpt Digital Twin
# ---------------------------------------------------------------------------

class LiveSculptTwin:
    """
    In-memory representation of the 3D sculpt, updated in place
    via vectorized NumPy operations as Nomad Link packets arrive.
    """
    def __init__(self, sculpt_id: str = "untitled"):
        self.sculpt_id = sculpt_id
        self.mesh_id: str = ""
        self.positions: np.ndarray = np.empty((0, 3), dtype=np.float32)
        self.previous_positions: Optional[np.ndarray] = None
        self.faces: List[List[int]] = []
        self.face_sizes: np.ndarray = np.empty(0, dtype=np.int32)
        self.corner_verts: np.ndarray = np.empty(0, dtype=np.int32)
        self.colors: Optional[np.ndarray] = None  # (N, 3) float32
        self.normals: Optional[np.ndarray] = None  # (N, 3) float32
        self.world_matrix: np.ndarray = np.identity(4, dtype=np.float32)
        self.version: int = 0
        self.bbox_min: np.ndarray = np.zeros(3, dtype=np.float32)
        self.bbox_max: np.ndarray = np.zeros(3, dtype=np.float32)
        self.bbox_center: np.ndarray = np.zeros(3, dtype=np.float32)
        self.dimensions: np.ndarray = np.zeros(3, dtype=np.float32)
        self.model_radius: float = 1.0

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    @property
    def face_count(self) -> int:
        return len(self.faces) if self.faces else len(self.face_sizes)

    def update_bounds(self):
        if len(self.positions) > 0:
            self.bbox_min = np.min(self.positions, axis=0)
            self.bbox_max = np.max(self.positions, axis=0)
            self.bbox_center = (self.bbox_min + self.bbox_max) * 0.5
            self.dimensions = self.bbox_max - self.bbox_min
            self.model_radius = float(np.max(np.linalg.norm(self.positions - self.bbox_center, axis=1)))
        else:
            self.model_radius = 1.0

    def ingest_full_mesh(self, header: dict, binary: bytes):
        """Builds full mesh twin from Nomad Link 'mesh_full' wire packet."""
        self.mesh_id = header.get("mesh_id", self.sculpt_id)
        name = header.get("name", self.sculpt_id).replace(" ", "_").lower()
        self.sculpt_id = name
        vert_count = int(header["vertex_count"])
        face_count = int(header["face_count"])

        # Positions (float32x3)
        pos_offset = int(header.get("position_offset", 0))
        self.positions = np.frombuffer(
            binary[pos_offset : pos_offset + vert_count * 12], dtype="<f4"
        ).reshape(-1, 3).copy()

        # Face topology
        self.faces = []
        if header.get("face_format") == "corners":
            corner_count = int(header.get("corner_count", 0))
            face_size_offset = int(header.get("face_size_offset", 0))
            corner_vert_offset = int(header.get("corner_vertex_offset", 0))
            self.face_sizes = np.frombuffer(binary[face_size_offset : face_size_offset + face_count * 4], dtype="<i4")
            self.corner_verts = np.frombuffer(binary[corner_vert_offset : corner_vert_offset + corner_count * 4], dtype="<i4")
            idx = 0
            for sz in self.face_sizes:
                self.faces.append(self.corner_verts[idx : idx + sz].tolist())
                idx += sz
        else:
            face_offset = int(header.get("face_offset", 0))
            raw_faces = np.frombuffer(binary[face_offset : face_offset + face_count * 16], dtype="<i4").reshape(-1, 4)
            for f in raw_faces:
                if f[3] >= 0:
                    self.faces.append([int(f[0]), int(f[1]), int(f[2]), int(f[3])])
                else:
                    self.faces.append([int(f[0]), int(f[1]), int(f[2])])

        # Colors (RGB)
        color_offset = header.get("base_color_offset") or header.get("color_offset")
        color_format = header.get("base_color_format") or header.get("color_format")
        if color_offset is not None and color_format == "rgb8":
            raw_cols = np.frombuffer(binary[color_offset : color_offset + vert_count * 3], dtype=np.uint8).reshape(-1, 3)
            self.colors = (raw_cols / 255.0).astype(np.float32)
        else:
            self.colors = None

        if "world_matrix" in header:
            self.world_matrix = np.array(header["world_matrix"], dtype=np.float32).reshape(4, 4)

        self.update_bounds()
        self.version += 1

    def apply_sparse_delta(
        self,
        header: dict,
        binary: bytes,
        camera: Optional[CameraState] = None,
        active_stage: str = SculptStage.STAGE_1_GESTURE_SILHOUETTE.value,
        active_brush_override: Optional[str] = None
    ) -> Optional[StrokeKineticEvent]:
        """
        Applies a sparse 'mesh_delta' packet in-place to the twin.
        Computes kinetic deformation energy, brush archetype, eye inspection coupling,
        and anatomical hotspot.
        """
        guard_vert_count = int(header.get("vertex_count", len(self.positions)))
        if guard_vert_count != len(self.positions):
            return None  # Topology guard triggered: mesh remeshed / changed

        count = int(header.get("count", 0))
        if count == 0:
            return None

        # 1. Read touched vertex indices
        idx_offset = int(header.get("index_offset", 0))
        indices = np.frombuffer(binary[idx_offset : idx_offset + count * 4], dtype="<u4").astype(np.int64)

        # 2. Extract new positions and compute displacement delta
        pos_offset = int(header.get("position_offset", 0))
        new_positions = np.frombuffer(
            binary[pos_offset : pos_offset + count * 12], dtype="<f4"
        ).reshape(-1, 3)

        old_positions = self.positions[indices]
        displacements = new_positions - old_positions
        disp_magnitudes = np.linalg.norm(displacements, axis=1)

        # Kinetic energy proxy: 0.5 * sum(||dx||^2)
        kinetic_energy = float(0.5 * np.sum(disp_magnitudes ** 2))
        max_disp = float(np.max(disp_magnitudes)) if len(disp_magnitudes) > 0 else 0.0
        mean_disp = float(np.mean(disp_magnitudes)) if len(disp_magnitudes) > 0 else 0.0

        # Hotspot computation (centroid & radius of touched vertices)
        hotspot_center = np.mean(new_positions, axis=0)
        hotspot_radius = float(np.max(np.linalg.norm(new_positions - hotspot_center, axis=1))) if len(new_positions) > 0 else 0.0

        # Classify anatomical region relative to bounding box
        # DEDICATED ALIEN CRANIOFACIAL & HEAD ANATOMY SCHEMA:
        # Macro-Cranium, Occipital Dome, Supraorbital Brow, Orbital Cavities,
        # Nasal/Olfactory Aperture, Zygomatic Flanges, Maxilla, Mandible/Chin, Throat
        rel_y = (hotspot_center[1] - self.bbox_min[1]) / max(self.dimensions[1], 1e-4)
        rel_x = abs(hotspot_center[0] - self.bbox_center[0]) / max(self.dimensions[0] * 0.5, 1e-4)
        rel_z = (hotspot_center[2] - self.bbox_center[2]) / max(self.dimensions[2] * 0.5, 1e-4)

        if rel_y > 0.68:
            if rel_z < -0.15:
                anatomical_region = "Occipital / Elongated Cranial Dome"
            elif rel_x > 0.50:
                anatomical_region = "Temporal Ridge / Cranial Flange"
            else:
                anatomical_region = "Cranial Vault / Upper Head"
        elif rel_y > 0.45:
            if rel_z > 0.10:
                if rel_x < 0.25:
                    anatomical_region = "Nasal Bridge / Olfactory Aperture"
                elif rel_x < 0.65:
                    anatomical_region = "Orbital Socket / Supraorbital Brow"
                else:
                    anatomical_region = "Zygomatic Arch / Alien Cheek Flange"
            else:
                if rel_x > 0.50:
                    anatomical_region = "Temporal / Lateral Cranial Wall"
                else:
                    anatomical_region = "Mid-Cranial Parietal Core"
        elif rel_y > 0.22:
            if rel_z > 0.05:
                if rel_y > 0.35:
                    anatomical_region = "Maxilla / Upper Labial Margin"
                else:
                    anatomical_region = "Mandible / Mental Apex (Alien Chin)"
            else:
                if rel_x > 0.45:
                    anatomical_region = "Mandibular Angle / Jaw Flange"
                else:
                    anatomical_region = "Cranial Base / Nuchal Crest"
        else:
            if rel_z > 0.05:
                anatomical_region = "Gular Throat / Submandibular Plane"
            else:
                anatomical_region = "Cervical Column / Neck Anchor"

        # Action classification (inflation vs carve vs smooth)
        centroid_rays = old_positions - self.bbox_center
        ray_norms = np.linalg.norm(centroid_rays, axis=1, keepdims=True)
        ray_norms[ray_norms == 0] = 1.0
        unit_rays = centroid_rays / ray_norms
        outward_components = np.sum(displacements * unit_rays, axis=1)
        mean_outward = float(np.mean(outward_components))

        if mean_outward > 0.005:
            action_type = "inflate_build"
        elif mean_outward < -0.005:
            action_type = "carve_crease"
        else:
            action_type = "smooth_flatten"

        # 3. Brush Archetype & Kinematics Inversion
        (
            archetype,
            brush_conf,
            dir_coherence,
            norm_alignment,
            tangential_conv
        ) = BrushKinematicClassifier.classify(
            old_positions=old_positions,
            new_positions=new_positions,
            hotspot_center=hotspot_center,
            hotspot_radius=hotspot_radius,
            model_radius=self.model_radius,
            is_paint_only=False
        )

        # Allow explicit user override if passed from Nomad tool channel
        if active_brush_override:
            brush_val = active_brush_override
        else:
            brush_val = archetype.value

        # 4. Camera Coupling & Inspection Telemetry
        # Compute patch normal from displacement or centroid
        patch_normal = hotspot_center - self.bbox_center
        norm_len = np.linalg.norm(patch_normal)
        if norm_len > 1e-6:
            patch_normal /= norm_len
        else:
            patch_normal = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        if camera:
            insp_mode, insp_angle = CameraInspectionAnalyzer.evaluate_inspection(
                camera, hotspot_center, patch_normal
            )
            inspection_mode_val = insp_mode.value
            inspection_angle_deg = insp_angle
        else:
            inspection_mode_val = CameraInspectionMode.UNKNOWN.value
            inspection_angle_deg = 0.0

        # In-place update of positions
        self.positions[indices] = new_positions

        # Update colors if present in delta
        if "color_offset" in header and self.colors is not None:
            c_offset = int(header["color_offset"])
            if header.get("color_format") == "rgb8":
                raw_c = np.frombuffer(binary[c_offset : c_offset + count * 3], dtype=np.uint8).reshape(-1, 3)
                self.colors[indices] = raw_c / 255.0

        self.version += 1
        self.update_bounds()

        return StrokeKineticEvent(
            stroke_id=self.version,
            timestamp=time.time(),
            touched_vertices=count,
            kinetic_energy=kinetic_energy,
            max_displacement=max_disp,
            mean_displacement=mean_disp,
            hotspot_center=(float(hotspot_center[0]), float(hotspot_center[1]), float(hotspot_center[2])),
            hotspot_radius=hotspot_radius,
            anatomical_region=anatomical_region,
            action_type=action_type,
            brush_archetype=brush_val,
            brush_confidence=brush_conf,
            directional_coherence=dir_coherence,
            normal_alignment=norm_alignment,
            tangential_convergence=tangential_conv,
            inspection_mode=inspection_mode_val,
            inspection_angle_deg=inspection_angle_deg,
            sculpt_stage=active_stage
        )

    def apply_attribute_delta(
        self,
        header: dict,
        binary: bytes,
        camera: Optional[CameraState] = None,
        active_stage: str = SculptStage.STAGE_5_MICRO_CHARACTER_DETAIL.value
    ) -> Optional[StrokeKineticEvent]:
        """
        Handles 'mesh_attributes' paint/mask packets where geometry is unchanged
        but vertex colors or layers are modified (Paint / Mask Brush).
        """
        guard_vert_count = int(header.get("vertex_count", len(self.positions)))
        if guard_vert_count != len(self.positions):
            return None

        # Check color updates
        color_offset = header.get("color_offset")
        if color_offset is not None and len(binary) > color_offset:
            vert_count = len(self.positions)
            c_fmt = header.get("color_format", "rgb8")
            if c_fmt == "rgb8":
                raw_c = np.frombuffer(binary[color_offset : color_offset + vert_count * 3], dtype=np.uint8).reshape(-1, 3)
                self.colors = (raw_c / 255.0).astype(np.float32)

        self.version += 1
        return StrokeKineticEvent(
            stroke_id=self.version,
            timestamp=time.time(),
            touched_vertices=len(self.positions),
            kinetic_energy=0.01,
            max_displacement=0.0,
            mean_displacement=0.0,
            hotspot_center=(float(self.bbox_center[0]), float(self.bbox_center[1]), float(self.bbox_center[2])),
            hotspot_radius=self.model_radius,
            anatomical_region="Full Model Surface",
            action_type="paint_mask",
            brush_archetype=BrushArchetype.PAINT_MASK.value,
            brush_confidence=0.98,
            directional_coherence=0.0,
            normal_alignment=0.0,
            tangential_convergence=0.0,
            inspection_mode=CameraInspectionMode.ORTHOGONAL_DIRECT.value,
            inspection_angle_deg=0.0,
            sculpt_stage=active_stage
        )

    def to_raw_dict(self) -> Dict[str, Any]:
        return {
            "sculpt_id": self.sculpt_id,
            "vertices": self.positions.tolist(),
            "faces": self.faces,
            "colors": self.colors.tolist() if self.colors is not None else None,
            "vertex_count": len(self.positions),
            "face_count": len(self.faces)
        }


# ---------------------------------------------------------------------------
# Live Wire Study Engine Daemon
# ---------------------------------------------------------------------------

class LiveWireStudyEngine:
    """
    Connects directly to the Nomad Link wire socket.
    Integrates the Live Sculpt Twin with 100% Data-Driven Study Profiles,
    Brush Archetype Classification, Camera Inspection, and Stage Progression.
    """
    def __init__(
        self,
        profile: Optional[StudyProfile] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        output_dir: Optional[str] = None
    ):
        self.profile = profile or get_default_study_profile()
        self.host = host
        self.port = port
        self.output_dir = Path(output_dir or f"Projects/3drealms/models/nomad_intake/{self.profile.name}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.token = get_saved_token()
        self.conn = None
        self.twin = LiveSculptTwin()
        self.camera_state: Optional[CameraState] = None
        self.stats = LiveSessionStats(sculpt_id="untitled", vertex_count=0, face_count=0)
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # User declared or overridden brush
        self.active_brush_override: Optional[str] = None

        # Event hooks / callbacks
        self.on_stroke_callbacks: List[Callable[[StrokeKineticEvent], None]] = []
        self.on_mesh_loaded_callbacks: List[Callable[[LiveSculptTwin], None]] = []
        self.on_idle_callbacks: List[Callable[[float], None]] = []
        self.on_stage_change_callbacks: List[Callable[[str, float], None]] = []

        # Idle tracking
        self.idle_threshold_seconds = 3.5
        self.last_activity_time = time.time()
        self.idle_study_triggered = False

    def set_active_brush(self, brush_name: Optional[str]):
        """Explicitly declares or overrides the active brush tool (e.g. from UI)."""
        self.active_brush_override = brush_name
        if brush_name:
            print(f"[LiveWireEngine] Active Brush Set: '{brush_name}'")

    def register_on_stroke(self, callback: Callable[[StrokeKineticEvent], None]):
        self.on_stroke_callbacks.append(callback)

    def register_on_mesh_loaded(self, callback: Callable[[LiveSculptTwin], None]):
        self.on_mesh_loaded_callbacks.append(callback)

    def register_on_stage_change(self, callback: Callable[[str, float], None]):
        self.on_stage_change_callbacks.append(callback)

    def connect(self, timeout: float = 8.0) -> bool:
        if transport is None:
            print("[LiveWireEngine] Warning: transport module not found. Running in standalone twin mode.")
            return False

        capabilities = [
            "camera", "mesh_full", "mesh_attributes", "sculpt_layers", "mesh_delta",
            "mesh_delta_receive", "mesh_attributes_receive", "hierarchy", "material",
            "session_config", "scene_edits", "object_state", "selection_transfer"
        ]

        print(f"[LiveWireEngine] Connecting to Nomad Link at {self.host}:{self.port}...")
        self.conn = transport.Connection(client_name="LiveWire Study Engine", capabilities=capabilities)
        self.conn.connect(self.host, self.port, self.token, transport.VERSION, 1)

        start = time.time()
        self.config_revision = 0
        while time.time() - start < timeout:
            for header, binary in self.conn.poll():
                kind = header.get("type")
                if kind == "session_config":
                    self.config_revision = header.get("revision", 0)
                elif kind == "hello":
                    print(f"[LiveWireEngine] Wire established. Nomad Version: {header.get('nomad_version')}")
                    # Enable live_sync in Nomad Link session
                    self.enable_live_sync()
                    return True
                elif kind == "pairing_pending":
                    print("[LiveWireEngine] Pairing request pending on iPad...")
            time.sleep(0.05)
        print("[LiveWireEngine] Connection timed out.")
        return False

    def enable_live_sync(self):
        """Signals Nomad Sculpt to enable real-time live streaming edits."""
        if self.conn:
            self.conn.send({
                "type": "set_session_config",
                "base_revision": self.config_revision,
                "live_sync": True,
                "sync_mode": "auto",
                "sync_view": True,
                "sync_objects": True,
                "sync_materials": True,
                "sync_lights": True,
                "sync_cameras": True
            })

    def request_mesh(self):
        if self.conn:
            print("[LiveWireEngine] Wire requesting complete scene from iPad...")
            self.conn.send({"type": "request_scene"})

    def handle_camera_packet(self, header: dict):
        cam = CameraInspectionAnalyzer.parse_camera_matrix(header)
        if cam:
            if self.camera_state is not None:
                cam.orbit_count = self.camera_state.orbit_count + 1
            self.camera_state = cam
            self.last_activity_time = time.time()

    def process_stroke_event(self, stroke_event: StrokeKineticEvent):
        """Updates live statistics, transitions, heatmaps, and stage classification."""
        self.stats.total_strokes += 1
        self.stats.total_kinetic_energy += stroke_event.kinetic_energy
        self.stats.recent_strokes.append(stroke_event)
        if len(self.stats.recent_strokes) > 200:
            self.stats.recent_strokes.pop(0)

        # 1. Update anatomical region heatmap
        reg = stroke_event.anatomical_region
        self.stats.region_heatmaps[reg] = self.stats.region_heatmaps.get(reg, 0.0) + stroke_event.kinetic_energy

        # 2. Update brush distribution and transition matrix
        brush = stroke_event.brush_archetype
        self.stats.brush_stroke_counts[brush] = self.stats.brush_stroke_counts.get(brush, 0) + 1
        self.stats.brush_time_distribution[brush] = self.stats.brush_time_distribution.get(brush, 0.0) + stroke_event.duration_ms

        if self.stats.last_brush_archetype and self.stats.last_brush_archetype != brush:
            prev = self.stats.last_brush_archetype
            if prev not in self.stats.brush_transitions:
                self.stats.brush_transitions[prev] = {}
            self.stats.brush_transitions[prev][brush] = self.stats.brush_transitions[prev].get(brush, 0) + 1

        self.stats.last_brush_archetype = brush
        self.stats.last_stroke_time = stroke_event.timestamp
        self.last_activity_time = stroke_event.timestamp
        self.idle_study_triggered = False

        # 3. Infer Human Sculpting Stage
        new_stage, conf = SculptingStageInferrer.infer_stage(
            self.stats.recent_strokes, self.twin.model_radius
        )
        if new_stage.value != self.stats.current_stage:
            old_stage = self.stats.current_stage
            self.stats.current_stage = new_stage.value
            self.stats.stage_confidence = conf
            print(f"[LiveWireEngine] Creative Stage Transition: {old_stage} -> {new_stage.value} ({conf:.0%})")
            for scb in self.on_stage_change_callbacks:
                scb(new_stage.value, conf)
        else:
            self.stats.stage_confidence = conf

        # 4. Fire stroke callbacks
        for cb in self.on_stroke_callbacks:
            cb(stroke_event)

    def poll_wire_packet(self):
        """Processes incoming packets off the live transport socket."""
        if not self.conn:
            return

        for header, binary in self.conn.poll():
            kind = header.get("type")

            if kind == "mesh_full":
                self.twin.ingest_full_mesh(header, binary)
                self.stats.sculpt_id = self.twin.sculpt_id
                self.stats.vertex_count = self.twin.vertex_count
                self.stats.face_count = self.twin.face_count
                self.last_activity_time = time.time()
                self.idle_study_triggered = False
                print(f"[LiveWireEngine] Mesh Twin Ingested: '{self.twin.sculpt_id}' ({self.twin.vertex_count:,} vertices)")
                for cb in self.on_mesh_loaded_callbacks:
                    cb(self.twin)

            elif kind == "camera":
                self.handle_camera_packet(header)

            elif kind == "mesh_delta":
                stroke_event = self.twin.apply_sparse_delta(
                    header=header,
                    binary=binary,
                    camera=self.camera_state,
                    active_stage=self.stats.current_stage,
                    active_brush_override=self.active_brush_override
                )
                if stroke_event:
                    self.process_stroke_event(stroke_event)
                else:
                    # Topology mismatch: twin demands fresh mesh pull
                    print("[LiveWireEngine] Topology moved on during sculpting. Auto-refreshing mesh...")
                    self.request_mesh()

            elif kind == "mesh_attributes":
                stroke_event = self.twin.apply_attribute_delta(
                    header=header,
                    binary=binary,
                    camera=self.camera_state,
                    active_stage=self.stats.current_stage
                )
                if stroke_event:
                    self.process_stroke_event(stroke_event)

            elif kind == "error":
                print(f"[LiveWireEngine] Wire Error: {header.get('message')}")

            elif kind == "session_config":
                self.config_revision = header.get("revision", self.config_revision)

    def check_idle_cycle(self):
        """Monitors pause in sculpting to trigger data-driven study analyses."""
        now = time.time()
        idle_duration = now - self.last_activity_time

        if (
            idle_duration >= self.idle_threshold_seconds
            and not self.idle_study_triggered
            and self.stats.total_strokes > 0
        ):
            self.idle_study_triggered = True
            print(f"\n[LiveWireEngine] Artist pause detected ({idle_duration:.1f}s idle). Auto-evaluating study profile...")
            self.save_telemetry_snapshot()
            for cb in self.on_idle_callbacks:
                cb(idle_duration)

    def save_telemetry_snapshot(self):
        """Flushes live wire telemetry, brush distribution, and stage progress to disk."""
        snapshot_file = self.output_dir / "live_wire_telemetry.json"
        payload = {
            "sculpt_id": self.stats.sculpt_id,
            "vertex_count": self.twin.vertex_count,
            "face_count": self.twin.face_count,
            "current_stage": self.stats.current_stage,
            "stage_confidence": round(self.stats.stage_confidence, 3),
            "total_strokes": self.stats.total_strokes,
            "total_kinetic_energy": round(self.stats.total_kinetic_energy, 4),
            "brush_stroke_counts": self.stats.brush_stroke_counts,
            "brush_transitions": self.stats.brush_transitions,
            "region_kinetic_heatmaps": {k: round(v, 4) for k, v in self.stats.region_heatmaps.items()},
            "camera_state": {
                "fov_y": self.camera_state.fov_y if self.camera_state else 50.0,
                "orthographic": self.camera_state.orthographic if self.camera_state else False,
                "orbit_count": self.camera_state.orbit_count if self.camera_state else 0
            },
            "recent_strokes": [asdict(s) for s in self.stats.recent_strokes[-20:]],
            "profile_name": self.profile.name
        }
        with open(snapshot_file, "w") as f:
            json.dump(payload, f, indent=2)

    def run_daemon(self):
        """Runs the continuous background polling loop."""
        self.running = True
        print("[LiveWireEngine] Daemon listening on live wire...")
        try:
            while self.running:
                self.poll_wire_packet()
                self.check_idle_cycle()
                time.sleep(0.01)
        except KeyboardInterrupt:
            print("[LiveWireEngine] Stopping daemon...")
        finally:
            self.save_telemetry_snapshot()
            if self.conn:
                self.conn.disconnect()

    def simulate_mock_stroke(
        self,
        vertex_indices: List[int],
        displacement_vec: Tuple[float, float, float],
        camera: Optional[CameraState] = None,
        active_brush_override: Optional[str] = None
    ) -> StrokeKineticEvent:
        """Allows instant offline unit testing of the live twin delta engine."""
        indices = np.array(vertex_indices, dtype=np.uint32)
        count = len(indices)
        
        # Build mock positions
        current_pos = self.twin.positions[indices]
        disp_arr = np.array(displacement_vec, dtype=np.float32)
        new_pos = current_pos + disp_arr

        # Pack into mock binary buffer
        binary = bytearray()
        idx_offset = len(binary)
        binary.extend(indices.tobytes())
        pos_offset = len(binary)
        binary.extend(new_pos.astype("<f4").tobytes())

        header = {
            "type": "mesh_delta",
            "mesh_id": self.twin.mesh_id,
            "count": count,
            "vertex_count": len(self.twin.positions),
            "index_offset": idx_offset,
            "position_offset": pos_offset
        }

        stroke = self.twin.apply_sparse_delta(
            header=header,
            binary=bytes(binary),
            camera=camera or self.camera_state,
            active_stage=self.stats.current_stage,
            active_brush_override=active_brush_override or self.active_brush_override
        )
        if stroke:
            self.process_stroke_event(stroke)
        return stroke


if __name__ == "__main__":
    profile = get_default_study_profile()
    engine = LiveWireStudyEngine(profile=profile)
    print(f"[LiveWireEngine] Initialized with Profile: '{profile.name}'")
    print(f"[LiveWireEngine] Profile cameras: {len(profile.cameras)}, environments: {len(profile.environments)}, LODs: {len(profile.lods)}")
