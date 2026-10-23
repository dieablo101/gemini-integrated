"""
sandbox/mind_twin/tests/test_hypergraph.py

Deterministic mathematical verification of the Attributed Directed Hypergraph primitive.
"""

import math
import time
import unittest
from sandbox.mind_twin.core.hypergraph import Vertex, Hyperedge, Hypergraph


class TestHypergraphPrimitives(unittest.TestCase):
    def setUp(self):
        self.hg = Hypergraph()

    def test_vertex_lifecycle_and_ebbinghaus_decay(self):
        t0 = 1000.0
        v = Vertex(id="concept:act_r", label="ACT-R Theory", created_at=t0, last_accessed=t0)
        
        # Immediate energy
        e0 = v.ebbinghaus_energy(t_now=t0)
        self.assertAlmostEqual(e0, 1.0, places=4)

        # Decay after 200 seconds under alpha=0.005, beta=0.3
        t1 = t0 + 200.0
        expected_retention = math.pow(1.0 + 0.005 * 200.0, -0.3)
        e1 = v.ebbinghaus_energy(t_now=t1)
        self.assertAlmostEqual(e1, expected_retention, places=4)
        self.assertLess(e1, e0)

        # Touch to simulate retrieval and verify energy boost
        v.touch(t_now=t1)
        self.assertEqual(v.access_count, 2)
        e2 = v.ebbinghaus_energy(t_now=t1)
        self.assertGreater(e2, e1)

    def test_hyperedge_multi_source_multi_target(self):
        # Hyperedge linking {iPad node, cellular timeout, commit 999c37b} -> {reverse polling, port 7331}
        self.hg.add_vertex("node:ipad", "iPad Node", vtype="node")
        self.hg.add_vertex("err:timeout", "Socket Timeout", vtype="error")
        self.hg.add_vertex("commit:sha", "Commit 999c37b", vtype="commit")
        self.hg.add_vertex("proto:reverse_poll", "Reverse Polling", vtype="protocol")
        self.hg.add_vertex("port:7331", "Mothership Port 7331", vtype="port")

        edge = self.hg.add_hyperedge(
            sources=["node:ipad", "err:timeout", "commit:sha"],
            targets=["proto:reverse_poll", "port:7331"],
            relation="resolves",
            weight=1.5,
            edge_id="edge_cellular_fix",
        )

        self.assertEqual(edge.id, "edge_cellular_fix")
        self.assertEqual(len(edge.sources), 3)
        self.assertEqual(len(edge.targets), 2)
        self.assertEqual(edge.relation, "resolves")

        # Verify dual indices
        incident_ipad = self.hg.incident_hyperedges("node:ipad", direction="outgoing")
        self.assertIn("edge_cellular_fix", incident_ipad)

        incident_port = self.hg.incident_hyperedges("port:7331", direction="incoming")
        self.assertIn("edge_cellular_fix", incident_port)

        # Verify neighbor traversal
        neighbors_out = self.hg.neighbors("node:ipad", direction="outgoing")
        self.assertEqual(neighbors_out, {"proto:reverse_poll", "port:7331"})

        neighbors_in = self.hg.neighbors("port:7331", direction="incoming")
        self.assertEqual(neighbors_in, {"node:ipad", "err:timeout", "commit:sha"})

    def test_hebbian_plasticity_reinforcement(self):
        edge = Hyperedge(
            id="e1",
            sources={"v1"},
            targets={"v2"},
            weight=1.0,
            last_reinforced=1000.0,
        )

        # Reinforce with high co-activation (a_src=1.0, a_tgt=1.0)
        # Delta w = eta * (a_src * a_tgt) - gamma * w
        # eta = 0.2, gamma = 0.05 -> Delta w = 0.2 - 0.05 = 0.15 -> new weight = 1.15
        new_w = edge.reinforce(
            src_activation=1.0,
            tgt_activation=1.0,
            eta=0.2,
            gamma=0.05,
            t_now=1000.0,
        )
        self.assertAlmostEqual(new_w, 1.15, places=4)
        self.assertEqual(edge.reinforce_count, 2)

    def test_edge_temporal_decay_and_pruning(self):
        t0 = 1000.0
        edge = self.hg.add_hyperedge(
            sources=["s1"],
            targets=["t1"],
            weight=0.1,
            edge_id="e_weak",
        )
        edge.last_reinforced = t0

        # High time delta: 50,000 seconds later
        t_future = t0 + 50000.0
        w_eff = edge.effective_weight(t_now=t_future, alpha=0.01, beta=0.5)
        self.assertLess(w_eff, 0.05)

        # Prune edges below 0.05
        pruned_count = self.hg.prune_decayed_edges(retention_threshold=0.05, t_now=t_future)
        self.assertEqual(pruned_count, 1)
        self.assertIsNone(self.hg.get_hyperedge("e_weak"))

    def test_subgraph_extraction(self):
        self.hg.add_hyperedge(["a", "b"], ["c"], relation="r1", edge_id="e1")
        self.hg.add_hyperedge(["c"], ["d"], relation="r2", edge_id="e2")
        self.hg.add_hyperedge(["x"], ["y"], relation="r3", edge_id="e3")

        sub = self.hg.extract_subgraph(["a", "b", "c"])
        self.assertEqual(len(sub.vertices), 3)
        self.assertEqual(len(sub.edges), 1)
        self.assertIsNotNone(sub.get_hyperedge("e1"))
        self.assertIsNone(sub.get_hyperedge("e2"))
        self.assertIsNone(sub.get_hyperedge("e3"))

    def test_serialization_roundtrip(self):
        self.hg.add_vertex("v1", "Source Vertex", vtype="entity", attributes={"priority": 1})
        self.hg.add_vertex("v2", "Target Vertex", vtype="target")
        self.hg.add_hyperedge(["v1"], ["v2"], relation="leads_to", weight=2.5, edge_id="e_roundtrip")

        serialized = self.hg.to_dict()
        self.assertEqual(serialized["vertex_count"], 2)
        self.assertEqual(serialized["edge_count"], 1)

        reconstructed = Hypergraph.from_dict(serialized)
        self.assertEqual(len(reconstructed.vertices), 2)
        self.assertEqual(len(reconstructed.edges), 1)
        
        edge = reconstructed.get_hyperedge("e_roundtrip")
        self.assertIsNotNone(edge)
        self.assertEqual(edge.weight, 2.5)
        self.assertEqual(edge.relation, "leads_to")
        self.assertEqual(edge.sources, {"v1"})
        self.assertEqual(edge.targets, {"v2"})

    def test_empty_sources_or_targets_raise_error(self):
        with self.assertRaises(ValueError):
            self.hg.add_hyperedge([], ["v2"])
        with self.assertRaises(ValueError):
            self.hg.add_hyperedge(["v1"], [])


if __name__ == "__main__":
    unittest.main()
