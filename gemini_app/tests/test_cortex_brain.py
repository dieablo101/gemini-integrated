"""
Unit and integration test suite for CortexBrain, Hypergraph, and Subconscious Engine.
"""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from gemini_app.cortex.brain import CortexBrain
from gemini_app.cortex.hypergraph import Hypergraph, Vertex, Hyperedge
from gemini_app.cortex.chat_dissector import ChatDissector, ShardCategory, ShardDomain
from gemini_app.cortex.relational_cortex import RelationalCortex
from gemini_app.cortex.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from gemini_app.cortex.subconscious.novelty_detector import NoveltyDetector
from gemini_app.cortex.subconscious.stillness_gate import StillnessGate
from gemini_app.tools.mind_tools import recall_memory


class TestCortexBrain(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home_dir = Path(self.temp_dir.name)
        self.brain = CortexBrain(home_dir=self.home_dir)

    def tearDown(self):
        self.brain.stop_subconscious()
        self.temp_dir.cleanup()

    def test_hypergraph_primitives(self):
        hg = Hypergraph()
        v1 = hg.add_vertex("v_godot", label="Godot 4", vtype="engine", base_energy=1.5)
        v2 = hg.add_vertex("v_blender", label="Blender 3D", vtype="dcc", base_energy=1.2)
        v3 = hg.add_vertex("v_gltf", label="glTF Exporter", vtype="pipeline", base_energy=1.0)

        self.assertEqual(len(hg.vertices), 3)
        self.assertEqual(hg.get_vertex("v_godot").label, "Godot 4")

        # Directed hyperedge: Blender -> glTF -> Godot
        e = hg.add_hyperedge(
            sources=["v_blender"],
            targets=["v_gltf", "v_godot"],
            relation="asset_export_pipeline",
            weight=0.9,
        )
        self.assertEqual(len(hg.edges), 1)

        # Traversal
        out_neighbors = hg.neighbors("v_blender", direction="outgoing")
        self.assertIn("v_gltf", out_neighbors)
        self.assertIn("v_godot", out_neighbors)

        # Subgraph extraction
        sub = hg.extract_subgraph(["v_blender", "v_gltf"])
        self.assertEqual(len(sub.vertices), 2)

        # Serialization round-trip
        data = hg.to_dict()
        hg_restored = Hypergraph.from_dict(data)
        self.assertEqual(len(hg_restored.vertices), 3)
        self.assertEqual(len(hg_restored.edges), 1)

    def test_chat_dissector_classification(self):
        dissector = ChatDissector()
        
        # Invariant rule test
        text_rule = "Security policy: PBKDF2 must always be used with at least 100000 iterations for passkey encryption."
        cat = dissector.classify_category(text_rule)
        dom = dissector.classify_domain(text_rule)
        self.assertEqual(cat, ShardCategory.INVARIANT_RULE)

        # Technical spec test
        text_spec = "Memory buffer threshold is set to 60fps and port 8080."
        cat_spec = dissector.classify_category(text_spec)
        self.assertEqual(cat_spec, ShardCategory.TECHNICAL_SPEC)

        # Unresolved todo test
        text_todo = "TODO: calibrate reconnect timer precision for satellite links."
        cat_todo = dissector.classify_category(text_todo)
        self.assertEqual(cat_todo, ShardCategory.UNRESOLVED_TODO)

    def test_cortex_brain_ingest_and_recall(self):
        # 1. Ingest turn
        res = self.brain.ingest_turn(
            chat_id="chat_alpha",
            turn_number=1,
            role="user",
            content="We are constructing the Godot Blender asset pipeline with sub-millisecond hypergraph memory.",
        )
        self.assertTrue(res["turn_id"].startswith("chat_alpha_1"))
        self.assertGreater(res["shards_count"], 0)
        self.assertGreater(res["graph_vertices"], 0)

        # 2. Ingest note
        nid = self.brain.ingest_note(
            topic="photon engine",
            content="Photon Engine bridges socket streams directly into Godot scene trees.",
            status="working",
        )
        self.assertTrue(nid.startswith("note:"))

        # 3. Recall
        rec = self.brain.recall("hypergraph", max_results=5)
        self.assertLess(rec["latency_ms"], 10.0, "Recall must be sub-10ms")
        self.assertGreaterEqual(rec["matches_count"], 1)
        self.assertEqual(rec["matches"][0]["chat_id"], "chat_alpha")
        self.assertGreaterEqual(len(rec["graph_associations"]), 1)

        # 4. Integrated mind_tools recall
        tool_rec = recall_memory(
            query="Godot Blender",
            max_results=5,
            cortex_brain=self.brain,
        )
        self.assertIn("graph_associations", tool_rec)
        self.assertIn("relational_shards", tool_rec)
        self.assertGreaterEqual(tool_rec["matches_count"], 1)

    def test_subconscious_epiphany_channel(self):
        channel = EpiphanyChannel(capacity=10)
        packet = EpiphanyPacket(
            packet_id="ep_001",
            spark_name="Cross-Engine Socket Mesh",
            domain_bridge=["3d_pipeline", "fleet_telemetry"],
            feasibility_score=0.92,
            summary="Connect iPad Nomad sculpts via headless Blender websocket to Godot.",
        )
        pushed = channel.push(packet)
        self.assertTrue(pushed)
        self.assertEqual(channel.size(), 1)

        drained = channel.drain_all()
        self.assertEqual(len(drained), 1)
        self.assertEqual(drained[0].spark_name, "Cross-Engine Socket Mesh")
        self.assertEqual(channel.size(), 0)

    def test_brain_persistence(self):
        self.brain.ingest_turn(
            chat_id="chat_beta",
            turn_number=10,
            role="assistant",
            content="Confirming hypergraph persistence across console reboot sessions.",
        )
        saved = self.brain.save_graph()
        self.assertTrue(saved)
        self.assertTrue(self.brain.graph_path.exists())

        # Load fresh brain on same home directory
        fresh_brain = CortexBrain(home_dir=self.home_dir)
        self.assertEqual(len(fresh_brain.graph.vertices), len(self.brain.graph.vertices))
        self.assertEqual(len(fresh_brain.graph.edges), len(self.brain.graph.edges))

    def test_concurrency_safety(self):
        def worker(idx: int):
            for i in range(5):
                self.brain.ingest_turn(
                    chat_id=f"thread_chat_{idx}",
                    turn_number=i,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Concurrent thread {idx} message {i} discussing hypergraph and pipeline.",
                )
                self.brain.recall("thread")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        telemetry = self.brain.get_telemetry()
        self.assertGreater(telemetry["vertices"], 10)
        self.assertGreater(telemetry["edges"], 10)


if __name__ == "__main__":
    unittest.main()
