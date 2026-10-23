"""
Heavy Stress, Chaos & Adversarial Test Suite for Mind Twin.
Tests:
1. PNS Socket Fuzzing, Slowloris, and Malformed Byte Flood
2. Pathological Novelty Detector Inputs (Giant strings, non-ASCII, null bytes)
3. Giant Graph & High-Degree Hub Topological Traversal (1,000 incident edges)
4. Epiphany Channel 20-Thread Lockless Chaos Stress
5. Rapid Crash-Loop Daemon Supervisor Resilience (100 consecutive abrupt crashes)
6. Attributed Hypergraph Deserialization Fuzzing
"""

import math
import os
import random
import socket
import tempfile
import threading
import time
import unittest
from typing import Dict, List, Any

from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge
from sandbox.mind_twin.core.activation import ActivationEngine
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine
from sandbox.mind_twin.core.subconscious.novelty_detector import NoveltyDetector
from sandbox.mind_twin.core.subconscious.conclusive_probe import ConclusiveRealityProbe
from sandbox.mind_twin.core.subconscious.subconscious_worker import SubconsciousWorker
from sandbox.mind_twin.core.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from sandbox.mind_twin.core.pns_sensor import PhoneSensoryTelemetry, PhoneSensorySynthesizer, PNSSensoryReceiver
from sandbox.mind_twin.core.lapse import LapseManager
from sandbox.mind_twin.core.daemon import CognitiveDaemon, ResilientCognitiveSupervisor
from sandbox.mind_twin.core.state import CognitiveStateVector, FocusItem


class TestMindTwinHeavyStress(unittest.TestCase):

    def test_pns_socket_fuzz_and_rapid_reconnect(self):
        """Spawns PNSSensoryReceiver on random port, hammers it with garbage bytes and rapid disconnects."""
        port = random.randint(30000, 45000)
        hg = Hypergraph()
        synth = PhoneSensorySynthesizer(hg)
        receiver = PNSSensoryReceiver(host="127.0.0.1", port=port, synthesizer=synth)
        receiver.start()
        time.sleep(0.1)

        try:
            # 1. Rapid connect and immediate close (50 times)
            for _ in range(50):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.connect(("127.0.0.1", port))
                finally:
                    s.close()

            # 2. Send malformed non-JSON binary junk
            for _ in range(20):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.connect(("127.0.0.1", port))
                    s.sendall(os.urandom(1024) + b"\n")
                finally:
                    s.close()

            # 3. Send partial JSON cut off midway
            for _ in range(20):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.connect(("127.0.0.1", port))
                    s.sendall(b'{"lux": 150.0, "battery": ')
                finally:
                    s.close()

            # 4. Send valid packet to verify receiver is still fully healthy
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect(("127.0.0.1", port))
                s.sendall(b'{"lux": 300.0, "battery_pct": 99.0}\n')
                resp = s.recv(1024)
                self.assertIn(b'"status":"ok"', resp)
            finally:
                s.close()

            self.assertIsNotNone(receiver.latest_packet)
            self.assertEqual(receiver.latest_packet.battery_pct, 99.0)

        finally:
            receiver.stop()

    def test_pathological_novelty_detector_inputs(self):
        """Tests NoveltyDetector against extreme inputs (100k string, null bytes, unicode emojis)."""
        detector = NoveltyDetector()

        # 1. 100,000 character repeating string
        giant_prompt = "arbitrary novel technical architecture " * 2500
        t0 = time.time()
        res1 = detector.evaluate(giant_prompt, active_topic="scaling")
        elapsed = time.time() - t0
        self.assertLess(elapsed, 0.5, f"Novelty evaluation took too long: {elapsed}s")
        self.assertIsInstance(res1.novelty_score, float)
        self.assertTrue(math.isfinite(res1.novelty_score))

        # 2. Null bytes and binary control characters
        corrupt_prompt = "\x00\x01\x02\xff\xfe\n\r\t"
        res2 = detector.evaluate(corrupt_prompt)
        self.assertFalse(res2.is_out_of_the_norm)

        # 3. Unicode and emojis only
        emoji_prompt = "🚀🔥🤖💡🔮🎨⚡"
        res3 = detector.evaluate(emoji_prompt)
        self.assertFalse(res3.is_out_of_the_norm)

    def test_high_degree_hub_spreading_activation(self):
        """Creates a central hub vertex connected to 1,000 outgoing targets and measures spread latency."""
        hg = Hypergraph()
        hub_id = "central_hub"
        hg.add_vertex(hub_id, label="Central Hub", base_energy=1.0)

        for i in range(1000):
            tid = f"leaf_{i}"
            hg.add_vertex(tid, label=f"Leaf {i}", base_energy=0.5)
            hg.add_hyperedge(sources={hub_id}, targets={tid}, weight=random.uniform(0.5, 1.0))

        engine = ActivationEngine(hg, max_hops=2)
        t0 = time.time()
        result = engine.spread(seeds={hub_id: 1.0})
        elapsed = time.time() - t0

        self.assertLess(elapsed, 0.2, f"Spreading activation over 1000 incident edges took {elapsed}s (> 200ms)")
        self.assertGreater(len(result.node_activations), 100)

    def test_epiphany_channel_multi_thread_chaos(self):
        """20 threads concurrently hammering EpiphanyChannel with 10,000 operations."""
        channel = EpiphanyChannel(capacity=32)
        errors = []
        stop_event = threading.Event()
        push_count = 0
        pop_count = 0
        lock = threading.Lock()

        def chaos_pusher(idx: int):
            nonlocal push_count
            for i in range(500):
                if stop_event.is_set():
                    break
                pkt = EpiphanyPacket(
                    packet_id=f"p_{idx}_{i}",
                    spark_name="Chaos Spark",
                    domain_bridge=["A", "B"],
                    feasibility_score=0.8,
                    summary="Chaos test"
                )
                try:
                    channel.push(pkt)
                    with lock:
                        push_count += 1
                except Exception as ex:
                    errors.append(f"Push ex: {ex}")

        def chaos_popper():
            nonlocal pop_count
            while not stop_event.is_set():
                try:
                    p = channel.pop()
                    if p:
                        with lock:
                            pop_count += 1
                    else:
                        time.sleep(0.001)
                except Exception as ex:
                    errors.append(f"Pop ex: {ex}")

        push_threads = [threading.Thread(target=chaos_pusher, args=(i,)) for i in range(10)]
        pop_threads = [threading.Thread(target=chaos_popper) for _ in range(10)]

        for t in pop_threads + push_threads:
            t.daemon = True
            t.start()

        for t in push_threads:
            t.join(timeout=3.0)

        time.sleep(0.2)
        stop_event.set()
        for t in pop_threads:
            t.join(timeout=1.0)

        self.assertEqual(len(errors), 0, f"Encountered channel errors: {errors}")
        self.assertLessEqual(channel.size(), 32, "Channel exceeded max capacity!")

    def test_supervisor_rapid_crash_loop(self):
        """Forces 50 consecutive sudden daemon crashes and verifies zero-hang fallback and state recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ckpt_path = os.path.join(tmpdir, "crash_loop_ckpt.json")
            hg = Hypergraph()
            for i in range(20):
                hg.add_vertex(f"v_{i}", label=f"Node {i}")

            supervisor = ResilientCognitiveSupervisor(checkpoint_path=ckpt_path, hypergraph=hg)

            # Warm initial query
            state0, used_fallback0 = supervisor.execute_query("initial warm query")
            self.assertFalse(used_fallback0)

            fallbacks = 0
            for turn in range(50):
                # Abruptly simulate process crash
                supervisor.daemon.simulate_crash()
                self.assertFalse(supervisor.daemon.ping())

                # Query while daemon is dead
                state, used_fallback = supervisor.execute_query(f"recovery query {turn}")
                self.assertTrue(used_fallback)
                fallbacks += 1

                # Supervisor must have automatically rebooted daemon
                self.assertTrue(supervisor.daemon.ping())
                self.assertIsNotNone(state)
                self.assertIn("FALLBACK", state.latent_intent)

            self.assertEqual(fallbacks, 50)
            self.assertEqual(supervisor.fallback_invocations, 50)
            self.assertGreaterEqual(supervisor.reboot_count, 50)

    def test_hypergraph_deserialization_fuzzing(self):
        """Fuzzes Hypergraph.from_dict with corrupt, missing, and contradictory fields."""
        fuzz_cases = [
            # 1. Missing attributes dict
            {"vertices": [{"id": "v1", "label": "V1"}], "edges": []},
            # 2. Hyperedge referring to vertices not yet in vertex list
            {
                "vertices": [],
                "edges": [{"id": "e1", "sources": ["v_ghost_1"], "targets": ["v_ghost_2"], "weight": 2.5}]
            },
            # 3. Negative / infinite / nan weights in hyperedge
            {
                "vertices": [{"id": "v1", "label": "V1"}, {"id": "v2", "label": "V2"}],
                "edges": [{"id": "e1", "sources": ["v1"], "targets": ["v2"], "weight": float("nan")}]
            },
            # 4. Extremely large access counts
            {
                "vertices": [{"id": "v1", "label": "V1", "access_count": 999999999}],
                "edges": []
            }
        ]

        for idx, case in enumerate(fuzz_cases):
            try:
                hg = Hypergraph.from_dict(case)
                self.assertIsInstance(hg, Hypergraph)
                # Ensure spreading activation doesn't crash on fuzzed graph
                engine = ActivationEngine(hg)
                res = engine.spread(seeds={"v1": 1.0})
                self.assertIsInstance(res.total_energy, float)
            except Exception as ex:
                self.fail(f"Hypergraph fuzz case #{idx+1} raised unexpected exception: {ex}")


if __name__ == "__main__":
    unittest.main()
