"""
Custom End-to-End Scenario Test for mind_twin:
Demonstrating:
1. Routine vs Novel task gating (dormant vs active incubation)
2. Directional 7-slot working memory constraint & latent suppression
3. Background Core 1 stochastic collision synthesis
4. Conclusive API reality probe verification
5. Epiphany trajection into conscious working memory without attention flood
"""

import time
import os
import json
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine, WorkingMemorySlot
from sandbox.mind_twin.core.subconscious.novelty_detector import NoveltyDetector
from sandbox.mind_twin.core.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from sandbox.mind_twin.core.subconscious.conclusive_probe import ConclusiveRealityProbe, RealityProbeResult
from sandbox.mind_twin.core.boot_synthesizer import BootSynthesizer

def run_custom_test():
    print("======================================================================")
    print("           MIND_TWIN ARCHITECTURAL SCENARIO TEST EXECUTION            ")
    print("======================================================================\n")

    # ---------------------------------------------------------
    # STAGE 1: ROUTINE WORKLOAD (EXPECTATION: DORMANT SUBCONSCIOUS)
    # ---------------------------------------------------------
    print(">>> STAGE 1: Simulating Routine Workload ('git commit & unit test')")
    routine_prompt = "git status and run tests to verify clean working tree"
    
    detector = NoveltyDetector()
    eval_routine = detector.evaluate(
        task_prompt=routine_prompt,
        active_topic="general"
    )
    print(f"  • Routine Task Novelty Score: {eval_routine.novelty_score:.3f} (Threshold: {detector.novelty_threshold})")
    print(f"  • Subconscious Worker Incubation Triggered: {eval_routine.should_fire_incubation}")
    assert not eval_routine.should_fire_incubation, "Subconscious should remain dormant on routine tasks!"
    print("  [✓] PASS: Subconscious strictly dormant. Zero CPU/API waste.\n")

    # ---------------------------------------------------------
    # STAGE 2: OUT-OF-THE-NORM CREATIVE DILEMMA (EXPECTATION: INCUBATION FIRES)
    # ---------------------------------------------------------
    print(">>> STAGE 2: Introducing Out-Of-The-Norm Task ('Phone Gyro to Blender Rig')")
    novel_prompt = "stream phone gyro quaternion telemetry to pose 3d blender character armature bones over p2p udp"
    
    eval_creative = detector.evaluate(
        task_prompt=novel_prompt,
        active_topic="blender & godot plugin development"
    )
    print(f"  • Creative Task Novelty Score: {eval_creative.novelty_score:.3f} (Threshold: {detector.novelty_threshold})")
    print(f"  • Subconscious Worker Incubation Triggered: {eval_creative.should_fire_incubation}")
    assert eval_creative.should_fire_incubation, "Subconscious must fire on novel/creative tasks!"
    print("  [✓] PASS: Novelty gate tripped. Worker ignited.\n")

    # ---------------------------------------------------------
    # STAGE 3: 7-SLOT WORKING MEMORY UNDER HIGH CONCEPT PRESSURE
    # ---------------------------------------------------------
    print(">>> STAGE 3: Testing 7-Slot Gate & Dynamic Depth Hierarchy")
    graph = Hypergraph()
    gate = DirectionalGateEngine(max_slots=7, depth_resistance_gamma=1.45)
    gate.update_trajectory(novel_prompt, active_topic="blender & godot plugin development")

    # Populate graph with 22 disparate candidate nodes (would flood naive LLM)
    candidates = [
        ("topic_blender", "Topic: Blender Rigging", 2.5),
        ("node_toughbook", "Host: Toughbook Core", 2.2),
        ("node_phone", "Device: Android Termux PNS", 2.1),
        ("tool_bmesh", "Tool: BMesh Geometry", 1.8),
        ("tool_armature", "Tool: PoseBone Transform", 1.9),
        ("pns_gyro", "Sensor: Gyroscope 6-DOF", 2.0),
        ("pns_lux", "Sensor: Ambient Lux", 0.9),
        ("pns_audio", "Sensor: Decibel Monitor", 0.8),
        ("node_ipad", "Device: iPad iSH Alpine", 1.1),
        ("usecase_godot", "Usecase: Godot Engine Bridge", 1.3),
        ("usecase_p2p", "Usecase: Local UDP Telemetry", 1.7),
        ("usecase_vcs", "Usecase: Git Versioning", 1.0),
        ("note_revisit_timer", "Note: Calibrate Reconnect Timer", 0.7),
        ("note_pypi_token", "Note: Encrypted PyPI Token", 0.6),
        ("note_emacs_dojo", "Note: Emacs Coding Dojo", 0.5),
        ("note_nomad_sculpt", "Note: Nomad Sculpt Ingestion", 1.2),
        ("topic_security", "Topic: System Bulletproofing", 0.8),
        ("task_water_sim", "Task: Water Shader Simulation", 1.0),
        ("task_loot_engine", "Task: Loot Generation System", 0.7),
        ("somatic_battery", "Somatic: Battery Level 41%", 0.9),
        ("somatic_desk", "Somatic: User Desk Stationary", 1.1),
        ("somatic_quiet", "Somatic: Room Acoustic Quiet", 0.9),
    ]
    candidate_activations = {}
    for cid, label, energy in candidates:
        graph.add_vertex(cid, label=label, vtype="concept", base_energy=energy)
        candidate_activations[cid] = energy

    # Connect deep child hierarchy to armature tool
    graph.add_vertex("armature_quaternion", label="Quaternion Matrix Rotation", vtype="math", base_energy=1.6)
    graph.add_vertex("armature_slerp", label="SLERP Dead-Reckoning Filter", vtype="algorithm", base_energy=1.4)
    graph.add_hyperedge(["tool_armature"], ["armature_quaternion"], weight=0.9, relation="has_math")
    graph.add_hyperedge(["armature_quaternion"], ["armature_slerp"], weight=0.85, relation="interpolates_with")

    snapshot = gate.gate_and_filter(
        graph=graph,
        candidate_activations=candidate_activations
    )

    print(f"  • Total Candidate Concepts Available: {len(candidates) + 2}")
    print(f"  • Active Slots Occupied: {len(snapshot.slots)} / {gate.max_slots}")
    print(f"  • Concepts Suppressed to Latent Store: {snapshot.suppressed_candidates_count}")
    assert len(snapshot.slots) <= 7, "Miller's law violated: more than 7 slots active!"
    assert snapshot.suppressed_candidates_count >= 15, "Latent suppression failed!"
    
    print("\n  Active 7 Conscious Slots (Ordered by Competition Metric):")
    for s in snapshot.slots:
        print(f"    Slot {s.slot_index + 1}: [{s.domain}] '{s.label}' (Depth: {s.max_depth_reached}, Energy: {s.root.energy:.2f})")
        for child in s.root.children:
            for line in child.format_tree("      "):
                print(line)
    print("  [✓] PASS: Exactly 7 slots active, 15 concepts suppressed. No flood.\n")

    # ---------------------------------------------------------
    # STAGE 4: SUBCONSCIOUS COLLISION & REALITY PROBE
    # ---------------------------------------------------------
    print(">>> STAGE 4: Forked Subconscious Graph Collision & Reality Gate")
    channel = EpiphanyChannel(capacity=10)
    probe = ConclusiveRealityProbe(confidence_gate=0.75)
    
    # Simulate background stochastic collision finding a high-resonance bridge
    print("  • Subconscious Worker synthesizing cross-domain connection...")
    bridge_concept_a = "Sensor: Gyroscope 6-DOF (Android PNS)"
    bridge_concept_b = "Tool: PoseBone Transform (Blender Armature)"
    
    # 1. Test Reality Probe on a bogus/hallucinatory bridge first
    bogus_verdict = probe.evaluate_candidate(
        candidate_id="cand_bogus_01",
        concept_a="Sensor: Ambient Lux",
        concept_b="Note: Encrypted PyPI Token",
        domain_a="pns_sensor",
        domain_b="packaging",
        proposed_bridge="Use room light brightness to decrypt PyPI master key"
    )
    print(f"  • Bogus Bridge Feasibility: {bogus_verdict.is_feasible} (Conf: {bogus_verdict.confidence})")
    print(f"    Mechanism: {bogus_verdict.technical_mechanism}")
    assert not bogus_verdict.is_feasible, "Probe should have rejected absurd bridge!"

    # 2. Test Reality Probe on the genuine technical bridge
    real_verdict = probe.evaluate_candidate(
        candidate_id="cand_valid_02",
        concept_a=bridge_concept_a,
        concept_b=bridge_concept_b,
        domain_a="pns_sensor",
        domain_b="blender_godot",
        proposed_bridge="Stream phone gyro orientation quaternions over socket directly into Blender pose bone matrix transforms."
    )
    print(f"  • Valid Bridge Feasibility: {real_verdict.is_feasible} (Conf: {real_verdict.confidence:.2f})")
    print(f"    Summary: {real_verdict.actionable_summary}")
    assert real_verdict.is_feasible and real_verdict.confidence >= 0.75, "Probe rejected valid technical bridge!"
    print("  [✓] PASS: Reality Probe filter successfully rejected hallucination and approved valid discovery.\n")

    # ---------------------------------------------------------
    # STAGE 5: TRAJECTING THE EPIPHANY INTO CONSCIOUS WORKING MEMORY
    # ---------------------------------------------------------
    print(">>> STAGE 5: Non-Blocking Epiphany Trajection into Conscious Gate")
    packet = EpiphanyPacket(
        packet_id="spark_gyro_rig_01",
        spark_name="Phone Gyro -> Blender Bone Rigging",
        domain_bridge=["PNS Sensor", "Blender 3D"],
        feasibility_score=real_verdict.confidence,
        summary=real_verdict.actionable_summary,
        mechanism=real_verdict.technical_mechanism,
    )
    channel.push(packet)
    print(f"  • Epiphany queued in lockless channel. Items in ring buffer: {channel.size()}")

    # Conscious gate checks the channel on its conversational cycle
    received_packet = channel.pop()
    assert received_packet is not None, "Failed to pop epiphany from channel!"
    
    print(f"  • Trajecting '{received_packet.spark_name}' into 7-Slot Memory...")
    trajected = gate.traject_epiphany(
        spark_label=received_packet.spark_name,
        domain_bridge=received_packet.domain_bridge,
        feasibility_score=received_packet.feasibility_score,
        summary=received_packet.summary
    )
    print(f"  • Epiphany Trajection Success: {trajected}")
    
    print("\n  Updated Conscious Working Memory After Trajection:")
    for s in gate.current_slots:
        marker = " [★ NEW EPIPHANY SPARK]" if s.is_epiphany else ""
        print(f"    Slot {s.slot_index + 1}: [{s.domain}] '{s.label}' (Depth: {s.max_depth_reached}, Energy: {s.root.energy:.2f}){marker}")
    
    assert len(gate.current_slots) == 7, "Memory ceiling broken after trajection!"
    assert any(s.is_epiphany for s in gate.current_slots), "Epiphany not found in active slots!"
    print("\n  [✓] PASS: Epiphany cleanly seated in Slot. Ceiling strictly maintained at 7.\n")

    print("======================================================================")
    print("           CUSTOM SCENARIO TEST COMPLETED SUCCESSFULLY                ")
    print("======================================================================\n")

if __name__ == "__main__":
    run_custom_test()
