"""
sandbox/mind_twin/tests/test_ast_mutation_dojo.py

Stress tests for Autonomous Coding Dojo & AST Mutation Fuzzing (Frontier 5).
Tests:
- Precision diagnostics of syntax defects with AST doctor.
- Automated self-healing heuristics for unclosed brackets, missing colons, and unterminated strings.
- Unicode mathematical variable parsing (Greek kinematics, 3D math symbols).
- Surgical patch context hashing and concurrent mutation collision rejection.
"""

import unittest

from sandbox.mind_twin.core.code_repair_engine import (
    ASTDoctor,
    DiagnosticIssue,
    SafePatchApplier,
    SurgicalPatch,
)


class TestASTMutationDojo(unittest.TestCase):

    def test_syntax_defect_localization(self):
        """AST doctor must locate exact line and defect when given corrupted syntax."""
        broken_code = """def calculate_velocity(p0, p1, dt):
    delta = p1 - p0
    if dt <= 0.0
        return 0.0
    return delta / dt
"""
        valid, issue = ASTDoctor.inspect_syntax(broken_code)
        self.assertFalse(valid)
        self.assertIsNotNone(issue)
        self.assertEqual(issue.line_number, 3)
        self.assertIn("if dt <= 0.0", issue.culprit_snippet)

    def test_self_healing_missing_colon_and_delimiters(self):
        """Doctor must autonomously repair missing colons and unclosed delimiters into 100% valid AST."""
        # 1. Missing colon on if statement
        code_missing_colon = "def test_speed():\n    if x > 10\n        return True\n    return False\n"
        healed, fixes = ASTDoctor.auto_heal_syntax(code_missing_colon)
        valid, _ = ASTDoctor.inspect_syntax(healed)
        self.assertTrue(valid, f"Failed to heal colon: {healed}")
        self.assertGreater(len(fixes), 0)

        # 2. Unterminated string literal
        code_unclosed_str = 'def get_mesh_name():\n    return "GodotArrayMesh\n'
        healed, fixes = ASTDoctor.auto_heal_syntax(code_unclosed_str)
        valid, _ = ASTDoctor.inspect_syntax(healed)
        self.assertTrue(valid, f"Failed to heal string: {healed}")

        # 3. Unclosed parenthesis / bracket
        code_unclosed_bracket = "def build_coords():\n    return [Vector3(1, 2, 3), Vector3(4, 5, 6)\n"
        healed, fixes = ASTDoctor.auto_heal_syntax(code_unclosed_bracket)
        valid, _ = ASTDoctor.inspect_syntax(healed)
        self.assertTrue(valid, f"Failed to heal brackets: {healed}")

    def test_unicode_mathematical_identifiers(self):
        """Python 3 AST must parse Greek kinematic variables and 3D mathematical identifiers without errors."""
        math_code = """def compute_ebbinghaus_3d(α_alpha, θ_fov, λ_decay):
    # Greek letters used in 6DOF spatial traversal
    Δx = 10.5
    Σ_energy = α_alpha * θ_fov - λ_decay
    return Σ_energy + Δx
"""
        valid, issue = ASTDoctor.inspect_syntax(math_code)
        self.assertTrue(valid, f"Unicode mathematical syntax rejected: {issue}")

    def test_patch_collision_safety_and_hashing(self):
        """Patch applier must reject stale patches when concurrent disk mutations alter the file hash."""
        original_file = "class KinematicBody:\n    speed = 10.0\n    drag = 0.85\n"
        expected_hash = SafePatchApplier.compute_hash(original_file)

        patch = SurgicalPatch(
            search_block="    speed = 10.0\n",
            replace_block="    speed = 25.0\n",
            expected_hash=expected_hash,
        )

        # 1. Successful application when hash matches
        ok, patched, err = SafePatchApplier.apply_patch(original_file, patch)
        self.assertTrue(ok)
        self.assertIn("speed = 25.0", patched)
        self.assertIsNone(err)

        # 2. Rejection when file was concurrently modified on disk (hash mismatch)
        concurrently_modified = "class KinematicBody:\n    speed = 12.0\n    drag = 0.85\n"
        ok2, _, err2 = SafePatchApplier.apply_patch(concurrently_modified, patch)
        self.assertFalse(ok2)
        self.assertIn("Concurrent mutation detected", err2)

    def test_duplicate_block_rejection(self):
        """Search blocks matching more than once must be rejected to prevent ambiguous replacements."""
        file_with_duplicates = "val = 1\nval = 1\n"
        patch = SurgicalPatch(search_block="val = 1\n", replace_block="val = 2\n")
        ok, _, err = SafePatchApplier.apply_patch(file_with_duplicates, patch)
        self.assertFalse(ok)
        self.assertIn("appears 2 times", err)


if __name__ == "__main__":
    unittest.main()
