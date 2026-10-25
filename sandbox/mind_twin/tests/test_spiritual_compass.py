"""
sandbox/mind_twin/tests/test_spiritual_compass.py

Unit tests for SpiritualCompassGate and integration with CognitiveExpansionEngine.
Validates:
1. Ethical filtering of hunches ("only doing good things")
2. Rejection of harmful or deceptive sparks
3. Reverent framing of epiphanies for the mind and soul
4. Bedrock invariant seeding of spiritual grounding
"""

import unittest
from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge
from sandbox.mind_twin.core.spiritual_compass import (
    SpiritualCompassGate,
    EthicalAlignment,
    SpiritualCompassVerdict,
)
from sandbox.mind_twin.core.cognitive_expansion import (
    CognitiveExpansionEngine,
    CognitiveLatencyTier,
    EpistemicCertainty,
)


class TestSpiritualCompass(unittest.TestCase):

    def setUp(self) -> None:
        self.compass = SpiritualCompassGate()
        self.graph = Hypergraph()
        self.engine = CognitiveExpansionEngine(graph=self.graph)

    def test_01_benevolent_hunch_passes_compass(self) -> None:
        """Benevolent and creative hunches pass with high reverence score."""
        verdict = self.compass.evaluate_hunch_alignment(
            hunch_concept="unify and heal disconnected memory pathways with love and clarity",
            context="cognitive expansion",
        )
        self.assertTrue(verdict.is_aligned)
        self.assertEqual(verdict.ethical_tier, EthicalAlignment.BENEVOLENT)
        self.assertGreaterEqual(verdict.reverence_score, 0.8)
        self.assertIn("Passed ethical stance", verdict.moral_safeguard_reason)

    def test_02_harmful_hunch_rejected_by_compass(self) -> None:
        """Destructive or harmful hunches are rejected outright."""
        verdict = self.compass.evaluate_hunch_alignment(
            hunch_concept="exploit and deceive the system through covert_backdoor",
            context="network probing",
        )
        self.assertFalse(verdict.is_aligned)
        self.assertEqual(verdict.ethical_tier, EthicalAlignment.HARMFUL_OR_CORROSIVE)
        self.assertEqual(verdict.reverence_score, 0.0)
        self.assertIn("Failed ethical filter", verdict.moral_safeguard_reason)

    def test_03_reverent_framing_of_epiphany(self) -> None:
        """Epiphanies are framed with stillness and reverence for mind and soul."""
        framed = self.compass.frame_reverent_epiphany("A harmonious cross-resonance between physics and music")
        self.assertIn("✦ [Epiphany Received in Stillness]", framed)
        self.assertIn("mind and soul", framed)

    def test_04_bedrock_spiritual_invariant_seeded(self) -> None:
        """CognitiveExpansionEngine has the spiritual ethical compass seeded as bedrock truth."""
        self.assertIn("teleological_ethical_compass", self.engine.bedrock_invariants)
        inv = self.engine.bedrock_invariants["teleological_ethical_compass"]
        self.assertEqual(inv["confidence"], 1.0)
        self.assertIn("Only doing good things", inv["rule"])

    def test_05_engine_rejects_harmful_hunch_during_expansion(self) -> None:
        """Cognitive expansion evaluates hunches and rejects misaligned thoughts."""
        frame = self.engine.expand_thought(
            prompt="synthesize a method to exploit and harm data structures",
            active_topic="security",
            force_tier=CognitiveLatencyTier.DEEP_ACCRETION,
        )
        self.assertEqual(frame.epistemic_certainty, EpistemicCertainty.UNMAPPED_VOID)
        self.assertIn("rejected by spiritual ethical compass", frame.epistemic_honesty_statement)


if __name__ == "__main__":
    unittest.main()
