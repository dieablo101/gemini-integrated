"""
sandbox/mind_twin/tests/test_activation.py

Unit tests for ACT-R Spreading Activation Engine.
Verifies seed matching, spreading activation across hyperedges,
Hebbian reinforcement, attention thresholding, and invariant distillation.
"""

import unittest
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.activation import ActivationEngine


class TestActivationEngine(unittest.TestCase):

    def setUp(self):
        self.graph = Hypergraph()

        # Build a small causal network modeling an iPad socket incident
        self.graph.add_vertex("node_ipad", label="iPad iSH Node", vtype="satellite")
        self.graph.add_vertex("wan_carrier", label="Cellular WAN Carrier NAT", vtype="network")
        self.graph.add_vertex("err_timeout", label="Errno 110 Connection Timed Out", vtype="error")
        self.graph.add_vertex("rev_poll", label="Reverse Polling Architecture", vtype="solution")
        self.graph.add_vertex("port_7331", label="Mothership Port 7331", vtype="endpoint")
        self.graph.add_vertex("unrelated_concept", label="Unrelated Baking Cake", vtype="concept")

        # Hyperedge 1: (node_ipad + wan_carrier) -> causes -> (err_timeout)
        self.graph.add_hyperedge(
            sources=["node_ipad", "wan_carrier"],
            targets=["err_timeout"],
            relation="causes",
            weight=1.2,
            edge_id="edge_cause",
        )

        # Hyperedge 2: (err_timeout) -> resolved_by -> (rev_poll, port_7331)
        self.graph.add_hyperedge(
            sources=["err_timeout"],
            targets=["rev_poll", "port_7331"],
            relation="resolved_by",
            weight=1.5,
            edge_id="edge_resolve",
        )

        self.engine = ActivationEngine(self.graph)

    def test_seed_matching(self):
        query = "Why did iPad cellular connection fail?"
        seeds = self.engine.match_seeds(query)
        self.assertIn("node_ipad", seeds)
        self.assertNotIn("unrelated_concept", seeds)

    def test_spreading_activation_two_hops(self):
        # Inject energy directly into iPad and WAN Carrier
        seeds = {"node_ipad": 1.0, "wan_carrier": 1.0}
        result = self.engine.spread(seeds, query="iPad timeout query", max_hops=2, threshold=0.1)

        # In hop 1: err_timeout should be activated
        self.assertIn("err_timeout", result.node_activations)

        # In hop 2: rev_poll and port_7331 should be activated
        self.assertIn("rev_poll", result.node_activations)
        self.assertIn("port_7331", result.node_activations)

        # Unrelated concepts should have ZERO activation
        self.assertNotIn("unrelated_concept", result.node_activations)

        # Invariants should capture the causal chain
        self.assertGreaterEqual(len(result.invariants), 2)
        summary_text = " ".join([inv.summary for inv in result.invariants])
        self.assertIn("causes", summary_text)
        self.assertIn("resolved_by", summary_text)

    def test_insufficient_antecedents_dampens_spread(self):
        # If only one source is active in a multi-source hyperedge, activation is attenuated
        seeds = {"node_ipad": 0.1, "wan_carrier": 0.0}
        result = self.engine.spread(seeds, threshold=0.4)
        # Should NOT reach the target above threshold 0.4
        self.assertNotIn("err_timeout", result.node_activations)

    def test_hebbian_reinforcement_on_activation(self):
        edge = self.graph.get_hyperedge("edge_cause")
        initial_weight = edge.weight
        seeds = {"node_ipad": 1.0, "wan_carrier": 1.0}
        self.engine.spread(seeds)
        # Traversal should reinforce the edge weight
        self.assertGreater(edge.weight, initial_weight)


if __name__ == "__main__":
    unittest.main()
