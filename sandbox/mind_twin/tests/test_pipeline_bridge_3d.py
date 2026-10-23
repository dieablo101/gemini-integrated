"""
sandbox/mind_twin/tests/test_pipeline_bridge_3d.py

Rigorous Stress Tests for 3D Procedural Asset Pipeline Bridge (Blender 4 <-> Godot 4).
Tests:
- Precision drift over 10,000 chained matrix multiplications.
- Blender Z-up to Godot Y-up coordinate parity.
- Mesh hull sanitization of non-manifold edges, zero-area triangles, and degenerate geometry.
- PBR shader validation (sampler exhaustion, loop hazards, and AST syntax parsing).
"""

import math
import unittest
from typing import List, Tuple

from sandbox.mind_twin.core.pipeline_bridge_3d import (
    CoordinateTransformer,
    Matrix4,
    MeshHullSanitizer,
    PBRShaderSynthesizer,
    TriangleMesh,
)
from sandbox.mind_twin.core.spatial_3d import Quaternion, Vector3


class TestPipelineBridge3D(unittest.TestCase):

    def test_coordinate_parity_round_trip(self):
        """Points transformed from Blender to Godot and back must maintain exact equivalence."""
        pts = [
            Vector3(10.5, -24.2, 5.0),
            Vector3(-100.0, 0.0, 42.12),
            Vector3(0.0, 0.0, 0.0),
            Vector3(1e4, -1e4, 5e3),
        ]
        for p in pts:
            godot_p = CoordinateTransformer.blender_to_godot_point(p)
            blender_p = CoordinateTransformer.godot_to_blender_point(godot_p)
            self.assertAlmostEqual(p.x, blender_p.x, places=5)
            self.assertAlmostEqual(p.y, blender_p.y, places=5)
            self.assertAlmostEqual(p.z, blender_p.z, places=5)

    def test_chained_rotation_matrix_drift(self):
        """Stress 10,000 chained incremental rotations to verify Gram-Schmidt drift elimination."""
        angle_step = math.radians(0.036)  # 360 deg after 10,000 steps
        q_step = Quaternion.from_axis_angle(Vector3(0.0, 1.0, 0.0), angle_step)
        rot_mat = Matrix4.from_quaternion(q_step)

        # 1. Uncompensated chain (drifts due to floating point error accumulation)
        chain_uncomp = Matrix4.identity()
        for _ in range(1000):
            chain_uncomp = chain_uncomp * rot_mat

        # 2. Compensated chain using periodic Gram-Schmidt orthogonalization
        transforms = [rot_mat] * 10000
        chain_comp = CoordinateTransformer.chain_transforms(transforms, compensate_drift_every=50)

        # After 10,000 steps (360 deg), matrix should equal identity matrix
        p = Vector3(1.0, 0.0, 0.0)
        p_transformed = chain_comp.transform_point(p)
        drift = (p - p_transformed).length()
        self.assertLess(drift, 1e-4, f"Compensated drift exceeded tolerance: {drift}")

    def test_mesh_hull_sanitizer_pathological_geometry(self):
        """Sanitizer must remove collinear triangles, duplicate vertices, and non-manifold edges."""
        # Create dirty mesh:
        # - 3 duplicate vertices at (0, 0, 0)
        # - 1 collinear triangle with 0 area
        # - 1 non-manifold triangle sharing edge with 2 existing faces
        # - 1 valid triangle
        verts = [
            Vector3(0.0, 0.0, 0.0),       # 0
            Vector3(0.00001, 0.0, 0.0),   # 1 (duplicate of 0)
            Vector3(1.0, 0.0, 0.0),       # 2
            Vector3(0.0, 1.0, 0.0),       # 3
            Vector3(2.0, 0.0, 0.0),       # 4 (collinear with 0 and 2)
            Vector3(0.0, 0.0, 1.0),       # 5
        ]

        faces = [
            (0, 2, 3),  # Valid triangle 1
            (1, 2, 3),  # Non-manifold duplicate face (shares edge 2-3 with face 1)
            (0, 2, 4),  # Collinear degenerate triangle (area ~ 0)
            (0, 3, 5),  # Valid triangle 2
            (0, 2, 5),  # Another face sharing edge (0, 2)
            (1, 2, 5),  # Non-manifold edge face
        ]

        raw_mesh = TriangleMesh(vertices=verts, indices=faces)
        sanitized, stats = MeshHullSanitizer.sanitize(raw_mesh)

        self.assertGreater(stats["duplicate_verts_merged"], 0)
        self.assertGreater(stats["degenerate_removed"], 0)
        self.assertGreater(stats["non_manifold_culled"], 0)
        self.assertTrue(sanitized.surface_area() > 0.0)

    def test_zero_volume_hull_remedy(self):
        """Completely flat 2D coplanar polygons must be padded to non-zero volume hulls."""
        flat_verts = [Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 1, 0)]
        flat_faces = [(0, 1, 2)]
        flat_mesh = TriangleMesh(vertices=flat_verts, indices=flat_faces)

        sanitized, _ = MeshHullSanitizer.sanitize(flat_mesh)
        self.assertEqual(len(sanitized.vertices), 4)  # Padded with 4th non-coplanar vertex

    def test_pbr_shader_synthesis_and_ast_validation(self):
        """Godot PBR shaders and Blender bpy scripts must be verified safe and syntactically sound."""
        # 1. Valid Godot Shader Generation
        shader_code = PBRShaderSynthesizer.generate_godot_pbr_shader(
            "WaterWindChunk",
            roughness=0.2,
            metallic=0.8,
            samplers=["normal_map", "roughness_map", "wind_noise"],
            include_wind_sway=True,
        )
        is_valid, err = PBRShaderSynthesizer.validate_godot_shader(shader_code)
        self.assertTrue(is_valid, f"Shader validation failed: {err}")

        # 2. Sampler Limit Clamp
        excessive_samplers = [f"tex_{i}" for i in range(25)]
        shader_excess = PBRShaderSynthesizer.generate_godot_pbr_shader("Excess", samplers=excessive_samplers)
        is_valid, _ = PBRShaderSynthesizer.validate_godot_shader(shader_excess)
        self.assertTrue(is_valid)  # Should have clamped internally to 16

        # 3. Malicious infinite loop rejection
        infinite_loop_shader = "shader_type spatial;\nvoid fragment() { while(true) { } }"
        is_valid, err = PBRShaderSynthesizer.validate_godot_shader(infinite_loop_shader)
        self.assertFalse(is_valid)
        self.assertIn("while(true)", err)

        # 4. Blender Material Script AST validation
        blender_py = PBRShaderSynthesizer.generate_blender_material_script("GoldArmor", (1.0, 0.84, 0.0))
        ast_valid, ast_err = PBRShaderSynthesizer.validate_blender_script_ast(blender_py)
        self.assertTrue(ast_valid, f"Blender AST parse failed: {ast_err}")


if __name__ == "__main__":
    unittest.main()
