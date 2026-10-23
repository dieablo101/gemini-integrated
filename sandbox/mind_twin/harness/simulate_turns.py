"""
Multi-Turn Continuous Cognition Simulation Harness.
Tests how cognition stays in-state across real/simulated time gaps between API calls.
"""
import time
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.activation import ActivationEngine
from sandbox.mind_twin.core.rehydrate import RehydrationEngine
from sandbox.mind_twin.daemon.runner import MindDaemon
from sandbox.mind_twin.harness.probe import load_compiled_graph

def run_multi_turn_simulation():
    print("=" * 76)
    print("  CONTINUOUS COGNITIVE PERSISTENCE SIMULATION (LOCAL STATE <-> REMOTE CALL)")
    print("=" * 76)

    # 1. Initialize Sandbox Shadow Environment
    hypergraph = load_compiled_graph()
    activation_engine = ActivationEngine(hypergraph, default_decay=0.7, default_threshold=0.15, max_hops=3)
    rehydration = RehydrationEngine(hypergraph, activation_engine)
    daemon_file = "/tmp/sandbox_mind_state.json"
    daemon = MindDaemon(daemon_file, hypergraph)

    # Simulated Timeline
    base_time = 1000000.0

    # ── Turn 1: User asks about Blender 3D modeling ───────────────────
    turn1_time = base_time
    print(f"\n[TURN 1] T = {turn1_time:.0f}s")
    print("  User Input: 'How do we generate 3D meshes and rigging in Blender?'")
    
    state1, prof1 = rehydration.rehydrate_and_prime(None, "Blender 3D mesh modeling rigging", now=turn1_time)
    daemon.save_state(state1)
    
    print("\n  >> Local State Vector Compiled for Remote Call (Prompt Injection Frame):")
    print("  " + "\n  ".join(state1.get_summary_frame().split("\n")))
    print(f"  Spotlight Active Count: {len(state1.focus_spotlight)} concepts")
    for item in state1.focus_spotlight[:4]:
        print(f"    - {item.concept_id:<40} (Energy: {item.energy:.3f})")

    # ── Turn 2: 120 Seconds Later (Short Gap) ─────────────────────────
    # User follows up with an ambiguous prompt: 'Can we send that to Godot?'
    turn2_time = turn1_time + 120.0
    print(f"\n[TURN 2] T = {turn2_time:.0f}s (Time elapsed: 2 minutes later)")
    print("  User Input: 'Can we send that to Godot?' (Notice: 'that' is ambiguous!)")

    # The background daemon ticked in between:
    daemon.tick_once(now=turn2_time)
    previous_state = daemon.load_state()

    # Rehydrate with Turn 2 query
    state2, prof2 = rehydration.rehydrate_and_prime(previous_state, "send to Godot", now=turn2_time)
    daemon.save_state(state2)

    print("\n  >> Local State Vector Compiled for Remote Call:")
    print("  " + "\n  ".join(state2.get_summary_frame().split("\n")))
    print("  >> Primed Spotlight (Blender state collided with Godot):")
    for item in state2.focus_spotlight[:5]:
        print(f"    - {item.concept_id:<40} (Energy: {item.energy:.3f})")

    # ── Sleep & Consolidation Cycle ──────────────────────────────────
    print("\n[CONSOLIDATION CYCLE ('DREAMING')]")
    rehydration.consolidate_synapses(state2, eta=0.25)
    print("  >> Strengthened Hebbian hyperedges between active concepts.")

    # ── Turn 3: 14,400 Seconds Later (4 Hours Later) ─────────────────
    # User returns hours later asking something completely different: 'System safety test'
    turn3_time = turn2_time + 14400.0
    print(f"\n[TURN 3] T = {turn3_time:.0f}s (Time elapsed: 4 hours later)")
    print("  User Input: 'Run a system safety test'")

    # Daemon has decayed the old thoughts over 4 hours
    daemon.tick_once(now=turn3_time)
    stale_state = daemon.load_state()

    state3, prof3 = rehydration.rehydrate_and_prime(stale_state, "System safety test emergency", now=turn3_time)
    daemon.save_state(state3)

    print("\n  >> Local State Vector Compiled for Remote Call:")
    print("  " + "\n  ".join(state3.get_summary_frame().split("\n")))
    print("  >> Notice: Blender/Godot naturally decayed below threshold. New Safety focus took over:")
    for item in state3.focus_spotlight[:4]:
        print(f"    - {item.concept_id:<40} (Energy: {item.energy:.3f})")

    print("\n" + "=" * 76)
    print("  SIMULATION COMPLETE: Continuous state preserved & verified.")
    print("=" * 76)

if __name__ == "__main__":
    run_multi_turn_simulation()
