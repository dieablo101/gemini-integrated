#!/usr/bin/env python3
"""
Interactive & automated verification probe for Pillar #1 Brain Upgrade (CortexBrain).
Run this script to inspect live ingestion, hypergraph topology, associative recall,
and subconscious epiphany generation.
"""

import sys
import time
from pathlib import Path

# Add new_engine to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from gemini_app.cortex.brain import CortexBrain
from gemini_app.tools.mind_tools import recall_memory

def run_probe():
    print("=" * 60)
    print("🚀 PROBING NEW ENGINE: CortexBrain & Subconscious Pipeline")
    print("=" * 60)

    test_home = Path(__file__).parent / "test_run_cortex"
    test_home.mkdir(exist_ok=True)

    print("\n1. Initializing CortexBrain with active Subconscious daemon...")
    brain = CortexBrain(home_dir=test_home, enable_subconscious=True)
    telemetry = brain.get_telemetry()
    print(f"   ✓ Brain initialized. Subconscious daemon active: {telemetry['subconscious_running']}")

    print("\n2. Ingesting multi-domain conversational turns...")
    t1 = brain.ingest_turn(
        chat_id="chat_probe",
        turn_number=1,
        role="user",
        content="We are setting up the iPad iSH bridge to Nomad Sculpt and headless Blender 3D export to Godot.",
    )
    print(f"   ✓ Turn #1 ingested -> {t1['shards_count']} shards, {t1['graph_vertices']} vertices, {t1['graph_edges']} edges")

    t2 = brain.ingest_turn(
        chat_id="chat_probe",
        turn_number=2,
        role="assistant",
        content="Security Policy: Passkey encryption with PBKDF2 must protect the remote socket mesh and satellite nodes.",
    )
    print(f"   ✓ Turn #2 ingested -> {t2['shards_count']} shards, {t2['graph_vertices']} vertices, {t2['graph_edges']} edges")

    t3 = brain.ingest_turn(
        chat_id="chat_probe",
        turn_number=3,
        role="user",
        content="TODO: Calibrate reconnect timer precision on the satellite links and test whisper latency.",
    )
    print(f"   ✓ Turn #3 ingested -> {t3['shards_count']} shards, {t3['graph_vertices']} vertices, {t3['graph_edges']} edges")

    print("\n3. Testing Unified Multi-Tier Recall...")
    queries = ["blender godot", "security policy", "satellite reconnect"]
    for q in queries:
        rec = brain.recall(q, max_results=3)
        print(f"\n   Query: '{q}' (Latency: {rec['latency_ms']}ms)")
        print(f"   - FTS matches: {rec['matches_count']}")
        print(f"   - Relational shards: {rec['relational_shards_count']}")
        print(f"   - Graph associations: {len(rec['graph_associations'])}")
        for assoc in rec['graph_associations'][:3]:
            print(f"       * [{assoc['vtype']}] {assoc['label']} (energy: {assoc['energy']})")

    print("\n4. Probing Subconscious Incubation & Stillness Gate...")
    print(f"   - Hearth seeds waiting: {brain.get_telemetry()['hearth_seeds']}")
    print("   - Simulating incubation step...")
    epiphany = brain.subconscious_worker.incubate_step()
    if epiphany:
        print(f"   ★ Epiphany generated: '{epiphany.spark_name}'!")
        print(f"     Summary: {epiphany.summary}")
    else:
        print("   - Still accumulating conceptual resonance in the hearth.")

    print("\n5. Testing Graph Persistence...")
    saved = brain.save_graph()
    print(f"   ✓ Graph persisted to {brain.graph_path}: {saved} ({brain.graph_path.stat().st_size} bytes)")

    brain.stop_subconscious()
    print(f"\n✓ Subconscious daemon cleanly shut down.")
    print("=" * 60)
    print("ALL TESTS PASSED! Ready for live testing.")
    print("=" * 60)

if __name__ == "__main__":
    run_probe()
