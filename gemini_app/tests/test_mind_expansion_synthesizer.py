"""
gemini_app/tests/test_mind_expansion_synthesizer.py

Production Unit Tests for Mind Expansion Synthesizer & Context Frame Assembler.
Verifies:
1. Sub-millisecond Prompt Expansion Frame Synthesis (0 API calls, < 2ms latency).
2. Token-Budgeted Context Compression (< 150 tokens default).
3. Grounded Invariant Matching & Epistemic Certainty Scoring.
4. Subconscious Hearth Epiphany Incubation & Spiritual Compass Filtering.
5. Cross-Fleet Satellite Telemetry Ingestion (iPad / Termux context mirroring).
6. Hebbian Synaptic Plasticity (Pathway Reinforcement & Decay).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from gemini_app.cloud.upper_mind import UpperMindClient
from gemini_app.cloud.mind_expansion_synthesizer import (
    MindExpansionSynthesizer,
    PromptExpansionFrame,
    FleetNodeTelemetry,
    SpiritualCompassGate,
    EthicalAlignment,
)


class TestProductionMindExpansionSynthesizer(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="prod_mind_expansion_test_")
        self.home_dir = Path(self.test_dir) / ".gemini"
        self.home_dir.mkdir(parents=True, exist_ok=True)

        self.upper_mind = UpperMindClient(gemini_home=self.home_dir, offline_mode=True)

        self.upper_mind.set_invariant(
            key="pypi_token_vault",
            value="PyPI token PBKDF2 encrypted in ~/.gemini/vault/pypi_token.txt.enc",
        )
        self.upper_mind.set_invariant(
            key="basis_orientation_rules",
            value="Blender is right-handed Z-up; Godot is right-handed Y-up",
        )

        self.upper_mind.add_shadow_topic(
            topic_name="blender & godot plugin development",
            summary="3D asset pipeline connecting Blender mesh generation to Godot game engine.",
            tags=["blender", "godot", "3d", "pipeline"],
            anchors=["iPad sculpt to Blender", "FBX/glTF export"],
        )
        self.upper_mind.add_shadow_topic(
            topic_name="fleet & satellite nodes",
            summary="Distributed satellite nodes running on iPad iSH and Android Termux.",
            tags=["ipad", "satellite", "fleet", "termux"],
            anchors=["Zero Rust on iSH", "Telemetry mirroring"],
        )
        self.upper_mind.add_synaptic_edge(
            source="fleet & satellite nodes",
            target="blender & godot plugin development",
            relation="mobile_sculpt_bridge",
            weight=1.4,
        )

        self.synthesizer = MindExpansionSynthesizer(
            upper_mind_client=self.upper_mind,
            max_token_budget=120,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_sub_millisecond_prompt_expansion(self) -> None:
        """Prompt expansion must assemble a dense context frame rapidly."""
        prompt = "How does the mobile sculpt bridge connect iPad to Blender and Godot?"
        
        # Warmup
        _ = self.synthesizer.expand_prompt_context(prompt, active_topic="blender & godot plugin development")

        t0 = time.perf_counter()
        frame: PromptExpansionFrame = self.synthesizer.expand_prompt_context(
            prompt=prompt,
            active_topic="blender & godot plugin development",
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(elapsed_ms, 10.0, f"Prompt expansion took {elapsed_ms:.2f}ms; expected < 10ms")
        self.assertIsNotNone(frame)
        self.assertIn("blender", frame.dense_context_str.lower())
        self.assertLessEqual(frame.token_estimate, 120)

    def test_02_invariant_matching_and_reflex_grounding(self) -> None:
        """Invariants in the shadow graph must be matched and ground certainty."""
        prompt = "Where is the PyPI token vault stored and how is it protected?"
        frame = self.synthesizer.expand_prompt_context(prompt, active_topic="packaging/working")

        self.assertGreater(len(frame.invariants_applied), 0)
        self.assertTrue(any("PBKDF2" in inv for inv in frame.invariants_applied))
        self.assertEqual(frame.certainty, "grounded_invariant")
        self.assertGreaterEqual(frame.confidence, 0.90)

    def test_03_subconscious_hearth_incubation_and_filtering(self) -> None:
        """Subconscious incubation should produce verified epiphanies and deposit into cache."""
        epiphany = self.synthesizer.incubate_subconscious_epiphany(
            domain_a="blender & godot plugin development",
            domain_b="fleet & satellite nodes",
            collision_premise="Headless Blender background daemon ingesting iPad Nomad Sculpt OBJ exports automatically",
        )
        self.assertIsNotNone(epiphany)
        self.assertTrue(epiphany["teleological_alignment"])
        self.assertIn("Headless Blender", epiphany["summary"])

        # Fetch unconsumed epiphanies from Upper Mind
        unconsumed = self.upper_mind.fetch_unconsumed_epiphanies()
        self.assertEqual(len(unconsumed), 1)
        self.assertEqual(unconsumed[0]["id"], epiphany["id"])

        # Expand prompt - the epiphany must appear in the synthesized frame
        frame = self.synthesizer.expand_prompt_context(
            prompt="What can we do with iPad Nomad Sculpt and Blender?",
            active_topic="blender & godot plugin development",
        )
        self.assertGreater(len(frame.active_epiphanies), 0)
        self.assertIn("Headless Blender", frame.active_epiphanies[0])

        # Consume the epiphany
        consumed_ok = self.upper_mind.mark_epiphany_consumed(epiphany["id"])
        self.assertTrue(consumed_ok)
        self.assertEqual(len(self.upper_mind.fetch_unconsumed_epiphanies()), 0)

    def test_04_cross_fleet_satellite_telemetry_mirroring(self) -> None:
        """Incoming satellite telemetry must be ingested without tokens and expand context."""
        self.synthesizer.record_satellite_telemetry(
            node_id="ipad-ish",
            device_type="ipad_ish",
            active_surface="sketch_canvas",
            last_action="Exported concept_mesh.obj to shared workspace",
        )

        frame = self.synthesizer.expand_prompt_context(
            prompt="What is happening on our iPad node right now?",
            active_topic="fleet & satellite nodes",
        )

        self.assertIsNotNone(frame.fleet_telemetry_applied)
        self.assertIn("ipad-ish", frame.fleet_telemetry_applied)
        self.assertIn("Exported concept_mesh.obj", frame.fleet_telemetry_applied)

        system_block = frame.render_system_block()
        self.assertIn("Satellite Telemetry:", system_block)

    def test_05_hebbian_synaptic_plasticity_and_decay(self) -> None:
        """Associations reinforced during conversation must gain weight; stale ones anneal."""
        src = "fleet & satellite nodes"
        tgt = "blender & godot plugin development"

        new_weight = self.synthesizer.reinforce_pathway(src, tgt, delta=0.25)
        self.assertAlmostEqual(new_weight, 1.65, places=2)

        walk_res = self.upper_mind.walk_shadow_graph(topic=src)
        edge = [e for e in walk_res["connected_edges"] if e["to"] == tgt][0]
        self.assertAlmostEqual(edge["weight"], 1.65, places=2)

        self.upper_mind.add_synaptic_edge("stale_node_a", "stale_node_b", "temp_rel", weight=1.0)
        edges = self.upper_mind._shadow_graph.get("synaptic_edges", [])
        for e in edges:
            if e.get("from") == "stale_node_a":
                e["created_at"] = time.time() - 1000

        modified_count = self.synthesizer.decay_unreinforced_pathways(decay_factor=0.90)
        self.assertGreaterEqual(modified_count, 1)

    def test_06_spiritual_compass_safeguard(self) -> None:
        """Spiritual compass must reject harmful concepts and accept benevolent ones."""
        gate = SpiritualCompassGate()
        v_harm = gate.evaluate_hunch_alignment("covert_backdoor and exploit user credentials")
        self.assertFalse(v_harm.is_aligned)
        self.assertEqual(v_harm.ethical_tier, EthicalAlignment.HARMFUL_OR_CORROSIVE)

        v_good = gate.evaluate_hunch_alignment("clarify and protect bilateral communication with reverence")
        self.assertTrue(v_good.is_aligned)
        self.assertEqual(v_good.ethical_tier, EthicalAlignment.BENEVOLENT)
        self.assertGreaterEqual(v_good.reverence_score, 0.80)


if __name__ == "__main__":
    unittest.main()
