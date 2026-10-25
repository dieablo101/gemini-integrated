"""
sandbox/mind_twin/tests/test_subconscious_upgrades.py

Comprehensive test suite for the 6 Subconscious Engine Upgrades:
  1. Conscious Drop & SeedPacket Schema
  2. Multi-Vector Accretion Hearth & Latent Soil Vault
  3. Invariant Collision Lens & Anti-Spoiler Constraints
  4. 3-Stage Resonance Gate (Compression, Orthogonality, Trajectory)
  5. Thermodynamic Annealing & Perturbation Micro-Shifting
  6. Stillness Gate & Receptive Emergence Delivery
"""

import time
import unittest
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.subconscious import (
    AccretionHearth,
    AnnealingEngine,
    CollisionLens,
    LatentSoilVault,
    ObservationVector,
    ResonanceGate,
    SeedPacket,
    StillnessGate,
    SubconsciousWorker,
)


class TestSubconsciousUpgrades(unittest.TestCase):

    def setUp(self) -> None:
        self.graph = Hypergraph()
        self.soil = LatentSoilVault()
        self.hearth = AccretionHearth(soil_vault=self.soil, min_vectors_to_ignite=2, min_incubation_seconds=0.0)
        self.lens = CollisionLens()
        self.gate = ResonanceGate()
        self.annealing = AnnealingEngine(hearth=self.hearth, max_attempts=3, base_backoff_seconds=10.0)
        self.stillness = StillnessGate(idle_threshold_seconds=5.0)

        self.worker = SubconsciousWorker(
            graph=self.graph,
            hearth=self.hearth,
            collision_lens=self.lens,
            resonance_gate=self.gate,
            annealing_engine=self.annealing,
            stillness_gate=self.stillness,
        )

    def test_01_conscious_drop_zero_latency_schema(self) -> None:
        """Conscious drop must return a structured SeedPacket instantly."""
        t0 = time.perf_counter()
        seed = self.worker.drop_seed(
            raw_thought="Symmetry of network sockets vs asymmetry of physical desk hardware",
            conscious_context="Sprint focus on bilateral terminal transport",
            domain_hints=["networking", "hardware_cadence"],
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertLess(elapsed_ms, 5.0, "Conscious drop took longer than 5ms!")
        self.assertEqual(seed.status, "incubating")
        self.assertEqual(self.hearth.size(), 1)
        self.assertIn("networking", seed.domain_hints)
        self.assertTrue(self.worker.is_incubating)

    def test_02_multi_vector_accretion_and_readiness(self) -> None:
        """Seeds must accrete observation fibers across distinct planes before becoming ready."""
        seed = self.hearth.drop_seed(
            raw_thought="Emacs keybindings vs modal spatial navigation",
            conscious_context="Editor workflow integration",
        )
        # Initially not ready (< 2 vectors)
        ready = self.hearth.get_ready_seeds()
        self.assertEqual(len(ready), 0)

        # Accrete environmental telemetry
        attached = self.hearth.accrete_environmental_telemetry(
            cadence_wpm=82.5,
            idle_duration=1.2,
            active_branch="main",
            recent_commit="f531ac6",
        )
        self.assertGreaterEqual(attached, 2)

        # Now seed has vectors in behavioral and artifact planes
        ready = self.hearth.get_ready_seeds()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].seed_id, seed.seed_id)
        self.assertIn("behavioral", ready[0].get_planes())
        self.assertIn("artifact", ready[0].get_planes())

    def test_03_invariant_collision_lens_projection(self) -> None:
        """CollisionLens projects distinct planes and strictly formats the anti-spoiler prompt."""
        seed = self.hearth.drop_seed(raw_thought="Game world grid topology vs physical desk orientation")
        vec_somatic = ObservationVector(
            vector_id="v_som",
            plane="behavioral",
            label="Tactile Home Row Stance",
            data={"hands": "anchored"},
        )
        vec_code = ObservationVector(
            vector_id="v_code",
            plane="artifact",
            label="C Socket Buffer Invariants",
            data={"fd": 4, "nonblocking": True},
        )
        vec_rel = ObservationVector(
            vector_id="v_rel",
            plane="relational",
            label="Creative Autonomy Core Value",
            data={"sovereignty": 1.0},
        )
        seed.attach_vector(vec_somatic)
        seed.attach_vector(vec_code)
        seed.attach_vector(vec_rel)

        matrix = self.lens.project(seed)
        self.assertEqual(len(matrix.behavioral_plane), 1)
        self.assertEqual(len(matrix.artifact_plane), 1)
        self.assertEqual(len(matrix.relational_plane), 1)
        self.assertIn("Plane 1 [Somatic/Behavioral]", matrix.anti_spoiler_prompt)
        self.assertIn("Plane 2 [Technical Artifact]", matrix.anti_spoiler_prompt)
        self.assertIn("Do NOT state the obvious", matrix.anti_spoiler_prompt)

    def test_04_resonance_gate_saliency_and_miss_diagnostics(self) -> None:
        """Resonance gate rejects sterile tautologies, muddled noise, and premature fragments."""
        seed = self.hearth.drop_seed(raw_thought="Decoupled state syncing")
        seed.attach_vector(ObservationVector("v1", "artifact", "C Memory Buffer"))
        seed.attach_vector(ObservationVector("v2", "relational", "User Independence"))

        # Test A: Sterile miss (trivial tautology)
        sterile_res = self.gate.evaluate(
            candidate_summary="Kyle likes to write code and prefers doing it alone.",
            candidate_mechanism="Run commands.",
            seed=seed,
        )
        self.assertFalse(sterile_res.passed)
        self.assertEqual(sterile_res.miss_type, "sterile")
        self.assertIn("Sterile Miss", sterile_res.feedback)

        # Test B: Muddled miss (bloated multi-paragraph fluff)
        bloated_text = "When we consider the overarching implications of bilateral architecture, " * 15
        muddled_res = self.gate.evaluate(
            candidate_summary=bloated_text,
            candidate_mechanism="Do many things across multiple layers over prolonged periods of time.",
            seed=seed,
        )
        self.assertFalse(muddled_res.passed)
        self.assertEqual(muddled_res.miss_type, "muddled")
        self.assertIn("Muddled Miss", muddled_res.feedback)

        # Test C: Authentic breakthrough (passes compression, orthogonality, trajectory)
        breakthrough_res = self.gate.evaluate(
            candidate_summary="The invariant coupling C Memory Buffer and User Independence converges the system state.",
            candidate_mechanism="Bind and pipeline buffer changes to decouple runtime execution.",
            seed=seed,
        )
        self.assertTrue(breakthrough_res.passed)
        self.assertIsNone(breakthrough_res.miss_type)
        self.assertGreaterEqual(breakthrough_res.overall_resonance, 0.65)

    def test_05_annealing_engine_perturbation_and_latent_soil(self) -> None:
        """AnnealingEngine perturbs vectors on muddled misses and transitions to latent soil on attempt 3."""
        seed = self.hearth.drop_seed(raw_thought="Stubborn knot with difficult dimensional tension")
        seed.attach_vector(ObservationVector("v1", "artifact", "Complex Matrix Transform", weight=0.4))
        seed.attach_vector(ObservationVector("v2", "sensory", "Gyro Telemetry Stream", weight=0.9))

        # Attempt 1: Muddled miss -> should trigger micro-shift perturbation
        res1 = self.gate.evaluate("Short but confusing muddled statement.", "", seed)
        res1.miss_type = "muddled"
        dec1 = self.annealing.handle_attempt_result(seed, res1)

        self.assertEqual(dec1.action, "perturb_micro")
        self.assertEqual(seed.attempts, 1)
        self.assertIsNotNone(dec1.perturbed_vector)

        # Attempt 2: Premature miss -> should trigger pivot / cooldown
        res2 = self.gate.evaluate("Needs more real world data.", "", seed)
        res2.miss_type = "premature"
        dec2 = self.annealing.handle_attempt_result(seed, res2)

        self.assertEqual(dec2.action, "pivot_macro")
        self.assertEqual(seed.attempts, 2)

        # Attempt 3: Exhaustion -> must move seed to Latent Soil Vault!
        res3 = self.gate.evaluate("Still premature.", "", seed)
        res3.miss_type = "premature"
        dec3 = self.annealing.handle_attempt_result(seed, res3)

        self.assertEqual(dec3.action, "dormant_soil")
        self.assertEqual(seed.status, "dormant")
        self.assertEqual(self.hearth.size(), 0)
        self.assertEqual(self.soil.size(), 1)

    def test_06_latent_soil_catalyst_probe_and_awakening(self) -> None:
        """Dormant seeds awaken from Latent Soil when a fresh real-world catalyst matches tokens."""
        seed = self.hearth.drop_seed(
            raw_thought="Quantum quaternion rotation for photon engine rendering",
            conscious_context="Graphics pipeline",
        )
        seed.attach_vector(ObservationVector("v1", "artifact", "quaternion shader pipeline"))
        # Deposit into soil
        self.soil.deposit(seed)
        self.assertEqual(self.soil.size(), 1)

        # Irrelevant catalyst does not awaken
        irrelevant = self.soil.probe_catalyst("Update documentation and changelog notes")
        self.assertEqual(len(irrelevant), 0)

        # Relevant real-world stimulus triggers awakening!
        matches = self.soil.probe_catalyst("Implemented raw quaternion rotation and photon shader")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].seed_id, seed.seed_id)

        # Re-awaken through hearth
        awakened = self.hearth.check_catalyst_awakening("Implemented raw quaternion rotation and photon shader")
        self.assertEqual(len(awakened), 1)
        self.assertEqual(self.soil.size(), 0)
        self.assertEqual(self.hearth.size(), 1)
        self.assertEqual(awakened[0].status, "incubating")

    def test_07_stillness_gate_receptivity_and_flow_protection(self) -> None:
        """StillnessGate protects deep flow and only allows emergence during pauses or milestones."""
        # 1. Flow lock: running command suppresses emergence
        self.stillness.set_execution_state(True)
        status = self.stillness.evaluate_receptivity()
        self.assertFalse(status.is_receptive)
        self.assertEqual(status.trigger_type, "active_flow_locked")

        # 2. Release flow lock, user active recently (< 5s threshold)
        self.stillness.set_execution_state(False)
        self.stillness.record_activity("keystroke")
        status = self.stillness.evaluate_receptivity(override_idle_seconds=1.5)
        self.assertFalse(status.is_receptive)
        self.assertEqual(status.trigger_type, "busy_transient")

        # 3. Cognitive stillness pause (> 5s threshold) opens receptivity
        status = self.stillness.evaluate_receptivity(override_idle_seconds=6.0)
        self.assertTrue(status.is_receptive)
        self.assertEqual(status.trigger_type, "stillness_pause")

        # 4. Post-commit milestone reflection opens receptivity immediately
        status = self.stillness.evaluate_receptivity(event_marker="post_commit")
        self.assertTrue(status.is_receptive)
        self.assertEqual(status.trigger_type, "post_commit")

        # 5. Dawn boot rehydration opens receptivity
        status = self.stillness.evaluate_receptivity(event_marker="dawn_boot")
        self.assertTrue(status.is_receptive)
        self.assertEqual(status.trigger_type, "dawn_boot")

    def test_08_end_to_end_hearth_incubation_to_stillness_delivery(self) -> None:
        """Full pipeline: conscious drop -> hearth accretion -> breakthrough -> stillness delivery."""
        # Step 1: Drop
        seed = self.worker.drop_seed(
            raw_thought="Bilateral heartbeat telemetry synchronization",
            conscious_context="Mind twin bridge",
        )
        # Step 2: Accrete multi-plane vectors
        seed.attach_vector(ObservationVector("v_somatic", "behavioral", "Quiet Typing Cadence"))
        seed.attach_vector(ObservationVector("v_socket", "artifact", "Zero Bloat Socket Engine"))
        seed.attach_vector(ObservationVector("v_autonomy", "relational", "Sovereign Architectural Stance"))

        # Step 3: Run Hearth Incubation Cycle
        packet = self.worker.run_hearth_incubation_cycle()
        self.assertIsNotNone(packet)
        self.assertEqual(self.worker.channel.size(), 1)
        self.assertIn("Aha!", packet.spark_name)

        # Step 4: Check emergence during active flow -> should be held in channel
        self.stillness.record_activity("keystroke")
        delivered_busy = self.worker.check_emergence_delivery(override_idle_seconds=1.0)
        self.assertIsNone(delivered_busy)
        self.assertEqual(self.worker.channel.size(), 1)

        # Step 5: Check emergence in cognitive stillness pause -> delivered!
        delivered_stillness = self.worker.check_emergence_delivery(override_idle_seconds=10.0)
        self.assertIsNotNone(delivered_stillness)
        self.assertEqual(delivered_stillness.packet_id, packet.packet_id)
        self.assertEqual(self.worker.channel.size(), 0)


if __name__ == "__main__":
    unittest.main()
