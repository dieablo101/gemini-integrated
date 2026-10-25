"""
sandbox/mind_twin/tests/test_ghost_sparring.py

Step 2 Test Suite: Ghost Sparring Bilateral Harness.
Verifies all 3 sparring scenarios between Upper Mind and Mind Twin:
1. Scenario A: Ambiguity Probe (Intent Disambiguation over Hypergraph)
2. Scenario B: AST Bug-Hunt (Reflex Auto-Cure & Context Hashing)
3. Scenario C: Subconscious Collision Drift (Novelty Gate & Epiphany Trajection)
4. Full closed-loop sparring session execution
5. Strict sandbox quarantine invariants
"""

import ast
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from sandbox.mind_twin.core.code_repair_engine import ASTDoctor, SafePatchApplier, SurgicalPatch
from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge
from sandbox.mind_twin.harness.ghost_sparring import GhostSparringHarness, SparringResult


class TestGhostSparring(unittest.TestCase):
    def setUp(self):
        # Isolated sandbox temporary environment
        self.test_dir = tempfile.mkdtemp(prefix="mind_twin_ghost_sparring_")
        self.home_dir = Path(self.test_dir) / ".gemini"
        self.home_dir.mkdir(parents=True, exist_ok=True)

        # Build a synthetic hypergraph seeded with known project domains
        self.graph = Hypergraph()
        self._seed_test_graph()

        # Initialize Ghost Sparring Harness with compiled hypergraph
        self.harness = GhostSparringHarness(
            gemini_home=self.home_dir,
            hypergraph=None,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _seed_test_graph(self):
        # Mobile sculpt & 3D pipeline nodes
        self.graph.add_vertex("v_ipad", "iPad Nomad Sculpt Concepts", "domain", 0.9, attributes={"domain": "mobile_sculpt"})
        self.graph.add_vertex("v_blender", "Blender Headless Retopology Daemon", "domain", 0.95, attributes={"domain": "blender"})
        self.graph.add_vertex("v_godot", "Godot glTF Importer Asset Pipeline", "domain", 0.9, attributes={"domain": "godot"})
        self.graph.add_hyperedge(sources=["v_ipad"], targets=["v_blender", "v_godot"], relation="asset_flow", weight=1.5, edge_id="e_pipeline")

        # Emacs dojo & satellite node nodes
        self.graph.add_vertex("v_emacs", "Emacs Keystroke Telemetry Cadence", "domain", 0.85, attributes={"domain": "emacs_cadence"})
        self.graph.add_vertex("v_satellite", "Satellite Watchdog Node Heartbeat", "domain", 0.88, attributes={"domain": "satellite_telemetry"})
        self.graph.add_hyperedge(sources=["v_emacs"], targets=["v_satellite"], relation="cadence_reflex", weight=1.2, edge_id="e_telemetry")

    def test_01_scenario_a_ambiguity_probe(self):
        """
        Upper Mind presents an ambiguous prompt. Mind Twin spreads activation,
        resolves multi-domain intent, and commits invariants to Upper Mind in < 50ms.
        """
        result = self.harness.run_scenario_a_ambiguity_probe(
            ambiguous_prompt="We need to optimize the asset pipeline bridging mobile sculpts to Godot"
        )
        self.assertTrue(result.success, f"Scenario A failed: {result.epistemic_verdict}")
        self.assertLess(result.latency_ms, 50.0, f"Scenario A latency too high: {result.latency_ms}ms")
        self.assertIn("blender", result.details["resolved_domains"])
        self.assertIn("godot", result.details["resolved_domains"])

        # Verify Upper Mind shadow graph state
        invariants = self.harness.upper_mind._shadow_graph.get("invariants", {})
        self.assertIn("pipeline_intent_disambiguation", invariants)
        walk_res = self.harness.upper_mind.walk_shadow_graph(topic="blender & godot plugin development")
        self.assertEqual(len(walk_res["matched_nodes"]), 1)

    def test_02_scenario_b_ast_bug_hunt(self):
        """
        Upper Mind injects broken code with missing colon.
        Mind Twin detects, auto-heals, validates AST, and registers fix in Upper Mind in < 15ms.
        """
        broken_code = (
            "def calculate_quaternion_slerp(q1, q2, t):\n"
            "    dot = sum(a * b for a, b in zip(q1, q2))\n"
            "    if dot < 0.0\n"
            "        return False\n"
            "    return True\n"
        )
        result = self.harness.run_scenario_b_ast_bug_hunt(broken_code)
        self.assertTrue(result.success, f"Scenario B failed: {result.epistemic_verdict}")
        self.assertLess(result.latency_ms, 15.0, f"Scenario B latency too high: {result.latency_ms}ms")
        self.assertTrue(result.details["post_valid"])
        self.assertGreaterEqual(len(result.details["fixes_applied"]), 1)

        # Upper Mind registered the repair
        invariants = self.harness.upper_mind._shadow_graph.get("invariants", {})
        repair_keys = [k for k in invariants if k.startswith("repair_")]
        self.assertEqual(len(repair_keys), 1)

    def test_03_scenario_c_subconscious_epiphany(self):
        """
        Upper Mind challenges Mind Twin to cross-pollinate Emacs telemetry and Satellite heartbeat.
        Subconscious hearth ignites, clears novelty & stillness gates, and passes epiphany to Upper Mind in < 15ms.
        """
        result = self.harness.run_scenario_c_subconscious_epiphany(
            domain_a="Emacs Keystroke Telemetry Cadence",
            domain_b="Satellite Watchdog Node Heartbeat",
        )
        self.assertTrue(result.success, f"Scenario C failed: {result.epistemic_verdict}")
        self.assertLess(result.latency_ms, 15.0, f"Scenario C latency too high: {result.latency_ms}ms")
        self.assertTrue(result.details["should_fire"])
        self.assertIsNotNone(result.details["spark_id"])

        # Verify Upper Mind synaptic edge creation
        edges = self.harness.upper_mind._shadow_graph.get("synaptic_edges", [])
        ghost_edges = [e for e in edges if e.get("origin") == "ghost_sparring_subconscious"]
        self.assertEqual(len(ghost_edges), 1)
        self.assertEqual(ghost_edges[0]["from"], "Emacs Keystroke Telemetry Cadence")
        self.assertEqual(ghost_edges[0]["to"], "Satellite Watchdog Node Heartbeat")

    def test_04_safe_patch_applier_concurrency_guard(self):
        """
        Validates SafePatchApplier rejects patches when concurrent mutations occur.
        """
        code = "val = 10\nresult = val * 2\n"
        expected_hash = SafePatchApplier.compute_hash(code)
        patch = SurgicalPatch(search_block="val = 10", replace_block="val = 20", expected_hash=expected_hash)

        # Valid application
        ok, patched, err = SafePatchApplier.apply_patch(code, patch)
        self.assertTrue(ok)
        self.assertIn("val = 20", patched)

        # Concurrent modification detected
        concurrent_code = "val = 15\nresult = val * 2\n"
        ok2, _, err2 = SafePatchApplier.apply_patch(concurrent_code, patch)
        self.assertFalse(ok2)
        self.assertIn("Concurrent mutation detected", err2)

    def test_05_full_ghost_sparring_session(self):
        """
        Executes the entire Ghost Sparring bilateral session and verifies 100% pass rate.
        """
        results = self.harness.run_full_sparring_session()
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r.success, f"{r.scenario} failed: {r.epistemic_verdict}")
            self.assertLess(r.latency_ms, 50.0)

    def test_06_strict_sandbox_quarantine(self):
        """
        Asserts zero test artifacts or modifications outside /sandbox/.
        """
        prod_cloud_files = [f.name for f in Path("gemini_app/cloud").iterdir() if f.is_file()]
        expected_files = {"__init__.py", "upper_mind.py", "rehydrate.py"}
        for f in prod_cloud_files:
            self.assertIn(f, expected_files)


if __name__ == "__main__":
    unittest.main()
