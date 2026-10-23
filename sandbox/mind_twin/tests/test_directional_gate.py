"""
sandbox/mind_twin/tests/test_directional_gate.py

Unit tests for 7-Slot Directional Working Memory Gate (Miller's Law)
and dynamic depth relevance hierarchy.
"""

import time
import unittest
from sandbox.mind_twin.core.directional_gate import (
    DirectionalGateEngine,
    WorkingMemoryNode,
    WorkingMemorySlot,
    WorkingMemorySnapshot,
)
from sandbox.mind_twin.core.hypergraph import Hypergraph


class TestDirectionalGate(unittest.TestCase):

    def setUp(self) -> None:
        self.graph = Hypergraph()
        # Seed 20 test vertices across diverse concepts
        for i in range(25):
            self.graph.add_vertex(
                v_id=f"concept_{i}",
                label=f"Concept {i}",
                vtype="core_task" if i < 10 else "peripheral_note",
                base_energy=1.0 + (i * 0.05),
                attributes={"topic": "sandbox_architecture", "index": i},
            )

        # Seed hierarchical child relationships for concept_0
        for child_idx in range(5):
            c_vid = f"subconcept_0_{child_idx}"
            self.graph.add_vertex(
                v_id=c_vid,
                label=f"SubConcept 0.{child_idx}",
                vtype="subtask",
                base_energy=0.8,
                attributes={"topic": "sandbox_architecture"},
            )
            self.graph.add_hyperedge(
                sources=["concept_0"],
                targets=[c_vid],
                relation="subtask_of",
                weight=1.0,
            )

            # Deep 3rd level subtask
            gc_vid = f"grandchild_0_{child_idx}"
            self.graph.add_vertex(
                v_id=gc_vid,
                label=f"Grandchild 0.{child_idx}",
                vtype="microtask",
                base_energy=0.6,
                attributes={"topic": "sandbox_architecture"},
            )
            self.graph.add_hyperedge(
                sources=[c_vid],
                targets=[gc_vid],
                relation="microtask_of",
                weight=0.9,
            )

        self.gate = DirectionalGateEngine(max_slots=7, max_depth_limit=3)

    def test_millers_law_7_slot_ceiling(self) -> None:
        """Verifies that working memory NEVER exceeds 7 active target slots."""
        # Flood with 25 candidate activations
        flooded_activations = {f"concept_{i}": 1.0 + (i * 0.1) for i in range(25)}

        snapshot = self.gate.gate_and_filter(self.graph, flooded_activations)

        self.assertLessEqual(len(snapshot.slots), 7)
        self.assertEqual(len(snapshot.slots), 7)
        self.assertEqual(snapshot.suppressed_candidates_count, 18)

    def test_dynamic_depth_hierarchy_pruning(self) -> None:
        """Verifies dynamic depth expands children but stops according to relevance budget."""
        self.gate.update_trajectory("sandbox architecture concept subtask", "sandbox")
        activations = {"concept_0": 2.5}

        snapshot = self.gate.gate_and_filter(self.graph, activations)

        self.assertEqual(len(snapshot.slots), 1)
        root_slot = snapshot.slots[0]
        self.assertEqual(root_slot.target_id, "concept_0")
        self.assertGreaterEqual(root_slot.max_depth_reached, 1)
        self.assertGreater(len(root_slot.root.children), 0)

    def test_directional_momentum_continuity(self) -> None:
        """Verifies momentum increases with intent continuity across turns."""
        self.gate.update_trajectory("blender modeling mesh rigging", "blender")
        initial_momentum = self.gate.momentum_score

        # Continuous follow-up
        self.gate.update_trajectory("blender rigging armature animation bones", "blender")
        continued_momentum = self.gate.momentum_score

        self.assertGreaterEqual(continued_momentum, initial_momentum)

    def test_epiphany_trajection_and_demotion(self) -> None:
        """Verifies subconscious epiphany can inject into slots and replace lowest energy."""
        flooded_activations = {f"concept_{i}": 0.5 + (i * 0.05) for i in range(10)}
        snapshot = self.gate.gate_and_filter(self.graph, flooded_activations)
        self.assertEqual(len(snapshot.slots), 7)

        # Inject verified epiphany
        success = self.gate.traject_epiphany(
            spark_label="Phone Gyro -> Blender Armature Pose Controller",
            domain_bridge=["fleet & satellite nodes", "blender"],
            feasibility_score=0.92,
            summary="Termux orientation stream controls 3D bone orientation.",
        )
        self.assertTrue(success)

        # Confirm epiphany occupies one of the 7 slots
        epiphany_slots = [s for s in self.gate.current_slots if s.is_epiphany]
        self.assertEqual(len(epiphany_slots), 1)
        self.assertIn("Phone Gyro", epiphany_slots[0].label)
        self.assertEqual(len(self.gate.current_slots), 7)

    def test_cognitive_frame_formatting(self) -> None:
        """Verifies formatted frame is concise and human-readable."""
        activations = {f"concept_{i}": 1.0 for i in range(5)}
        snapshot = self.gate.gate_and_filter(self.graph, activations)
        frame = snapshot.get_cognitive_frame()

        self.assertIn("[WORKING MEMORY FRAME:", frame)
        self.assertIn("Slot 1", frame)
        self.assertLess(len(frame.splitlines()), 30)


if __name__ == "__main__":
    unittest.main()
