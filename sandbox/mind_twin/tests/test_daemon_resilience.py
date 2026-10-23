"""
Unit Tests for Cognitive Daemon Resilience, Lapse Recovery, and Fallback.
Verifies zero-hang degradation, lapse detection, autonomous reboot, and state re-sync.
"""
import unittest
import os
import shutil
import tempfile
import time

from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.state import CognitiveStateVector, FocusItem
from sandbox.mind_twin.core.lapse import LapseManager, LapseEvent
from sandbox.mind_twin.core.daemon import CognitiveDaemon, ResilientCognitiveSupervisor

class TestDaemonResilience(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.checkpoint_file = os.path.join(self.test_dir, "cognitive_checkpoint.json")
        self.graph = Hypergraph()
        # Seed test graph with proper vertex IDs
        self.graph.add_vertex("v_godot", "godot", vtype="engine")
        self.graph.add_vertex("v_blender", "blender", vtype="dcc")
        self.graph.add_vertex("v_shader", "shader", vtype="graphics")
        self.graph.add_hyperedge(["v_blender"], ["v_godot"], "exports_to", weight=0.8)
        self.graph.add_hyperedge(["v_godot"], ["v_shader"], "renders_with", weight=0.9)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_daemon_normal_lifecycle_and_checkpoint(self):
        daemon = CognitiveDaemon(self.checkpoint_file, hypergraph=self.graph)
        lapse = daemon.start(now=1000.0)
        self.assertTrue(daemon.ping())
        self.assertTrue(os.path.exists(self.checkpoint_file))

        # Process a query
        state, profile = daemon.process_query("godot shader", now=1005.0)
        self.assertGreater(len(state.focus_spotlight), 0)
        self.assertEqual(state.turn_counter, 1)

        # Verify checkpoint was written to disk
        lapse_mgr = LapseManager(self.checkpoint_file)
        loaded_state, hb = lapse_mgr.load_checkpoint()
        self.assertIsNotNone(loaded_state)
        self.assertEqual(hb, 1005.0)
        self.assertEqual(loaded_state.turn_counter, 1)

    def test_lapse_detection_and_decay(self):
        lapse_mgr = LapseManager(self.checkpoint_file, decay_alpha=0.05, decay_beta=0.5)
        
        # Initial warm state
        initial_state = CognitiveStateVector(
            session_id="test_session",
            timestamp=1000.0,
            turn_counter=5,
            focus_spotlight=[
                FocusItem(concept_id="godot", energy=0.9, primed_hops=1, last_activated=1000.0),
                FocusItem(concept_id="blender", energy=0.3, primed_hops=2, last_activated=1000.0)
            ]
        )
        lapse_mgr.save_checkpoint(initial_state, now=1000.0)

        # Simulate a 1-hour blackout lapse (3600 seconds)
        resume_time = 4600.0
        reconciled_state, lapse_event = lapse_mgr.reconcile_post_lapse(now=resume_time)

        self.assertTrue(lapse_event.restored)
        self.assertEqual(lapse_event.duration_seconds, 3600.0)
        self.assertEqual(lapse_event.pre_lapse_turn, 5)

        # Retention factor for Δt=3600: (1 + 0.05 * 3600)^(-0.5) = (1 + 180)^(-0.5) ≈ 1 / 13.45 ≈ 0.074
        # "godot" 0.9 * 0.074 ≈ 0.067 (< 0.1 threshold -> decayed out)
        # Verify items properly decayed over 1 hour
        self.assertEqual(len(reconciled_state.focus_spotlight), 0)
        self.assertEqual(lapse_event.decayed_spotlight_count, 2)

    def test_supervisor_immediate_fallback_on_crash(self):
        supervisor = ResilientCognitiveSupervisor(self.checkpoint_file, hypergraph=self.graph)
        self.assertEqual(supervisor.reboot_count, 1)
        self.assertEqual(supervisor.fallback_invocations, 0)

        # Run query 1 on alive daemon
        state1, used_fallback = supervisor.execute_query("godot", now=1000.0)
        self.assertFalse(used_fallback)
        self.assertEqual(state1.turn_counter, 1)

        # Simulate sudden crash of the daemon
        self.assertIsNotNone(supervisor.daemon)
        supervisor.daemon.simulate_crash()
        self.assertFalse(supervisor.daemon.ping())

        # Run query 2 while daemon is dead: MUST NOT RAISE ERROR OR CRASH
        # Supervisor provides instant in-process fallback and initiates reboot
        state2, used_fallback = supervisor.execute_query("blender", now=1010.0)
        self.assertTrue(used_fallback)
        self.assertEqual(supervisor.fallback_invocations, 1)
        self.assertEqual(supervisor.reboot_count, 2)  # Autonomously rebooted!
        self.assertIn("FALLBACK", state2.latent_intent)

        # Daemon should now be revived and healthy
        self.assertTrue(supervisor.daemon.ping())

        # Run query 3 on recovered daemon: should be back on native daemon!
        state3, used_fallback = supervisor.execute_query("shader", now=1020.0)
        self.assertFalse(used_fallback)
        self.assertTrue(state3.turn_counter >= 2)

    def test_buffered_events_reconciliation(self):
        lapse_mgr = LapseManager(self.checkpoint_file)
        state0 = CognitiveStateVector(session_id="test", timestamp=100.0, turn_counter=1)
        lapse_mgr.save_checkpoint(state0, now=100.0)

        # Buffer events during downtime
        lapse_mgr.buffer_event("query", {"query": "emergency sync item 1"}, timestamp=150.0)
        lapse_mgr.buffer_event("query", {"query": "emergency sync item 2"}, timestamp=180.0)

        # Reconcile at t=200.0
        reconciled_state, lapse = lapse_mgr.reconcile_post_lapse(now=200.0, hypergraph=self.graph)
        self.assertEqual(lapse.missed_events_count, 2)
        self.assertEqual(reconciled_state.turn_counter, 3)
        self.assertIn("emergency sync item 2", reconciled_state.latent_intent)

if __name__ == "__main__":
    unittest.main()
