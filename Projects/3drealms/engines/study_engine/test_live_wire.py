#!/usr/bin/env python3
import sys
import math
from pathlib import Path
import unittest
import numpy as np

STUDY_DIR = Path(__file__).resolve().parent
if str(STUDY_DIR) not in sys.path:
    sys.path.insert(0, str(STUDY_DIR))

from study_spec import (
    StudyProfile, get_default_study_profile, CameraSpec, EnvironmentSkyboxSpec
)
from live_wire_engine import (
    LiveSculptTwin, LiveWireStudyEngine, StrokeKineticEvent,
    BrushArchetype, CameraInspectionMode, SculptStage,
    CameraState, CameraInspectionAnalyzer, BrushKinematicClassifier,
    validate_session_name, compute_mesh_fingerprint, verify_mesh_match,
    save_in_progress_snapshot, check_in_progress_snapshot_exists,
    record_camera_snapto, cancel_and_scrub_session, finalize_livewire_session,
    list_all_livewire_sessions, LiveWireSessionManager, STUDIES_ROOT, PRODUCTION_ROOT,
    MidpointSnapshotRenderer, open_snapshot_viewer
)

class TestLiveWireStudyEngine(unittest.TestCase):

    def setUp(self):
        self.profile = get_default_study_profile()
        self.engine = LiveWireStudyEngine(profile=self.profile)

        # Initialize twin with a synthetic cube (8 vertices)
        # Centered around (0, 0, 0), bounds -1 to 1
        positions = np.array([
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]
        ], dtype=np.float32)
        self.engine.twin.positions = positions
        self.engine.twin.faces = [[0, 1, 2, 3], [4, 5, 6, 7]]
        self.engine.twin.update_bounds()

    def test_study_profile_serialization(self):
        profile_json = self.profile.to_json()
        loaded = StudyProfile.from_dict(self.profile.to_dict())
        self.assertEqual(loaded.name, self.profile.name)
        self.assertEqual(len(loaded.cameras), len(self.profile.cameras))
        self.assertEqual(len(loaded.environments), 5)
        self.assertEqual(len(loaded.lods), 3)

    def test_live_wire_sparse_delta_and_kinetics(self):
        # Apply a displacement stroke on vertices 2 and 6 (top-right cranium)
        stroke = self.engine.simulate_mock_stroke([2, 6], (0.0, 0.5, 0.0))
        self.assertIsNotNone(stroke)
        self.assertEqual(stroke.touched_vertices, 2)
        # Kinetic energy = 0.5 * sum(||dx||^2) = 0.5 * (0.25 + 0.25) = 0.25
        self.assertAlmostEqual(stroke.kinetic_energy, 0.25, places=4)
        self.assertEqual(self.engine.stats.total_strokes, 1)
        self.assertGreater(self.engine.stats.total_kinetic_energy, 0.0)
        self.assertTrue("Surface Region" in stroke.anatomical_region)

    def test_cadence_stroke_chunking_and_verification_events(self):
        # 1. Stroke chunk grouping within 1.5s
        s1 = self.engine.simulate_mock_stroke([0, 1], (0.0, 0.2, 0.0))
        self.assertIsNotNone(self.engine.active_stroke_chunk)
        self.assertEqual(self.engine.active_stroke_chunk.sub_strokes, 1)

        # 2. Rapid follow-up stroke within 1.5s
        s2 = self.engine.simulate_mock_stroke([2, 3], (0.0, 0.2, 0.0))
        self.assertEqual(self.engine.active_stroke_chunk.sub_strokes, 2)

        # 3. Idle triggers chunk close
        self.engine.active_stroke_chunk.last_delta_epoch -= 2.0
        self.engine.check_idle_cycle()
        self.assertIsNone(self.engine.active_stroke_chunk)

        mgr = LiveWireSessionManager.get_instance()
        self.assertGreaterEqual(len(mgr.verification_events), 1)
        recent = mgr.get_most_recent_event()
        self.assertIsNotNone(recent)
        self.assertEqual(recent.event_type, "stroke_chunk")
        self.assertEqual(recent.sub_stroke_count, 2)

    def test_topology_guard(self):
        # Mismatched vertex count should return None (safeguard for remeshing)
        bad_header = {
            "type": "mesh_delta",
            "count": 1,
            "vertex_count": 9999,
            "index_offset": 0,
            "position_offset": 4
        }
        res = self.engine.twin.apply_sparse_delta(bad_header, b"\x00" * 32)
        self.assertIsNone(res)

    def test_brush_classification_move_grab(self):
        # All vertices moving in the exact same direction (high directional coherence > 0.85)
        indices = [0, 1, 2, 3]
        stroke = self.engine.simulate_mock_stroke(indices, (0.0, 0.4, 0.0))
        self.assertIsNotNone(stroke)
        self.assertEqual(stroke.brush_archetype, BrushArchetype.MOVE_GRAB.value)
        self.assertGreater(stroke.directional_coherence, 0.85)

    def test_camera_silhouette_inspection_coupling(self):
        # Camera is situated on the +Z axis at (0, 0, 5) looking towards origin (0, 0, 0)
        # Hotspot is on the lateral edge (vertices 1 and 5) at (1.0, -1.0, 0.0) with normal in XY plane.
        # The view vector from (0,0,5) to (1,-1,0) has angle ~ 74 degrees to normal -> SILHOUETTE!
        cam = CameraState(
            camera_pos=np.array([0.0, 0.0, 5.0], dtype=np.float32),
            view_dir=np.array([0.0, 0.0, -1.0], dtype=np.float32)
        )
        self.engine.camera_state = cam
        
        stroke = self.engine.simulate_mock_stroke([1, 5], (0.2, 0.0, 0.0), camera=cam)
        self.assertIsNotNone(stroke)
        self.assertEqual(stroke.inspection_mode, CameraInspectionMode.SILHOUETTE_PROFILE.value)
        self.assertGreaterEqual(stroke.inspection_angle_deg, 70.0)

    def test_brush_transitions_and_stage_inference(self):
        # Perform a sequence of strokes: Move -> Clay -> Smooth -> Crease
        # 1. Move stroke
        self.engine.simulate_mock_stroke([0, 1, 2, 3], (0.0, 0.3, 0.0))
        # 2. Clay Buildup override
        self.engine.simulate_mock_stroke([2, 6], (0.1, 0.1, 0.0), active_brush_override=BrushArchetype.CLAY_BUILDUP.value)
        # 3. Smooth override
        self.engine.simulate_mock_stroke([2, 6], (0.01, 0.01, 0.0), active_brush_override=BrushArchetype.SMOOTH_RELAX.value)
        # 4. Crease override
        self.engine.simulate_mock_stroke([6], (-0.05, 0.0, 0.0), active_brush_override=BrushArchetype.CREASE_PINCH.value)

        stats = self.engine.stats
        self.assertGreaterEqual(stats.total_strokes, 4)
        
        # Verify Markov transition tracking
        transitions = stats.brush_transitions
        self.assertIn("clay_buildup", transitions)
        self.assertIn("smooth_relax", transitions["clay_buildup"])
        self.assertEqual(transitions["clay_buildup"]["smooth_relax"], 1)

    def test_session_name_validation(self):
        # Must enforce subfolder
        ok, err, f, fn = validate_session_name("pirate")
        self.assertFalse(ok)
        self.assertEqual(err, "must add subfolder Example: folder/filename")

        ok, err, f, fn = validate_session_name("pirates/oldcrazypirate")
        self.assertTrue(ok)
        self.assertEqual(f, "pirates")
        self.assertEqual(fn, "oldcrazypirate")

        ok, err, f, fn = validate_session_name("")
        self.assertFalse(ok)
        self.assertEqual(err, "please name your livewire session")

    def test_strict_vs_lenient_verification(self):
        twin1 = self.engine.twin
        # Create identical copy twin2
        twin2 = LiveSculptTwin()
        twin2.positions = twin1.positions.copy()
        twin2.faces = list(twin1.faces)
        twin2.update_bounds()

        # 1. 100% strict match for studies
        ok, msg, audit = verify_mesh_match(twin1, twin2, mode="studies")
        self.assertTrue(ok)
        self.assertEqual(audit["total_variances_detected"], 0)

        # 2. Modify 1 vertex slightly
        twin2.positions[0] += np.array([0.05, 0.0, 0.0], dtype=np.float32)
        twin2.update_bounds()

        # Strict check should fail
        ok, msg, audit = verify_mesh_match(twin1, twin2, mode="studies")
        self.assertFalse(ok)
        self.assertIn("Integrity Check Failed", msg)

        # Production lenient check should pass if under 3%
        ok_prod, msg_prod, audit_prod = verify_mesh_match(twin1, twin2, mode="production", tolerance_pct=3.0)
        self.assertTrue(ok_prod)
        self.assertIn("APPROVED_WITH_LENIENCY", audit_prod.get("status", ""))
        self.assertGreater(len(audit_prod["provenance_notes"]), 0)

    def test_in_progress_snapshot_and_camera_snapto(self):
        folder = "test_species"
        filename = "snap_test_unit"
        twin = self.engine.twin
        cam1 = CameraState(camera_pos=np.array([0.0, 0.0, 3.0], dtype=np.float32))

        # Save snapshot
        snap_meta = save_in_progress_snapshot(
            mode="studies",
            folder=folder,
            filename=filename,
            twin=twin,
            camera=cam1,
            stats=self.engine.stats
        )
        self.assertTrue(snap_meta.exists())
        self.assertTrue(check_in_progress_snapshot_exists("studies", folder, filename))

        # Camera rotation change -> record_camera_snapto
        cam2 = CameraState(camera_pos=np.array([2.0, 1.0, 3.0], dtype=np.float32))
        snapto = record_camera_snapto(
            mode="studies",
            folder=folder,
            filename=filename,
            from_camera={"camera_pos": [0.0, 0.0, 3.0]},
            to_camera=cam2
        )
        self.assertEqual(snapto["event"], "camera_snapto")
        self.assertIn("intentional camera snap-to", snapto["note"])

        # Test cancel & scrub
        ok_scrub, msg_scrub = cancel_and_scrub_session("studies", folder, filename)
        self.assertTrue(ok_scrub)
        self.assertFalse(check_in_progress_snapshot_exists("studies", folder, filename))

    def test_production_finalization_structure(self):
        folder = "test_pirates"
        filename = "captain_test"
        twin = self.engine.twin

        ok, msg, audit = finalize_livewire_session(
            mode="production",
            folder=folder,
            filename=filename,
            engine=self.engine,
            tolerance_pct=3.0
        )
        self.assertTrue(ok)
        sess_dir = PRODUCTION_ROOT / folder / filename
        self.assertTrue(sess_dir.exists())
        self.assertTrue((sess_dir / f"{filename}.fbx").exists())
        self.assertTrue((sess_dir / "production_leniency_audit.json").exists())

        # Clean up test session
        cancel_and_scrub_session("production", folder, filename)
        self.assertFalse(sess_dir.exists())

    def test_high_res_snapshot_and_viewer(self):
        folder = "test_sculpt"
        filename = "high_res_test"
        twin = self.engine.twin
        snap_meta = save_in_progress_snapshot(
            mode="studies",
            folder=folder,
            filename=filename,
            twin=twin,
            camera=CameraState(),
            stats=self.engine.stats
        )
        snap_dir = snap_meta.parent
        preview_png = snap_dir / "chkpt_001_preview.png"
        self.assertTrue(preview_png.exists())
        self.assertGreater(preview_png.stat().st_size, 500)

        # Test open_snapshot_viewer
        ok_view, msg_view = open_snapshot_viewer(preview_png)
        self.assertTrue(ok_view)
        self.assertIn("chkpt_001_preview.png", msg_view)

        # Test ANSI preview generation
        from PIL import Image
        im = Image.open(preview_png)
        ansi_text = MidpointSnapshotRenderer._generate_ansi_halfblocks(im, 36, 8)
        self.assertIn("▀", ansi_text)

        # Clean up
        cancel_and_scrub_session("studies", folder, filename)

if __name__ == "__main__":
    unittest.main()
