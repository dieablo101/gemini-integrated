#!/usr/bin/env python3
"""
LiveWire Session Recorder Runner
--------------------------------
Background daemon that connects to Nomad Link on iPad, initializes the LiveSculptTwin,
and logs all live stroke kinematics, camera inspection angles, and stage progressions.
Terminates cleanly on SIGINT or SIGTERM and flushes the full session ledger.
"""

import os
import sys
import time
import signal
import json
from pathlib import Path

# Setup paths
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))
NOMAD_LINK_DIR = CURRENT_DIR.parents[2] / "nomad-link" / "examples"
if str(NOMAD_LINK_DIR) not in sys.path:
    sys.path.append(str(NOMAD_LINK_DIR))

from live_wire_engine import LiveWireStudyEngine, DEFAULT_HOST, DEFAULT_PORT
from study_spec import get_default_study_profile

SESSION_DIR = Path("Projects/3drealms/models/nomad_intake/live_test")
SESSION_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = SESSION_DIR / "livewire.pid"
LOG_FILE = SESSION_DIR / "live_wire_stream.log"
STATS_FILE = SESSION_DIR / "live_wire_session.json"

def log_msg(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def main():
    PID_FILE.write_text(str(os.getpid()))
    log_msg(f"LiveWire Recording Runner starting (PID: {os.getpid()}). Target: {DEFAULT_HOST}:{DEFAULT_PORT}")

    profile = get_default_study_profile()
    profile.name = "live_test"
    
    engine = LiveWireStudyEngine(
        profile=profile,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        output_dir=str(SESSION_DIR)
    )

    # Register callbacks for telemetry logging
    def on_stroke(stroke):
        log_msg(
            f"⚡ STROKE #{stroke.stroke_id} | Verts: {stroke.touched_vertices} | "
            f"Archetype: {stroke.brush_archetype} ({stroke.brush_confidence:.0%}) | "
            f"Action: {stroke.action_type} | Energy: {stroke.kinetic_energy:.4f} | "
            f"Region: {stroke.anatomical_region} | Insp: {stroke.inspection_mode} ({stroke.inspection_angle_deg:.1f}°)"
        )
        engine.save_telemetry_snapshot()

    def on_mesh(twin):
        log_msg(f"📦 MESH INGESTED: '{twin.sculpt_id}' ({twin.vertex_count:,} vertices, {twin.face_count:,} faces)")
        engine.save_telemetry_snapshot()

    def on_stage(new_stage, conf):
        log_msg(f"🎯 STAGE SHIFT: {new_stage} (confidence: {conf:.0%})")
        engine.save_telemetry_snapshot()

    def on_idle(duration):
        log_msg(f"⏳ ARTIST PAUSE: {duration:.1f}s idle. Telemetry snapshot flushed.")

    engine.register_on_stroke(on_stroke)
    engine.register_on_mesh_loaded(on_mesh)
    engine.register_on_stage_change(on_stage)
    engine.on_idle_callbacks.append(on_idle)

    # Signal handlers for clean shutdown
    shutdown_requested = [False]
    def handle_sig(sig, frame):
        log_msg(f"Shutdown signal ({sig}) received. Finalizing session record...")
        shutdown_requested[0] = True
        engine.running = False

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    log_msg("Attempting Nomad Link handshake...")
    connected = engine.connect(timeout=8.0)
    if not connected:
        log_msg("❌ Failed to connect to Nomad Link. Is Nomad Sculpt running on iPad with Link active?")
        if PID_FILE.exists():
            PID_FILE.unlink()
        sys.exit(1)

    log_msg("✅ Nomad Link connection established! Requesting initial active scene...")
    engine.request_mesh()

    log_msg("🚀 RECORDER LIVE & ARMED. Polling stroke packets...")
    engine.running = True

    try:
        while engine.running and not shutdown_requested[0]:
            engine.poll_wire_packet()
            engine.check_idle_cycle()
            time.sleep(0.01)
    finally:
        log_msg("Closing recording session and saving final telemetry snapshot...")
        engine.save_telemetry_snapshot()
        if engine.conn:
            try:
                engine.conn.disconnect()
            except Exception:
                pass
        if PID_FILE.exists():
            PID_FILE.unlink()
        log_msg("Session saved cleanly. LiveWire Recorder stopped.")

if __name__ == "__main__":
    main()
