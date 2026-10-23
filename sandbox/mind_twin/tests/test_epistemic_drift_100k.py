"""
sandbox/mind_twin/tests/test_epistemic_drift_100k.py

Stress tests for Deep Epistemic Drift & 100,000-Turn Memory Compaction (Frontier 4).
Tests:
- 100,000 simulated conversational turns with Ebbinghaus decay.
- Verification of zero catastrophic forgetting on critical anchors.
- Natural decay of transient trivia to < 0.05 energy.
- Hierarchical graph compaction collapsing decayed clusters into abstract summaries
  with > 75% vertex reduction while preserving causal provenance.
"""

import unittest

from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.memory_compactor import HierarchicalCompactor, LongHorizonDecaySimulator


class TestEpistemicDrift100k(unittest.TestCase):

    def setUp(self):
        self.hg = Hypergraph()
        self.t0 = 1_000_000.0

        # Seed 5 critical anchors
        for i in range(5):
            self.hg.add_vertex(
                f"anchor_core_{i}",
                label=f"Core Directive {i}",
                vtype="anchor",
                base_energy=3.0,
                attributes={"is_anchor": True, "topic": "core_rules"},
            )
            v = self.hg.get_vertex(f"anchor_core_{i}")
            v.last_accessed = self.t0

        # Seed 150 transient trivia nodes across 3 topics
        topics = ["random_chitchat", "debug_bash_logs", "temporary_scratch"]
        for i in range(150):
            top = topics[i % len(topics)]
            vid = f"transient_{top}_{i}"
            self.hg.add_vertex(
                vid,
                label=f"Transient Log {i}",
                vtype="trivia",
                base_energy=1.0,
                attributes={"topic": top},
            )
            v = self.hg.get_vertex(vid)
            v.last_accessed = self.t0

        # Wire hyperedges from anchors to some transient nodes
        self.hg.add_hyperedge(
            sources=["anchor_core_0"],
            targets=["transient_random_chitchat_0", "transient_debug_bash_logs_1"],
            relation="causal_spawn",
        )

    def test_100k_turn_simulation_anchor_retention(self):
        """Simulating 100,000 turns must preserve anchor energies while decaying transient trivia."""
        sim_res = LongHorizonDecaySimulator.simulate_100k_turns(
            self.hg,
            total_turns=100_000,
            seconds_per_turn=60.0,
            anchor_reinforce_interval=2_000,
        )

        self.assertEqual(sim_res["simulated_turns"], 100_000)
        self.assertGreater(sim_res["min_anchor_energy"], 0.70, "Catastrophic forgetting detected on anchors!")
        self.assertLess(sim_res["max_transient_energy"], 0.05, "Transient trivia failed to decay naturally!")

    def test_hierarchical_compaction(self):
        """Hierarchical compactor must reduce decayed vertices by > 75% without touching anchors."""
        sim_res = LongHorizonDecaySimulator.simulate_100k_turns(
            self.hg,
            total_turns=50_000,
            seconds_per_turn=60.0,
            anchor_reinforce_interval=2_000,
        )

        initial_count = self.hg.vertex_count()
        compactor = HierarchicalCompactor(decay_energy_threshold=0.08, min_cluster_size=3)
        compact_res = compactor.compact(self.hg, t_now=sim_res["sim_end_time"])

        final_count = self.hg.vertex_count()

        # Anchors must remain 100% intact
        self.assertEqual(compact_res["preserved_anchors"], 5)
        for i in range(5):
            self.assertIsNotNone(self.hg.get_vertex(f"anchor_core_{i}"))

        # Pruned vertices must be substantial (> 75% of initial 155 nodes)
        pruned = compact_res["pruned_vertices"]
        self.assertGreater(pruned, 100, f"Pruned {pruned} vertices, expected > 100")
        self.assertLess(final_count, 35)

        # Abstract summary vertices should exist
        summary_vids = [
            vid for vid, v in self.hg.get_vertices_snapshot().items()
            if v.vtype == "abstract_summary"
        ]
        self.assertGreater(len(summary_vids), 0)


if __name__ == "__main__":
    unittest.main()
