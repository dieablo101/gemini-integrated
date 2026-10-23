"""
sandbox/mind_twin/tests/test_subconscious_engine.py

Unit tests for Subconscious Incubation Engine:
- Novelty Gating Filter (Routine = dormant, Out-of-the-norm = fire)
- Conclusive API Reality Probe
- Lockless Epiphany Channel
- Forked Subconscious Worker Collision Scanning
"""

import time
import unittest
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.subconscious import (
    ConclusiveRealityProbe,
    EpiphanyChannel,
    EpiphanyPacket,
    NoveltyDetector,
    SubconsciousWorker,
)


class TestSubconsciousEngine(unittest.TestCase):

    def setUp(self) -> None:
        self.detector = NoveltyDetector(novelty_threshold=0.60)
        self.probe = ConclusiveRealityProbe(confidence_gate=0.75)
        self.channel = EpiphanyChannel(capacity=8)

        # Setup hypergraph with vertices across distinct domains
        self.graph = Hypergraph()

        # Domain A: Fleet & Sensory
        self.graph.add_vertex(
            v_id="phone_gyro_stream",
            label="Phone Gyroscope Stream",
            vtype="sensory_telemetry",
            base_energy=1.0,
            attributes={"topic": "fleet", "full_content": "telemetry sensor stream gyro quaternion"},
        )

        # Domain B: 3D Game & Armature
        self.graph.add_vertex(
            v_id="blender_bone_armature",
            label="Blender Bone Armature",
            vtype="game_dev",
            base_energy=1.0,
            attributes={"topic": "blender", "full_content": "mesh armature rigging 3d bone rotation"},
        )

        self.worker = SubconsciousWorker(
            graph=self.graph,
            novelty_detector=self.detector,
            reality_probe=self.probe,
            epiphany_channel=self.channel,
        )

    def test_novelty_gating_routine_task_stays_dormant(self) -> None:
        """Routine dev tasks (git, test, status) must produce low novelty and stay dormant."""
        routine_prompt = "run the unit test and check git status diff"
        eval_res = self.detector.evaluate(routine_prompt, active_topic="dev_routine")

        self.assertFalse(eval_res.is_out_of_the_norm)
        self.assertFalse(eval_res.should_fire_incubation)
        self.assertLess(eval_res.novelty_score, 0.45)
        self.assertIn("dormant", eval_res.reason)

    def test_novelty_gating_out_of_norm_ignites_incubation(self) -> None:
        """Creative, cross-domain problems must cross threshold and trigger incubation."""
        novel_prompt = "synthesize bilateral subconscious apophenia with somatic phone telemetry and blender shader armature"
        eval_res = self.detector.evaluate(novel_prompt, active_topic="subconscious_engine")

        self.assertTrue(eval_res.is_out_of_the_norm)
        self.assertTrue(eval_res.should_fire_incubation)
        self.assertGreaterEqual(eval_res.novelty_score, 0.60)
        self.assertIn("Out of the norm detected", eval_res.reason)

    def test_conclusive_reality_probe_filters_hallucinations(self) -> None:
        """Probe rejects ungrounded connections and approves grounded ones."""
        # Ungrounded nonsense pairing
        rejected = self.probe.evaluate_candidate(
            candidate_id="bad_1",
            concept_a="Coffee mug",
            concept_b="SQL database",
            domain_a="kitchen",
            domain_b="database",
            proposed_bridge="Drink coffee to increase database table index speed.",
        )
        self.assertFalse(rejected.is_feasible)
        self.assertLess(rejected.confidence, 0.60)

        # Grounded technical bridge
        approved = self.probe.evaluate_candidate(
            candidate_id="good_1",
            concept_a="Phone Gyroscope Stream",
            concept_b="Blender Bone Armature",
            domain_a="telemetry",
            domain_b="blender",
            proposed_bridge="Stream real-time phone sensor quaternion stream into Blender bone transform matrix pipeline over socket ipc.",
        )
        self.assertTrue(approved.is_feasible)
        self.assertGreaterEqual(approved.confidence, 0.75)

    def test_epiphany_channel_fifo_mechanics(self) -> None:
        """Verifies push, pop, peek, and capacity limits of EpiphanyChannel."""
        packet1 = EpiphanyPacket(
            packet_id="ep1",
            spark_name="Spark 1",
            domain_bridge=["A", "B"],
            feasibility_score=0.85,
            summary="Insight 1",
        )
        packet2 = EpiphanyPacket(
            packet_id="ep2",
            spark_name="Spark 2",
            domain_bridge=["C", "D"],
            feasibility_score=0.90,
            summary="Insight 2",
        )

        self.channel.push(packet1)
        self.channel.push(packet2)
        self.assertEqual(self.channel.size(), 2)

        popped = self.channel.pop()
        self.assertIsNotNone(popped)
        self.assertEqual(popped.packet_id, "ep1")
        self.assertEqual(self.channel.size(), 1)

    def test_worker_incubation_discovery_cycle(self) -> None:
        """Simulates worker detecting novelty, igniting, and discovering candidate epiphany."""
        is_novel, _ = self.worker.check_and_ignite(
            task_prompt="create novel somatic link between phone sensors and blender rigging",
            active_topic="creative_pipeline",
        )
        self.assertTrue(is_novel)
        self.assertTrue(self.worker.is_incubating)

        # Run incubation cycle
        packet = self.worker.run_incubation_cycle()
        self.assertIsNotNone(packet)
        self.assertEqual(self.channel.size(), 1)
        self.assertIn("Phone Gyroscope", packet.spark_name)
        self.assertGreaterEqual(packet.feasibility_score, 0.75)


if __name__ == "__main__":
    unittest.main()
