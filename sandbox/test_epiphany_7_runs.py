"""
sandbox/test_epiphany_7_runs.py

Simulates 7 complex, realistic subconscious feeds reflecting actual trajectory,
tensions, somatosensory rhythms, and technical architecture.
Evaluates through the calibrated Resonance Gate and Annealing Engine.
"""

import sys
import time
from typing import Dict, List, Any

from sandbox.mind_twin.core.subconscious.seed_packet import SeedPacket, ObservationVector
from sandbox.mind_twin.core.subconscious.collision_lens import CollisionLens
from sandbox.mind_twin.core.subconscious.resonance_gate import ResonanceGate, ResonanceResult
from sandbox.mind_twin.core.subconscious.accretion_hearth import AccretionHearth
from sandbox.mind_twin.core.subconscious.annealing_engine import AnnealingEngine


def vec(plane: str, label: str, data: Dict[str, Any]) -> ObservationVector:
    return ObservationVector(
        vector_id=f"vec_{plane}_{label}",
        plane=plane,
        label=label,
        data=data,
        weight=1.0,
    )


def run_experiment():
    hearth = AccretionHearth()
    lens = CollisionLens()
    # Calibrated Resonance Gate: Strict thresholds for high selectivity
    gate = ResonanceGate(
        min_compression=0.65,
        min_orthogonality=0.70,
        min_trajectory=0.60,
        overall_threshold=0.75,
    )
    annealing = AnnealingEngine(hearth=hearth)

    feeds = [
        # Feed 1: Somatosensory Neurological Hesitation vs POSIX Socket Errno
        {
            "id": "feed_1_muscle_memory_rift",
            "title": "Neurological Hesitation vs POSIX Socket Errno (The Muscle Memory Rift)",
            "thought": "When coding raw C network protocols at 2 AM, does keystroke hesitation between M-x chords correlate with non-blocking socket errno transitions, or am I just exhausted?",
            "context": "Exploring tactile synchronization between human motor cortex and bare-metal socket state machines.",
            "hints": ["somatic_telemetry", "posix_c", "cognitive_fatigue"],
            "vectors": [
                vec("behavioral", "keystroke_hesitation", {"wpm": 48, "latency_ms": 340, "fatigue_index": 0.78}),
                vec("artifact", "nonblocking_c_socket", {"errno": "EAGAIN", "epoll_edge_triggered": True}),
                vec("relational", "craving_for_instrument_feel", {"agency": "visceral", "anti_passive": True}),
                vec("sensory", "night_terminal_room", {"theme": "purple", "lux": 2.0}),
            ],
            # Word-salad exposition: fails Kolmogorov compression
            "candidate_summary": (
                "The developer's somatosensory nervous system acts as an analog biological transducer "
                "that modulates digital network socket throughput and buffer saturation via neurological hesitation "
                "patterns and micro-delays between keystrokes across prolonged nocturnal development sessions."
            ),
            "candidate_mechanism": (
                "Collect more keystroke interval timestamps to build statistical correlation tables."
            ),
        },

        # Feed 2: Android Wi-Fi Client Isolation & Apophenic Theory
        {
            "id": "feed_2_wifi_isolation_paranoia",
            "title": "Android Wi-Fi Client Isolation & Apophenic Paranoid Theory",
            "thought": "Why does iPad iSH bridge effortlessly over local SSH while the Android phone gets trapped behind subnet client isolation? Is the Android OS actively fighting local mesh agency?",
            "context": "Debugging satellite fleet node connectivity on restricted local subnets.",
            "hints": ["fleet_networking", "android_isolation", "apophenia"],
            "vectors": [
                vec("artifact", "android_kernel_sandbox", {"port": 8022, "selinux": "enforcing", "arp_drop": True}),
                vec("behavioral", "frustrated_burst_capture", {"interrupted": True, "voice_attempts": 3}),
                vec("relational", "mobile_ecosystem_mistrust", {"walled_garden_alienation": True}),
            ],
            # Apophenic cliché: fails orthogonality
            "candidate_summary": (
                "Android Wi-Fi client isolation is simply dropping ARP requests because the corporate operating system "
                "enforces a digital alienation protocol to prevent local mesh symbiosis."
            ),
            "candidate_mechanism": (
                "Bypass network routing layers using reverse outbound tunnels."
            ),
        },

        # Feed 3: iPad Apple Pencil to Headless Blender Topology Rift
        {
            "id": "feed_3_mesh_topology_rift",
            "title": "Nomad Sculpt iPad to Headless Blender (The 3D Topology Rift)",
            "thought": "How do we preserve the fluid trance of 120Hz Apple Pencil sofa sculpting while headless Blender QuadriFlow retopo crunches 800k polygons into game-ready Godot 4 assets?",
            "context": "Multi-device spatial game asset pipeline bridging iPad Pro and Debian workstation.",
            "hints": ["3d_pipeline", "blender_daemon", "spatial_ergonomics"],
            "vectors": [
                vec("behavioral", "sofa_apple_pencil_cadence", {"pressure_levels": 4096, "posture": "relaxed"}),
                vec("artifact", "headless_blender_retopo", {"bmesh": True, "quadriflow": True, "target_faces": 4000}),
                vec("artifact", "godot_asset_hot_reload", {"format": "gltf", "engine": "godot4"}),
            ],
            # Solid engineering, but only bridges 2 planes and lacks trajectory
            "candidate_summary": (
                "Mobile touch surfaces act as organic sketch transceivers, while headless desktop daemons "
                "serve as mechanical geometric compilers."
            ),
            "candidate_mechanism": (
                "Decouple mesh capture from topology baking via an automated background watch folder."
            ),
        },

        # Feed 4: Bicameral Core 1 Affinity & The Race Condition Myth
        {
            "id": "feed_4_bicameral_myth",
            "title": "Bicameral Core 1 Affinity & The Race Condition Myth",
            "thought": "If Core 1 runs stochastic hypergraph diffusion while Core 0 handles conscious TUI events, are we achieving genuine artificial bicameralism or just romanticizing thread scheduling?",
            "context": "Investigating hardware CPU pinning and cognitive separation of concern.",
            "hints": ["cpu_affinity", "bicameralism", "thread_contention"],
            "vectors": [
                vec("artifact", "sched_setaffinity_mask", {"core_id": 1, "posix_affinity": True}),
                vec("artifact", "conscious_textual_event_loop", {"core_id": 0, "fps": 60, "latency_ms": 1.2}),
                vec("relational", "jaynesian_intuition", {"split_mind": True}),
            ],
            # Apophenic cliché: detected "cosmic tapestry"
            "candidate_summary": (
                "Core 0 is the waking ego while Core 1 is the dreaming id, weaving a cosmic tapestry between cycles."
            ),
            "candidate_mechanism": (
                "Set affinity masks using standard Linux sched_setaffinity calls."
            ),
        },

        # Feed 5: Memory Graph Decay vs Guilt of Discarding Ideas
        {
            "id": "feed_5_decay_guilt",
            "title": "Hypergraph Memory Decay vs Psychological Guilt of Discarding Ideas",
            "thought": "As ACT-R decay prunes dormant memory nodes, why do I feel guilty watching old notes fade, even though hoarding 2,000 stale items causes catastrophic cognitive drag?",
            "context": "Balancing long-term relational hypergraph retention with active attention budget.",
            "hints": ["act_r", "memory_decay", "cognitive_guilt"],
            "vectors": [
                vec("artifact", "sqlite_hypergraph_edges", {"count": 1420, "decay_lambda": 0.05}),
                vec("behavioral", "reluctance_to_prune", {"manual_revisits": 14, "hoarded_todos": 48}),
                vec("relational", "existential_impermanence", {"fear_of_loss": True}),
            ],
            # Premature / sterile CS restatement
            "candidate_summary": (
                "Memory decay is simply an algorithmic necessity to prevent combinatorial graph explosion "
                "during associative spreading activation across hyperedge clusters."
            ),
            "candidate_mechanism": (
                "Tune decay half-life parameters in the configuration file."
            ),
        },

        # Feed 6: Fleet CRDT Convergence Across Asynchronous Realities
        {
            "id": "feed_6_crdt_divergence",
            "title": "Fleet CRDT State Convergence Across Asynchronous Realities",
            "thought": "When offline mobile edits collide with background daemon commits, what does eventual consistency mean for a mind that expects instantaneous coherence?",
            "context": "Managing multi-node satellite note state and offline replication.",
            "hints": ["crdt", "vector_clocks", "fleet_nodes"],
            "vectors": [
                vec("artifact", "lww_element_set_crdt", {"clock_skew_ms": 420, "conflict_free": True}),
                vec("behavioral", "offline_train_editing", {"network_disconnected": True}),
                vec("relational", "trust_in_mathematics", {"fear_of_silent_corruption": True}),
            ],
            # Textbook CS recitation: sterile
            "candidate_summary": (
                "CRDT state synchronization guarantees eventual consistency as we know by using deterministic "
                "timestamp ordering to resolve concurrent edits across distributed nodes."
            ),
            "candidate_mechanism": (
                "Apply standard LWW register merge rules on incoming satellite packets."
            ),
        },

        # Feed 7: The Autonomy Singularity & The Externalized Nervous System
        {
            "id": "feed_7_autonomy_singularity",
            "title": "The Autonomy Singularity & The Externalized Nervous System",
            "thought": "Why spend weeks building an air-gapped terminal, custom hypergraph, PBKDF2 vault, and isolated Core 1 subconscious instead of using Cursor or standard LLM APIs?",
            "context": "The fundamental core invariant driving the bilateral Gemini architecture.",
            "hints": ["sovereignty", "hypergraph", "autonomy", "bicameralism"],
            "vectors": [
                vec("behavioral", "home_row_anchoring", {"wpm": 65, "mouse_rejected": True, "keystroke_cadence": "fluid"}),
                vec("artifact", "air_gapped_hypergraph_vault", {"sqlite": True, "pbkdf2_enc": True, "zero_cloud": True}),
                vec("relational", "cognitive_sovereignty", {"uncolonized_mind": True, "anti_leased_cognition": True}),
                vec("sensory", "bare_metal_terminal_ambience", {"viewport": "125x37", "theme": "purple", "os": "debian"}),
            ],
            # True Epiphany: Dense, 4-plane orthogonal bridge, powerful trajectory
            "candidate_summary": (
                "Tool sovereignty is not an engineering preference; it is the biological boundary "
                "that prevents commercial platforms from formatting the cognitive topology of the thinker."
            ),
            "candidate_mechanism": (
                "Anchor and synthesize all cognitive memory into an air-gapped, self-compiling hypergraph "
                "to decouple human thought from vendor platform lifecycles."
            ),
        },
    ]

    print(f"=== CALIBRATED EPIPHANY ENGINE EXPERIMENT (7 COMPLEX RUNS) ===")
    results = []

    for idx, f in enumerate(feeds, 1):
        seed = SeedPacket(
            seed_id=f["id"],
            raw_thought=f["thought"],
            conscious_context=f["context"],
            domain_hints=f["hints"],
            vectors=f["vectors"],
            created_at=time.time() - 500.0,
        )

        matrix = lens.project(seed)
        res: ResonanceResult = gate.evaluate(
            candidate_summary=f["candidate_summary"],
            candidate_mechanism=f["candidate_mechanism"],
            seed=seed,
        )

        decision = annealing.handle_attempt_result(seed, res, t_now=time.time())

        results.append({
            "run": idx,
            "id": f["id"],
            "title": f["title"],
            "thought": f["thought"],
            "candidate_summary": f["candidate_summary"],
            "candidate_mechanism": f["candidate_mechanism"],
            "result": res,
            "decision": decision,
        })

    hits = 0
    misses = 0

    for r in results:
        res = r["result"]
        dec = r["decision"]
        if res.passed:
            hits += 1
            status = "HIT (IGNITE)"
        else:
            misses += 1
            status = f"MISS ({res.miss_type.upper() if res.miss_type else 'FAILED'})"

        print(f"\n--- [Run {r['run']}/7] {r['title']} ---")
        print(f"Tension Knot: {r['thought']}")
        print(f"Candidate Invariant: \"{r['candidate_summary']}\"")
        print(f"Outcome: {status}")
        print(f"  Scores: Comp={res.compression_score:.3f} | Ortho={res.orthogonality_score:.3f} | Traj={res.trajectory_score:.3f} | Overall={res.overall_resonance:.3f}")
        print(f"  Feedback: {res.feedback}")
        print(f"  Annealing Decision: {dec.action.upper()} (Reason: {dec.reason})")

    print(f"\n==========================================")
    print(f"FINAL TALLY: {hits} HIT(S) | {misses} MISS(ES) out of 7 runs.")
    print(f"Selectivity Rate: {round((misses / 7) * 100, 1)}% Misses vs {round((hits / 7) * 100, 1)}% Hits.")
    print(f"==========================================")


if __name__ == "__main__":
    run_experiment()
