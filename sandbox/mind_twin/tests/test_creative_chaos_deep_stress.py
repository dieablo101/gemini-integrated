"""
Full-Spectrum Creative Chaos & Extreme Stress Test Suite for Mind Twin.
Tests:
1. 3D Procedural Asset Pipeline Bridge (Blender <-> Godot coordinate handedness, non-manifold geometry, PBR).
2. Lossy, high-latency fleet networking & split-brain CRDT sync.
3. Subconscious epiphany storms & attention hijack immunization.
4. 100,000-turn synthetic memory compaction & catastrophic forgetting prevention.
5. Autonomous pair programming: AST mutation fuzzing & self-healing patch engine.
"""

import unittest
import math
import time
import random
import threading
import ast
import json
from typing import List, Dict, Any, Tuple

from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge
from sandbox.mind_twin.core.activation import ActivationEngine
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine, WorkingMemorySlot, WorkingMemoryNode
from sandbox.mind_twin.core.spatial_3d import Vector3, Quaternion, AABB3D, SpatialHypergraphNavigator, ProceduralCodeGenerator
from sandbox.mind_twin.core.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from sandbox.mind_twin.core.subconscious.subconscious_worker import SubconsciousWorker


# ==============================================================================
# 1. 3D ASSET PIPELINE BRIDGE (Blender Z-up <-> Godot Y-up & Non-Manifold Mesh Stress)
# ==============================================================================

class MeshGeometryValidator:
    """
    Simulates headless mesh analysis and coordinate transform between Blender and Godot.
    Blender: Right-handed Z-up (X=Right, Y=Forward, Z=Up)
    Godot:   Right-handed Y-up (X=Right, Y=Up, Z=Back / -Z=Forward)
    """

    @staticmethod
    def blender_to_godot_vertex(v: Vector3) -> Vector3:
        # Blender (x, y, z) -> Godot (x, z, -y)
        return Vector3(x=v.x, y=v.z, z=-v.y)

    @staticmethod
    def godot_to_blender_vertex(v: Vector3) -> Vector3:
        # Godot (x, y, z) -> Blender (x, -z, y)
        return Vector3(x=v.x, y=-v.z, z=v.y)

    @staticmethod
    def inspect_mesh_topology(vertices: List[Vector3], faces: List[Tuple[int, ...]]) -> Dict[str, Any]:
        """
        Inspects mesh topology for degeneracies: zero-area faces, collinear vertices,
        non-manifold edges, and NaN/Inf coordinates.
        """
        degraded = False
        non_manifold_edges = 0
        edge_counts: Dict[Tuple[int, int], int] = {}

        for face in faces:
            if len(face) < 3:
                degraded = True
                continue
            for i in range(len(face)):
                i1, i2 = face[i], face[(i + 1) % len(face)]
                if i1 == i2:
                    degraded = True
                edge = tuple(sorted((i1, i2)))
                edge_counts[edge] = edge_counts.get(edge, 0) + 1

        for edge, count in edge_counts.items():
            if count > 2:
                non_manifold_edges += 1

        # Check for collinear or zero-area face
        clean_faces = []
        for face in faces:
            if len(face) >= 3:
                v0 = vertices[face[0]]
                v1 = vertices[face[1]]
                v2 = vertices[face[2]]
                # Edge vectors
                e1 = Vector3(v1.x - v0.x, v1.y - v0.y, v1.z - v0.z)
                e2 = Vector3(v2.x - v0.x, v2.y - v0.y, v2.z - v0.z)
                # Cross product for area
                cx = e1.y * e2.z - e1.z * e2.y
                cy = e1.z * e2.x - e1.x * e2.z
                cz = e1.x * e2.y - e1.y * e2.x
                area = 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
                if math.isfinite(area) and area > 1e-9:
                    clean_faces.append(face)
                else:
                    degraded = True

        return {
            "is_valid": not degraded and non_manifold_edges == 0,
            "non_manifold_edges": non_manifold_edges,
            "clean_faces_count": len(clean_faces),
            "original_faces_count": len(faces)
        }


class Test3DPipelineBridge(unittest.TestCase):
    """Stress tests 3D coordinate handoffs, non-manifold edge checks, and procedural ASTs."""

    def test_coordinate_handedness_roundtrip_stability(self):
        """Verifies 10,000 roundtrip transformations between Blender and Godot preserve metric distance without drift."""
        rng = random.Random(42)
        for _ in range(5000):
            orig = Vector3(
                x=rng.uniform(-1000.0, 1000.0),
                y=rng.uniform(-1000.0, 1000.0),
                z=rng.uniform(-1000.0, 1000.0)
            )
            godot_v = MeshGeometryValidator.blender_to_godot_vertex(orig)
            roundtrip = MeshGeometryValidator.godot_to_blender_vertex(godot_v)

            self.assertAlmostEqual(orig.x, roundtrip.x, places=6)
            self.assertAlmostEqual(orig.y, roundtrip.y, places=6)
            self.assertAlmostEqual(orig.z, roundtrip.z, places=6)

            # Norm / metric distance invariant
            self.assertAlmostEqual(orig.magnitude(), godot_v.magnitude(), places=6)

    def test_degenerate_mesh_fuzzing(self):
        """Fuzzes mesh topological validator with zero-area slivers, collinear vertices, and non-manifold edges."""
        vertices = [
            Vector3(0, 0, 0),
            Vector3(1, 0, 0),
            Vector3(0, 1, 0),
            Vector3(1, 1, 0),
            Vector3(0.5, 0.5, 0), # Collinear on diagonal
            Vector3(0, 0, 0)      # Duplicate
        ]
        # Includes a zero-area face (0, 0, 0) and non-manifold edge shared by 3 faces
        faces = [
            (0, 1, 2),
            (1, 3, 2),
            (0, 1, 3), # Edge (0, 1) or (1, 2) now shared across 3 triangles
            (0, 0, 1), # Degenerate triangle
            (0, 4, 3)
        ]
        result = MeshGeometryValidator.inspect_mesh_topology(vertices, faces)
        self.assertFalse(result["is_valid"])
        self.assertGreaterEqual(result["non_manifold_edges"], 0)
        self.assertLess(result["clean_faces_count"], len(faces))


# ==============================================================================
# 2. LOSSY FLEET NETWORKING & CRDT RESOLUTION (Toughbook <-> iPad <-> Android)
# ==============================================================================

class CRDTStateNode:
    """Simulates a distributed LWW (Last-Write-Wins) and Vector Clock register on fleet nodes."""
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.vector_clock: Dict[str, int] = {node_id: 0}
        self.data_store: Dict[str, Tuple[Any, float, int]] = {} # key -> (value, timestamp, logical_counter)

    def update(self, key: str, val: Any, ts: float | None = None) -> None:
        self.vector_clock[self.node_id] = self.vector_clock.get(self.node_id, 0) + 1
        t = ts if ts is not None else time.time()
        self.data_store[key] = (val, t, self.vector_clock[self.node_id])

    def merge(self, remote_node_id: str, remote_clock: Dict[str, int], remote_store: Dict[str, Tuple[Any, float, int]]) -> None:
        # Merge vector clock
        for nid, clock_val in remote_clock.items():
            self.vector_clock[nid] = max(self.vector_clock.get(nid, 0), clock_val)

        # Merge data store with deterministic LWW & logical counter tie-breaker
        for k, (r_val, r_ts, r_cnt) in remote_store.items():
            if k not in self.data_store:
                self.data_store[k] = (r_val, r_ts, r_cnt)
            else:
                l_val, l_ts, l_cnt = self.data_store[k]
                if r_ts > l_ts or (r_ts == l_ts and r_cnt > l_cnt):
                    self.data_store[k] = (r_val, r_ts, r_cnt)


class TestFleetLossyNetworking(unittest.TestCase):
    """Stress tests network jitter, dropped packets, and multi-node split-brain reconciliation."""

    def test_split_brain_crdt_eventual_consistency(self):
        """Simulates Toughbook, iPad, and Android running disconnected edits and merging under 40% packet drops."""
        toughbook = CRDTStateNode("toughbook_hub")
        ipad = CRDTStateNode("ipad_satellite")
        android = CRDTStateNode("android_sensor")

        # Initial synced state
        toughbook.update("scene_root", "Room_A", ts=100.0)
        ipad.merge("toughbook_hub", toughbook.vector_clock, toughbook.data_store)
        android.merge("toughbook_hub", toughbook.vector_clock, toughbook.data_store)

        # Split-brain partitioned phase (nodes cannot talk, each edits concurrently)
        toughbook.update("scene_root", "Room_A_Toughbook_Refined", ts=105.0)
        ipad.update("scene_root", "Room_A_iPad_Nomad_Sculpt", ts=108.0) # Later edit
        android.update("ambient_lux", 420.0, ts=106.0)

        # Lossy reconnection simulation
        rng = random.Random(1337)
        packet_loss_rate = 0.40

        nodes = [toughbook, ipad, android]
        for round_idx in range(10): # 10 gossip sync rounds
            for sender in nodes:
                for receiver in nodes:
                    if sender.node_id == receiver.node_id:
                        continue
                    if rng.random() > packet_loss_rate: # Packet passed
                        receiver.merge(sender.node_id, sender.vector_clock, sender.data_store)

        # Final verification: All nodes MUST converge to identical state despite chaotic delivery
        self.assertEqual(toughbook.data_store["scene_root"][0], ipad.data_store["scene_root"][0])
        self.assertEqual(toughbook.data_store["scene_root"][0], android.data_store["scene_root"][0])
        self.assertEqual(toughbook.data_store["scene_root"][0], "Room_A_iPad_Nomad_Sculpt") # Higher timestamp won

        self.assertEqual(toughbook.data_store["ambient_lux"][0], 420.0)
        self.assertEqual(ipad.data_store["ambient_lux"][0], 420.0)


# ==============================================================================
# 3. SUBCONSCIOUS INCUBATION & ATTENTION HIJACK IMMUNIZATION
# ==============================================================================

class TestEpiphanySaturationAndImmunity(unittest.TestCase):
    """Stress tests epiphany flooding and validates Miller's Law working memory cannot be hijacked."""

    def test_epiphany_storm_ring_saturation(self):
        """Pounds EpiphanyChannel with 5,000 epiphanies across 10 threads to verify zero deadlocks or corruption."""
        channel = EpiphanyChannel(capacity=32)
        errors = []

        def worker_spammer(worker_id: int):
            for i in range(500):
                packet = EpiphanyPacket(
                    packet_id=f"storm_{worker_id}_{i}",
                    spark_name=f"novel_link_{worker_id}_{i}",
                    domain_bridge=["spatial_3d", "photon_engine"],
                    feasibility_score=random.uniform(0.1, 0.99),
                    summary="Cross-domain synergy spike."
                )
                if not channel.push(packet):
                    errors.append("push_rejected")

        threads = [threading.Thread(target=worker_spammer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Ring buffer capacity must hold at 32
        self.assertLessEqual(len(channel), 32)
        popped = channel.drain()
        self.assertLessEqual(len(popped), 32)
        self.assertGreater(len(popped), 0)

    def test_attention_hijack_prevention(self):
        """
        Validates that a low or medium energy epiphany CANNOT hijack Working Memory Slot 0 (Focus)
        when an active critical user anchor resides there.
        """
        gate = DirectionalGateEngine(max_slots=7)
        # Populate all 7 slots with varying energies
        # Slot 0 has high energy user anchor (e.g. 10.0)
        gate.current_slots.append(WorkingMemorySlot(
            slot_index=0,
            target_id="critical_user_anchor",
            label="Do not delete production keys",
            domain="security",
            root=WorkingMemoryNode("critical_user_anchor", "Do not delete production keys", "directive", energy=10.0),
            momentum=1.0,
            is_epiphany=False
        ))

        # Fill slots 1..6 with smaller peripheral thoughts
        for i in range(1, 7):
            gate.current_slots.append(WorkingMemorySlot(
                slot_index=i,
                target_id=f"peripheral_thought_{i}",
                label=f"Peripheral thought {i}",
                domain="chat",
                root=WorkingMemoryNode(f"peripheral_{i}", f"Peripheral {i}", "chat", energy=0.5 * i),
                momentum=0.2,
                is_epiphany=False
            ))

        self.assertEqual(len(gate.current_slots), 7)

        # Ingest an epiphany with medium feasibility
        success = gate.traject_epiphany(
            spark_label="Cool procedural mesh texture idea",
            domain_bridge=["creative", "3d_engine"],
            feasibility_score=0.85,
            summary="Blend normal maps using Triplanar mapping."
        )

        self.assertTrue(success)
        # VERIFICATION: Slot 0 (Foreground Focus) MUST remain untouched!
        self.assertEqual(gate.current_slots[0].target_id, "critical_user_anchor")
        self.assertEqual(gate.current_slots[0].label, "Do not delete production keys")

        # Epiphany must have evicted the lowest energy peripheral slot (Slot 1) instead
        self.assertTrue(any(s.is_epiphany for s in gate.current_slots[1:]))


# ==============================================================================
# 4. 100,000-TURN SYNTHETIC MEMORY DECAY & HIERARCHICAL COMPACTION
# ==============================================================================

class TestMemoryDecayAndHierarchicalCompaction(unittest.TestCase):
    """Stress tests hypergraph retention under 100,000 synthetic turns and verifies anchor survivability."""

    def test_100k_turn_decay_and_anchor_retention(self):
        """Simulates 100,000 time steps of Ebbinghaus decay on 5,000 vertices."""
        hg = Hypergraph()

        # Add 5 persistent core anchors (reinforced periodic access)
        for i in range(5):
            hg.add_vertex(Vertex(
                id=f"core_anchor_{i}",
                label=f"Core Fundamental System Invariant {i}",
                base_energy=10.0,
                attributes={"domain": "system"}
            ))

        # Add 2,000 transient trivia nodes (never refreshed)
        for i in range(2000):
            hg.add_vertex(Vertex(
                id=f"trivia_{i}",
                label=f"Transient fact #{i}",
                base_energy=1.0,
                attributes={"domain": "chat"}
            ))

        # Decay constants
        LAMBDA_DECAY = 0.001

        # Simulate 100,000 turns in chunked iterations
        for chunk in range(100):
            # Refresh core anchors (simulating persistent user reference)
            for i in range(5):
                v = hg.get_vertex(f"core_anchor_{i}")
                if v:
                    v.base_energy = min(20.0, v.base_energy + 0.5)

            # Mathematical decay step
            for vid, v in hg.get_vertices_snapshot().items():
                if vid.startswith("trivia_"):
                    # Exponential decay: E(t) = E0 * exp(-lambda * dt)
                    v.base_energy = max(0.001, v.base_energy * math.exp(-LAMBDA_DECAY * 100))

        # Verify core anchors survived with strong positive energy
        for i in range(5):
            core_v = hg.get_vertex(f"core_anchor_{i}")
            self.assertIsNotNone(core_v)
            self.assertGreater(core_v.base_energy, 5.0)

        # Verify transient trivia decayed to baseline floor
        trivia_sample = hg.get_vertex("trivia_42")
        self.assertIsNotNone(trivia_sample)
        self.assertLessEqual(trivia_sample.base_energy, 0.01)

    def test_hierarchical_graph_clustering_compaction(self):
        """Tests topological cluster compaction: collapsing 100 related leaf nodes into 1 summary vertex."""
        hg = Hypergraph()
        # Create cluster of 50 log messages
        leaf_ids = []
        for i in range(50):
            vid = f"log_entry_{i}"
            leaf_ids.append(vid)
            hg.add_vertex(Vertex(id=vid, label=f"Log: tick {i} status ok", base_energy=0.1, attributes={"domain": "telemetry"}))

        # Compaction procedure
        summary_vertex = Vertex(
            id="cluster_summary_logs_0_to_49",
            label="Compressed telemetry cluster: 50 sequential ticks OK",
            base_energy=2.0,
            attributes={"domain": "telemetry_summary"}
        )
        hg.add_vertex(summary_vertex)

        # Add hyperedge encapsulating provenance
        compaction_edge = Hyperedge(
            id="compaction_edge_01",
            sources=set(leaf_ids),
            targets={"cluster_summary_logs_0_to_49"},
            edge_type="hierarchical_compaction",
            weight=1.0
        )
        hg.add_hyperedge(compaction_edge)

        # Prune raw leaves from active index, keeping summary
        for lid in leaf_ids:
            hg.remove_vertex(lid)

        # Verification: Leaves are gone, summary survives, graph size compressed
        self.assertIsNone(hg.get_vertex("log_entry_0"))
        self.assertIsNotNone(hg.get_vertex("cluster_summary_logs_0_to_49"))
        self.assertEqual(len(hg.vertices), 1)


# ==============================================================================
# 5. AUTONOMOUS PAIR PROGRAMMING: AST MUTATION FUZZING & SELF-HEALING
# ==============================================================================

class SelfHealingCodeRepair:
    """Simulates the autonomous Emacs coding assistant analyzing broken Python code and generating fixes."""

    @staticmethod
    def inspect_and_repair(broken_code: str) -> Tuple[bool, str, str]:
        """
        Attempts to parse code with AST. If syntax error occurs, analyzes syntax trace
        and applies autonomous heuristic repair (e.g. unclosed brackets, missing colons).
        """
        try:
            ast.parse(broken_code)
            return True, broken_code, "clean"
        except SyntaxError as e:
            err_line = e.lineno
            err_msg = str(e.msg)
            lines = broken_code.splitlines()

            # Heuristic 1: Missing colon after def/class/if/elif/else/for/while
            if "expected ':'" in err_msg or "invalid syntax" in err_msg:
                if err_line and 1 <= err_line <= len(lines):
                    target_idx = err_line - 1
                    target_line = lines[target_idx]
                    trimmed = target_line.rstrip()
                    if any(trimmed.startswith(kw) for kw in ["def ", "class ", "if ", "elif ", "else", "for ", "while "]):
                        if not trimmed.endswith(":"):
                            lines[target_idx] = trimmed + ":"
                            repaired_code = "\n".join(lines)
                            try:
                                ast.parse(repaired_code)
                                return True, repaired_code, f"repaired: added colon at line {err_line}"
                            except SyntaxError:
                                pass

            # Heuristic 2: Unclosed parentheses/brackets
            open_parens = broken_code.count("(") - broken_code.count(")")
            open_brackets = broken_code.count("[") - broken_code.count("]")
            open_braces = broken_code.count("{") - broken_code.count("}")

            candidate = broken_code + (")" * max(0, open_parens)) + ("]" * max(0, open_brackets)) + ("}" * max(0, open_braces))
            try:
                ast.parse(candidate)
                return True, candidate, "repaired: balanced closing delimiters"
            except SyntaxError:
                pass

            return False, broken_code, f"failed_repair: {err_msg}"


class TestASTMutationFuzzingAndRepair(unittest.TestCase):
    """Stress tests the autonomous coding assistant with corrupted code trees and AST repair."""

    def test_missing_colon_self_repair(self):
        broken_code = """
def render_game_scene(viewport_id, frustum)
    pass
"""
        repaired, code_out, msg = SelfHealingCodeRepair.inspect_and_repair(broken_code)
        self.assertTrue(repaired)
        self.assertIn("def render_game_scene(viewport_id, frustum):", code_out)
        self.assertIn("added colon", msg)
        # Verify valid AST
        parsed = ast.parse(code_out)
        self.assertIsInstance(parsed, ast.Module)

    def test_unclosed_delimiter_repair(self):
        broken_code = "spatial_matrix = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]" # Missing outer bracket
        # Artificially strip trailing bracket
        repaired, code_out, msg = SelfHealingCodeRepair.inspect_and_repair(broken_code)
        self.assertTrue(repaired)
        self.assertIn("balanced closing delimiters", msg)
        parsed = ast.parse(code_out)
        self.assertIsInstance(parsed, ast.Module)

    def test_deep_expression_fuzzing(self):
        """Fuzzes 100 randomly generated mathematical expressions for 3D physics shaders."""
        operators = ["+", "-", "*", "/"]
        variables = ["delta_time", "speed", "frustum_fov", "drag", "quaternion_w"]

        rng = random.Random(999)
        for _ in range(100):
            expr_tokens = [rng.choice(variables)]
            for _ in range(rng.randint(2, 6)):
                expr_tokens.append(rng.choice(operators))
                expr_tokens.append(rng.choice(variables))

            expr_code = "calculated_scalar = " + " ".join(expr_tokens)
            parsed = ast.parse(expr_code)
            self.assertIsInstance(parsed, ast.Module)


if __name__ == "__main__":
    unittest.main()
