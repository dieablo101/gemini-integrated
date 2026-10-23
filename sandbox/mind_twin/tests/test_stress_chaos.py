"""
Stress & Chaos Test Suite for sandbox/mind_twin Cognitive Architecture.
Subject the system to massive graphs, numerical edge cases, race conditions,
corrupted inputs, socket floods, and extreme time warps.
"""

import math
import os
import random
import socket
import sys
import tempfile
import threading
import time
import unittest
from typing import List, Dict, Any

from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge
from sandbox.mind_twin.core.activation import ActivationEngine, ActivationResult
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine, WorkingMemorySnapshot
from sandbox.mind_twin.core.subconscious.novelty_detector import NoveltyDetector
from sandbox.mind_twin.core.subconscious.conclusive_probe import ConclusiveRealityProbe
from sandbox.mind_twin.core.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from sandbox.mind_twin.core.subconscious.subconscious_worker import SubconsciousWorker
from sandbox.mind_twin.core.pns_sensor import PhoneSensoryTelemetry, PhoneSensorySynthesizer, PNSSensoryReceiver
from sandbox.mind_twin.core.daemon import CognitiveDaemon, ResilientCognitiveSupervisor
from sandbox.mind_twin.core.lapse import LapseManager
from sandbox.mind_twin.core.rehydrate import RehydrationEngine
from sandbox.mind_twin.core.state import CognitiveStateVector, FocusItem
from sandbox.mind_twin.core.boot_synthesizer import BootSynthesizer, UnifiedCognitiveBootState
from sandbox.mind_twin.core.node_capability import FleetTopologySynthesizer, NodeCapabilityProfile, WholeSystemCapability


class MindTwinChaosStressTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="mind_twin_stress_")
        self.ckpt_path = os.path.join(self.tmp_dir, "test_ckpt.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # =========================================================================
    # 1. SCALE & GRAPH TOPOLOGY STRESS
    # =========================================================================
    def test_massive_graph_construction_and_spreading(self):
        """Builds a 5,000 vertex, 10,000 hyperedge graph and stress tests queries."""
        hg = Hypergraph()
        t0 = time.perf_counter()
        
        # 1. Create 5,000 vertices
        for i in range(5000):
            hg.add_vertex(f"v_{i}", label=f"Concept Node {i}", vtype="concept", base_energy=1.0)
            
        # 2. Add 10,000 hyperedges with varied fan-in / fan-out
        for i in range(10000):
            src_count = random.randint(1, 4)
            tgt_count = random.randint(1, 4)
            srcs = [f"v_{random.randint(0, 4999)}" for _ in range(src_count)]
            tgts = [f"v_{random.randint(0, 4999)}" for _ in range(tgt_count)]
            hg.add_hyperedge(sources=srcs, targets=tgts, relation="causes", weight=random.uniform(0.1, 1.5))
            
        self.assertEqual(len(hg.vertices), 5000)
        self.assertEqual(len(hg.edges), 10000)

        # 3. Spreading activation on massive graph
        engine = ActivationEngine(hg, max_hops=3)
        t_spread_0 = time.perf_counter()
        res = engine.spread({"v_42": 1.0, "v_100": 0.8})
        spread_time = time.perf_counter() - t_spread_0

        self.assertIsInstance(res, ActivationResult)
        self.assertLess(spread_time, 2.5, f"Spreading activation took too long: {spread_time:.2f}s")

    # =========================================================================
    # 2. NUMERICAL STABILITY & ARITHMETIC OVERFLOW / UNDERFLOW
    # =========================================================================
    def test_multi_source_overflow_underflow(self):
        """Tests antecedent geometric mean with 1,200 sources (overflow / underflow trap)."""
        hg = Hypergraph()
        sources = [f"src_{i}" for i in range(1200)]
        for s in sources:
            hg.add_vertex(s, label=s)
        hg.add_vertex("target_sink", label="Sink")
        
        # Hyperedge with 1,200 sources
        hg.add_hyperedge(sources=sources, targets=["target_sink"], relation="aggregates")
        engine = ActivationEngine(hg, max_hops=2)
        
        # Seed all sources with energy = 2.0 (would cause float overflow without log-sum)
        seeds = {s: 2.0 for s in sources}
        res = engine.spread(seeds)
        self.assertIn("target_sink", res.node_activations)
        self.assertFalse(math.isinf(res.node_activations["target_sink"]))
        self.assertFalse(math.isnan(res.node_activations["target_sink"]))

    def test_extreme_and_corrupt_energies(self):
        """Tests resilience when vertex energies are 0, negative, inf, nan."""
        hg = Hypergraph()
        hg.add_vertex("v_zero", label="Zero Node", base_energy=0.0)
        hg.add_vertex("v_neg", label="Neg Node", base_energy=-5.0)
        hg.add_vertex("v_inf", label="Inf Node", base_energy=float("inf"))
        hg.add_vertex("v_nan", label="NaN Node", base_energy=float("nan"))
        hg.add_hyperedge(["v_zero"], ["v_neg"])
        hg.add_hyperedge(["v_neg"], ["v_inf"])
        hg.add_hyperedge(["v_inf"], ["v_nan"])

        engine = ActivationEngine(hg)
        seeds = engine.match_seeds("Zero Neg Inf NaN")
        res = engine.spread(seeds)
        self.assertIsInstance(res, ActivationResult)

    # =========================================================================
    # 3. DIRECTIONAL GATE STRESS
    # =========================================================================
    def test_directional_gate_empty_and_massive_inputs(self):
        """Tests directional gate with 0 tokens, 100,000 tokens, and empty candidates."""
        hg = Hypergraph()
        gate = DirectionalGateEngine(max_slots=7)
        
        # Empty graph, empty candidates
        snap_empty = gate.gate_and_filter(hg, {})
        self.assertEqual(len(snap_empty.slots), 0)
        self.assertEqual(snap_empty.total_active_nodes, 0)
        
        # 100,000 word prompt
        huge_prompt = "system architecture hypergraph neural test memory " * 20000
        gate.update_trajectory(huge_prompt)
        self.assertGreater(len(gate.trajectory_tokens), 0)
        
        # Flood with 2,000 candidate activations including NaNs and Infs
        candidates = {}
        for i in range(2000):
            vid = f"cand_{i}"
            hg.add_vertex(vid, label=f"Candidate Concept {i}", vtype="topic")
            candidates[vid] = random.uniform(0.1, 5.0)
        candidates["cand_nan"] = float("nan")
        candidates["cand_inf"] = float("inf")
            
        snap = gate.gate_and_filter(hg, candidates)
        # Must strictly obey Miller's Law (<= 7 slots)
        self.assertLessEqual(len(snap.slots), 7)
        self.assertGreater(snap.suppressed_candidates_count, 1900)

    def test_epiphany_rapid_flood(self):
        """Floods the directional gate with 500 epiphanies consecutively."""
        gate = DirectionalGateEngine(max_slots=7)
        for i in range(500):
            ok = gate.traject_epiphany(
                spark_label=f"Epiphany #{i}",
                domain_bridge=["DomainA", "DomainB"],
                feasibility_score=random.uniform(0.70, 0.99),
                summary=f"Epiphany summary text {i}",
            )
            self.assertTrue(ok)
            # Active slots must NEVER exceed 7
            self.assertLessEqual(len(gate.current_slots), 7)

    # =========================================================================
    # 4. CONCURRENCY & RACE CONDITIONS
    # =========================================================================
    def test_concurrent_graph_reads_and_writes(self):
        """6 simultaneous threads modifying, pruning, and reading the hypergraph."""
        hg = Hypergraph()
        for i in range(100):
            hg.add_vertex(f"init_{i}", label=f"Init {i}")
            
        errors = []
        stop_event = threading.Event()
        
        def writer_thread():
            count = 0
            while not stop_event.is_set() and count < 500:
                try:
                    vid = f"dyn_{random.randint(0, 300)}"
                    hg.add_vertex(vid, label=f"Dynamic Node {vid}")
                    src = f"init_{random.randint(0, 99)}"
                    hg.add_hyperedge([src], [vid], relation="dyn_rel")
                    if count % 25 == 0:
                        hg.prune_decayed_edges(retention_threshold=0.01)
                    if count % 50 == 0:
                        hg.remove_vertex(f"dyn_{random.randint(0, 300)}")
                except Exception as e:
                    errors.append(("writer", e))
                count += 1

        def reader_thread():
            engine = ActivationEngine(hg)
            count = 0
            while not stop_event.is_set() and count < 100:
                try:
                    _ = engine.spread({f"init_{random.randint(0, 99)}": 1.0})
                    _ = engine.match_seeds("Dynamic Node Init")
                except Exception as e:
                    errors.append(("reader", e))
                count += 1

        threads = [
            threading.Thread(target=writer_thread),
            threading.Thread(target=writer_thread),
            threading.Thread(target=writer_thread),
            threading.Thread(target=reader_thread),
            threading.Thread(target=reader_thread),
            threading.Thread(target=reader_thread),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=6.0)
        stop_event.set()

        self.assertEqual(len(errors), 0, f"Race condition errors detected during concurrent execution: {errors}")

    # =========================================================================
    # 5. PNS SENSOR NETWORK & MALFORMED PAYLOADS
    # =========================================================================
    def test_pns_malformed_and_flood_payloads(self):
        """Sends corrupt JSON, raw binary, and rapid packet floods to PNS receiver."""
        hg = Hypergraph()
        synth = PhoneSensorySynthesizer(hg)
        
        # Test free port
        port = 7397
        receiver = PNSSensoryReceiver(host="127.0.0.1", port=port, synthesizer=synth)
        try:
            started = receiver.start()
            self.assertTrue(started)
            time.sleep(0.1)

            # 1. Send garbage binary bytes
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", port))
            s.sendall(b"\x00\xFF\xFE\xFDcorrupted_non_json\n")
            s.close()
            time.sleep(0.05)

            # 2. Send truncated json
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", port))
            s.sendall(b'{"lux": 150, "battery_pct":\n')
            s.close()
            time.sleep(0.05)

            # 3. Test frame building with NaN and Inf
            telem_nan = PhoneSensoryTelemetry(lux=float("nan"), battery_pct=float("inf"), audio_amplitude_db=float("-inf"))
            synth.ingest(telem_nan)
            frame = synth.build_somatic_frame()
            self.assertIn("PNS Phone Sensor:", frame)
            self.assertNotIn("nan", frame.lower())

            self.assertTrue(receiver.running)
            self.assertTrue(receiver._thread.is_alive())
        finally:
            receiver.stop()

    def test_pns_port_conflict_graceful_handling(self):
        """Verifies that port collision does not crash the process."""
        receiver1 = PNSSensoryReceiver(host="127.0.0.1", port=7396)
        receiver2 = PNSSensoryReceiver(host="127.0.0.1", port=7396)
        try:
            r1_ok = receiver1.start()
            self.assertTrue(r1_ok)
            # Second receiver attempts to bind same port
            r2_ok = receiver2.start()
            self.assertFalse(r2_ok)
            self.assertIsNotNone(receiver2.bind_error)
            self.assertFalse(receiver2.running)
        finally:
            receiver1.stop()
            receiver2.stop()

    # =========================================================================
    # 6. BOOT SYNTHESIZER & CORRUPT STATE INGESTION
    # =========================================================================
    def test_boot_synthesizer_corrupt_notes_and_history(self):
        """Boots synthesizer with None, garbage notes, malformed turns, and broken fleet nodes."""
        synthesizer = BootSynthesizer()

        # 1. Test None notes and empty history
        state1 = synthesizer.boot(notes_data=None, chat_history=None)
        self.assertIsInstance(state1, UnifiedCognitiveBootState)
        self.assertEqual(state1.active_topic, "general")

        # 2. Test corrupted notes dict with missing fields and non-dict entries
        dirty_notes = {
            "current_topic": "Security Testing",
            "working_notes": None,
            "notes": [
                {"id": "n1", "content": None},
                "not_a_dict_entry",
                {"id": "n2", "content": "Valid Note", "status": "get_back_to"},
                {"id": "n3", "content": "", "status": 12345},
            ]
        }
        # Corrupted chat history turns
        dirty_history = [
            "invalid_turn_string",
            None,
            {"turn_id": "t1", "role": "user", "text": "hello", "timestamp": float("nan")},
            {"turn_id": "t2", "role": "model", "text": "world", "timestamp": "invalid_ts"},
        ]
        # Malformed fleet snapshot
        dirty_fleet = {
            "nodes": [
                {"node_id": "n_corrupt", "telemetry": "not_a_dict"},
                None,
                {"node_id": "node_nan", "telemetry": {"mem_total_mb": float("nan"), "battery": {"percentage": float("nan")}}},
            ]
        }

        state2 = synthesizer.boot(
            notes_data=dirty_notes,
            chat_history=dirty_history,
            fleet_snapshot=dirty_fleet,
            current_user_prompt="Stress testing boot with dirty inputs",
        )
        self.assertIsInstance(state2, UnifiedCognitiveBootState)
        self.assertEqual(state2.active_topic, "Security Testing")
        self.assertLessEqual(state2.active_slots_count, 7)
        frame = state2.get_unified_boot_frame()
        self.assertIn("UNITIZED MENTAL STATE BOOT", frame)

    # =========================================================================
    # 7. DAEMON SUPERVISOR & CRASH RESILIENCE
    # =========================================================================
    def test_supervisor_corrupted_checkpoint_recovery(self):
        """Forces daemon supervisor to recover from corrupt / half-written checkpoint files."""
        with open(self.ckpt_path, "w", encoding="utf-8") as f:
            f.write("CORRUPTED_JSON_DATA_HALF_WRITTEN { \"turn\": 42, ")

        supervisor = ResilientCognitiveSupervisor(checkpoint_path=self.ckpt_path)
        state, used_fallback = supervisor.execute_query("test query after corruption")
        self.assertIsNotNone(state)
        self.assertTrue(os.path.exists(self.ckpt_path))

    def test_extreme_time_dilation_lapse(self):
        """Tests lapse manager with 10 years of simulated downtime and backward clock skew."""
        mgr = LapseManager(checkpoint_path=self.ckpt_path)
        base_state = CognitiveStateVector(
            session_id="time_test",
            timestamp=1000.0,
            focus_spotlight=[
                FocusItem(concept_id="c1", energy=1.0, primed_hops=1, last_activated=1000.0),
                FocusItem(concept_id="c2", energy=0.5, primed_hops=1, last_activated=1000.0),
            ]
        )
        mgr.save_checkpoint(base_state, now=1000.0)

        # 1. 10 years later (315,360,000 seconds)
        ten_years_later = 1000.0 + 315360000.0
        reconciled_state, lapse_ev = mgr.reconcile_post_lapse(now=ten_years_later)
        self.assertTrue(lapse_ev.restored)
        self.assertGreater(lapse_ev.duration_seconds, 300000000.0)
        self.assertEqual(len(reconciled_state.focus_spotlight), 0)

        # 2. Backward clock skew (now is BEFORE checkpoint heartbeat, e.g. NTP correction)
        clock_skew_now = 500.0
        skew_state, skew_lapse = mgr.reconcile_post_lapse(now=clock_skew_now)
        self.assertTrue(skew_lapse.restored)
        self.assertEqual(skew_lapse.duration_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
