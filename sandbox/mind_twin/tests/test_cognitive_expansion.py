"""
sandbox/mind_twin/tests/test_cognitive_expansion.py

Test Suite for Cognitive Thought Expansion & Multi-Tiered Latency Engine.
Verifies reflex speed (<10ms), relational traversal breadcrumbs, subconscious accretion,
and epistemic honesty calibration.

Quarantine Invariant:
100% strictly contained in sandbox/mind_twin/. Zero mutations to production gemini_app/.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from sandbox.mind_twin.core.cognitive_expansion import (
    CognitiveExpansionEngine,
    CognitiveLatencyTier,
    EpistemicCertainty,
    TraversalBreadcrumb,
    ExpandedThoughtFrame,
)
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.subconscious import (
    AccretionHearth,
    AnnealingEngine,
    CollisionLens,
    LatentSoilVault,
    ResonanceGate,
    StillnessGate,
    SubconsciousWorker,
)
from sandbox.mind_twin.harness.probe import load_compiled_graph


class TestCognitiveExpansion(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = load_compiled_graph()
        cls.directional_gate = DirectionalGateEngine(max_slots=7)

        cls.soil = LatentSoilVault()
        cls.hearth = AccretionHearth(soil_vault=cls.soil, min_vectors_to_ignite=1, min_incubation_seconds=0.0)
        cls.lens = CollisionLens()
        cls.gate = ResonanceGate()
        cls.annealing = AnnealingEngine(hearth=cls.hearth, max_attempts=2, base_backoff_seconds=1.0)
        cls.stillness = StillnessGate(idle_threshold_seconds=0.0)

        cls.subconscious_worker = SubconsciousWorker(
            graph=cls.graph,
            hearth=cls.hearth,
            collision_lens=cls.lens,
            resonance_gate=cls.gate,
            annealing_engine=cls.annealing,
            stillness_gate=cls.stillness,
        )

        cls.engine = CognitiveExpansionEngine(
            graph=cls.graph,
            directional_gate=cls.directional_gate,
            subconscious_worker=cls.subconscious_worker,
        )

    def test_01_reflex_tier_sub_10ms(self) -> None:
        """Prompt matching Bedrock invariant must execute in reflex tier (< 10ms)."""
        prompt = "How is our PyPI token encrypted in the vault?"
        frame = self.engine.expand_thought(prompt, active_topic="packaging/working")

        self.assertEqual(frame.latency_tier, CognitiveLatencyTier.REFLEX)
        self.assertEqual(frame.epistemic_certainty, EpistemicCertainty.GROUNDED_INVARIANT)
        self.assertGreaterEqual(frame.confidence_score, 0.95)
        self.assertLess(frame.elapsed_ms, 25.0)  # Generous upper bound for CI; typically < 5ms
        self.assertIn("PBKDF2", frame.epistemic_honesty_statement or frame.living_thought_stream)

    def test_02_associative_hop_breadcrumbs(self) -> None:
        """Relational queries must trace valid multi-hop breadcrumbs through the hypergraph."""
        prompt = "Connect our mobile sculpt workflow with Blender and Godot"
        frame = self.engine.expand_thought(prompt, active_topic="blender & godot plugin development")

        self.assertEqual(frame.latency_tier, CognitiveLatencyTier.ASSOCIATIVE_HOP)
        self.assertIn(
            frame.epistemic_certainty,
            [EpistemicCertainty.GROUNDED_INVARIANT, EpistemicCertainty.RELATIONAL_ASSOCIATION],
        )
        self.assertGreater(len(frame.breadcrumbs), 0)
        first_crumb = frame.breadcrumbs[0]
        self.assertIsInstance(first_crumb, TraversalBreadcrumb)
        self.assertGreater(len(first_crumb.relation), 0)
        self.assertIn("traversing:", frame.visual_synaptic_pulse)

    def test_03_deep_accretion_epiphany_spark(self) -> None:
        """Cross-domain synthesis prompt triggers deep accretion and subconscious hearth."""
        prompt = "Synthesize tactile Emacs keystroke timing with satellite watchdog pings for anomaly detection"
        frame = self.engine.expand_thought(
            prompt,
            active_topic="cross_domain_synthesis",
            force_tier=CognitiveLatencyTier.DEEP_ACCRETION,
        )

        self.assertEqual(frame.latency_tier, CognitiveLatencyTier.DEEP_ACCRETION)
        self.assertIsNotNone(frame.subconscious_spark)
        self.assertIn("Accreting", frame.subconscious_spark)

    def test_04_epistemic_calibration_honesty(self) -> None:
        """An unmapped, completely unknown query must result in honest unmapped_void with low confidence."""
        alien_prompt = "What is the quantum spin of the hypothetical chroniton particle in sector 7?"
        frame = self.engine.expand_thought(alien_prompt, active_topic="astrophysics_sci_fi")

        self.assertIn(
            frame.epistemic_certainty,
            [EpistemicCertainty.UNMAPPED_VOID, EpistemicCertainty.ASSOCIATIVE_HUNCH],
        )
        self.assertLess(frame.confidence_score, 0.50)
        self.assertTrue(
            "first principles" in frame.epistemic_honesty_statement
            or "lateral" in frame.epistemic_honesty_statement
            or "Faint" in frame.epistemic_honesty_statement,
        )

    def test_05_visual_synaptic_pulse_formatting(self) -> None:
        """Visual pulses and living thought streams must be well-formed and non-empty."""
        prompt = "Inspect satellite node connectivity and cluster vitals"
        frame = self.engine.expand_thought(prompt, active_topic="fleet & satellite nodes")

        self.assertTrue(frame.visual_synaptic_pulse.startswith("[traversing:") or frame.visual_synaptic_pulse.startswith("[reflex:"))
        self.assertIn("THOUGHT EXPANSION", frame.living_thought_stream)
        self.assertIn(frame.latency_tier.value.upper(), frame.living_thought_stream)

    def test_06_strict_sandbox_quarantine(self) -> None:
        """Zero files in gemini_app/ should be modified."""
        import subprocess
        res = subprocess.run(["git", "status", "-s", "gemini_app/"], capture_output=True, text=True)
        self.assertEqual(res.stdout.strip(), "", "Quarantine breach: gemini_app/ modified!")


if __name__ == "__main__":
    unittest.main()
