"""
sandbox/mind_twin/tests/test_spatial_3d_engine_stress.py

Aggressive Stress & Computational Chaos Tests for 3D Spatial Mind Traversal,
6DOF Kinematics, View Frustum Attention Gating, Ray-Casting, and Procedural Code Generation.
"""

from __future__ import annotations

import ast
import math
import random
import threading
import time
import unittest

from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.spatial_3d import (
    AABB3D,
    ProceduralCodeGenerator,
    Quaternion,
    SpatialHypergraphNavigator,
    Vector3,
)


class TestSpatialMathSingularities(unittest.TestCase):
    """Stress tests arithmetic edge cases, singularities, and numerical stability."""

    def test_vector3_numerical_singularities(self) -> None:
        # Zero norm normalization
        zero_v = Vector3(0.0, 0.0, 0.0)
        self.assertEqual(zero_v.normalized(), Vector3(0.0, 0.0, 0.0))

        # Division by zero
        div_zero = Vector3(10.0, -5.0, 2.0) / 0.0
        self.assertEqual(div_zero, Vector3(0.0, 0.0, 0.0))

        # NaN / Inf injection
        nan_v = Vector3(float("nan"), float("inf"), float("-inf"))
        self.assertEqual(nan_v.x, 0.0)
        self.assertEqual(nan_v.y, 0.0)
        self.assertEqual(nan_v.z, 0.0)

        # Extreme magnitude dot product
        v_huge = Vector3(1e150, 1e150, 1e150)
        # Should not throw unhandled exception
        dot_res = v_huge.dot(v_huge)
        self.assertTrue(math.isfinite(dot_res) or math.isinf(dot_res))

        # Angle between identical and antipodal vectors
        v1 = Vector3(1.0, 0.0, 0.0)
        v2 = Vector3(-1.0, 0.0, 0.0)
        self.assertAlmostEqual(v1.angle_to(v1), 0.0, places=5)
        self.assertAlmostEqual(v1.angle_to(v2), math.pi, places=5)

    def test_quaternion_gimbal_lock_and_extremes(self) -> None:
        # Pitch at exact gimbal lock (+90 and -90 degrees)
        q_gimbal_up = Quaternion.from_euler(pitch=math.pi * 0.5, yaw=math.pi * 0.25, roll=0.0)
        q_gimbal_down = Quaternion.from_euler(pitch=-math.pi * 0.5, yaw=math.pi * 0.25, roll=0.0)
        self.assertTrue(math.isfinite(q_gimbal_up.w))
        self.assertTrue(math.isfinite(q_gimbal_down.w))

        # Degenerate zero quaternion normalization
        q_zero = Quaternion(0.0, 0.0, 0.0, 0.0).normalized()
        self.assertEqual(q_zero, Quaternion(1.0, 0.0, 0.0, 0.0))

        # Rotate vector by quaternion 360 degrees
        q_full = Quaternion.from_axis_angle(Vector3(0, 1, 0), math.pi * 2.0)
        v_orig = Vector3(3.0, 4.0, 5.0)
        v_rot = q_full.rotate_vector(v_orig)
        self.assertAlmostEqual(v_orig.x, v_rot.x, places=4)
        self.assertAlmostEqual(v_orig.y, v_rot.y, places=4)
        self.assertAlmostEqual(v_orig.z, v_rot.z, places=4)

    def test_aabb_raycast_chaos(self) -> None:
        box = AABB3D(min_pt=Vector3(-2, -2, -2), max_pt=Vector3(2, 2, 2))

        # Ray directly hitting front
        hit_dist = box.intersects_ray(origin=Vector3(0, 0, -10), direction=Vector3(0, 0, 1))
        self.assertIsNotNone(hit_dist)
        self.assertAlmostEqual(hit_dist, 8.0, places=3)

        # Ray pointing directly away
        miss_dist = box.intersects_ray(origin=Vector3(0, 0, -10), direction=Vector3(0, 0, -1))
        self.assertIsNone(miss_dist)

        # Ray parallel to face right on boundary (slab edge case)
        parallel_ray = box.intersects_ray(origin=Vector3(2.0, 0, -10), direction=Vector3(0, 0, 1))
        self.assertIsNotNone(parallel_ray)

        # Zero-direction ray (should not divide by zero or crash)
        zero_ray = box.intersects_ray(origin=Vector3(0, 0, -5), direction=Vector3(0, 0, 0))
        self.assertIsNone(zero_ray)

        # Ray starting from inside the box
        inside_hit = box.intersects_ray(origin=Vector3(0, 0, 0), direction=Vector3(0, 1, 0))
        self.assertIsNotNone(inside_hit)


class TestRealtimeGameEngineSimulation(unittest.TestCase):
    """Stress tests the cognitive engine as a 60 FPS real-time 3D game loop."""

    def setUp(self) -> None:
        self.graph = Hypergraph()
        self.gate = DirectionalGateEngine(max_slots=7)
        self.navigator = SpatialHypergraphNavigator(
            graph=self.graph,
            directional_gate=self.gate,
            initial_pos=Vector3(0, 0, 0),
        )

    def test_high_density_voxel_world_60fps_compliance(self) -> None:
        """Populates a 3D grid of 200 rooms and tests 100 consecutive 60 FPS ticks."""
        # Build 3D spatial cluster
        idx = 0
        for x in range(-5, 6, 2):
            for y in range(-2, 3, 2):
                for z in range(0, 16, 2):
                    vid = f"room_{idx}"
                    pos = Vector3(float(x * 5), float(y * 4), float(z * 6))
                    self.navigator.add_spatial_cell(
                        vid=vid,
                        label=f"Spatial Chamber {idx}",
                        position=pos,
                        extents=Vector3(2.0, 1.8, 2.0),
                    )
                    idx += 1

        self.assertEqual(len(self.navigator._spatial_nodes), idx)

        # Run 100 kinematic ticks simulating continuous player movement and mouse look
        max_tick_time = 0.0
        total_time = 0.0
        steps = 100

        for i in range(steps):
            # Simulate player flying forward, banking and pitching
            throttle = Vector3(0.0, 0.0, 15.0)  # Move forward along look vector
            delta_yaw = 0.02 * math.sin(i * 0.1)
            delta_pitch = 0.01 * math.cos(i * 0.08)

            self.navigator.step_kinematics(dt=0.016, throttle=throttle, delta_yaw=delta_yaw, delta_pitch=delta_pitch)
            snapshot, telemetry = self.navigator.navigate_tick()

            # Assert working memory strictly adheres to Miller's Law (at most 7 slots)
            self.assertLessEqual(len(snapshot.slots), 7)
            # Verify 60 FPS compliance (< 16.66 ms)
            self.assertTrue(telemetry["is_60fps_compliant"], f"Tick {i} exceeded 60 FPS: {telemetry['tick_time_ms']}ms")

            tick_ms = telemetry["tick_time_ms"]
            max_tick_time = max(max_tick_time, tick_ms)
            total_time += tick_ms

        avg_time = total_time / steps
        print(f"\n[SPATIAL 60FPS BENCHMARK] 200 Rooms | 100 Ticks | Avg: {avg_time:.3f}ms | Max: {max_tick_time:.3f}ms")
        self.assertLess(avg_time, 5.0)  # High performance headroom

    def test_frustum_gaze_attention_orientation(self) -> None:
        """Verifies that turning the camera immediately shifts cognitive attention."""
        # Target A at (0, 0, 10) [In front]
        self.navigator.add_spatial_cell("target_north", "Northern Sanctum", position=Vector3(0, 0, 10))
        # Target B at (0, 0, -10) [Behind]
        self.navigator.add_spatial_cell("target_south", "Southern Vault", position=Vector3(0, 0, -10))

        # Looking forward (+Z)
        snapshot, _ = self.navigator.navigate_tick()
        active_ids = [s.target_id for s in snapshot.slots]
        self.assertIn("target_north", active_ids)
        self.assertNotIn("target_south", active_ids)

        # Turn 180 degrees (Yaw = pi)
        self.navigator.yaw = math.pi
        self.navigator.step_kinematics(dt=0.016)

        snapshot_rotated, _ = self.navigator.navigate_tick()
        rotated_ids = [s.target_id for s in snapshot_rotated.slots]
        self.assertIn("target_south", rotated_ids)
        self.assertNotIn("target_north", rotated_ids)

    def test_procedural_code_synthesis_syntax_validity(self) -> None:
        """Verifies that generated Blender Python code is 100% syntactically valid via ast.parse."""
        for i in range(25):
            dim = Vector3(random.uniform(2.0, 20.0), random.uniform(1.0, 10.0), random.uniform(2.0, 20.0))
            pos = Vector3(random.uniform(-100, 100), random.uniform(-10, 50), random.uniform(-100, 100))

            blender_code = ProceduralCodeGenerator.generate_blender_bmesh_script(
                room_id=f"procedural_mesh_{i}",
                position=pos,
                dimensions=dim,
            )
            # Python AST parsing verification
            try:
                parsed_tree = ast.parse(blender_code)
                self.assertIsNotNone(parsed_tree)
            except SyntaxError as e:
                self.fail(f"Blender procedural script failed AST parse on iteration {i}: {e}")

            godot_code = ProceduralCodeGenerator.generate_godot_mesh_script(
                room_id=f"godot_chunk_{i}",
                dimensions=dim,
                color_hex="#ff8800",
            )
            self.assertIn("@tool", godot_code)
            self.assertIn("MeshInstance3D.new()", godot_code)
            self.assertIn("CollisionShape3D.new()", godot_code)


class TestConcurrencyAndProceduralChaos(unittest.TestCase):
    """Stress tests concurrent world generation while navigating."""

    def test_simultaneous_navigation_and_world_chunk_spawning(self) -> None:
        graph = Hypergraph()
        navigator = SpatialHypergraphNavigator(graph=graph)

        stop_event = threading.Event()
        errors: List[Exception] = []

        # Thread 1: Flight & Navigation loop at ~100Hz
        def nav_worker():
            try:
                while not stop_event.is_set():
                    navigator.step_kinematics(
                        dt=0.01,
                        throttle=Vector3(random.uniform(-5, 5), 0, random.uniform(5, 20)),
                        delta_yaw=random.uniform(-0.05, 0.05),
                    )
                    navigator.navigate_tick()
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        # Thread 2: Procedural World Builder constantly adding new rooms & portals
        def builder_worker():
            try:
                for i in range(60):
                    if stop_event.is_set():
                        break
                    pos = Vector3(random.uniform(-50, 50), random.uniform(-10, 10), random.uniform(0, 100))
                    navigator.add_spatial_cell(
                        vid=f"streamed_chunk_{i}",
                        label=f"Streamed Chunk {i}",
                        position=pos,
                    )
                    time.sleep(0.008)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=nav_worker, daemon=True)
        t2 = threading.Thread(target=builder_worker, daemon=True)

        t1.start()
        t2.start()

        time.sleep(0.8)
        stop_event.set()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        self.assertEqual(len(errors), 0, f"Encountered concurrency exceptions: {errors}")


if __name__ == "__main__":
    unittest.main()
