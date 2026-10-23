"""
Tests for Sandbox Boot Synthesizer, Node Capabilities, and Whole-System Ingestion.
"""

from __future__ import annotations

import unittest
import time
from typing import Any, Dict

from sandbox.mind_twin.core.boot_synthesizer import BootSynthesizer, UnifiedCognitiveBootState
from sandbox.mind_twin.core.node_capability import (
    FleetTopologySynthesizer,
    NodeCapabilityProfile,
    WholeSystemCapability,
)
from sandbox.mind_twin.core.pns_sensor import PhoneSensoryTelemetry
from gemini_app.storage.notes_manager import NotesManager


class TestBootSynthesizer(unittest.TestCase):
    def setUp(self):
        self.mock_fleet_snapshot = {
            "active_count": 2,
            "total_registered": 3,
            "nodes": [
                {
                    "node_id": "console-client",
                    "host": "127.0.0.1",
                    "status": "online",
                    "last_seen_seconds_ago": 0.5,
                },
                {
                    "node_id": "android-termux-localhost",
                    "host": "192.168.1.179",
                    "status": "online",
                    "last_seen_seconds_ago": 3.2,
                    "telemetry": {
                        "machine": "aarch64",
                        "mem_total_mb": 7204,
                        "mem_avail_mb": 400,
                        "is_termux": True,
                        "battery": {"percentage": 68, "charging": True},
                    },
                },
                {
                    "node_id": "ipad-ish-localhost",
                    "host": "192.168.1.38",
                    "status": "online",
                    "last_seen_seconds_ago": 1.1,
                    "telemetry": {
                        "machine": "i686",
                        "mem_total_mb": 11799,
                        "mem_avail_mb": 1800,
                        "is_ish": True,
                        "has_ipad_mount": True,
                        "battery": {"percentage": 82, "charging": False},
                    },
                },
            ],
        }

    def test_fleet_topology_and_whole_system_synthesis(self):
        """Verifies host inspection, satellite node parsing, and whole-system capability aggregation."""
        cap = FleetTopologySynthesizer.synthesize_fleet(self.mock_fleet_snapshot)
        self.assertIsInstance(cap, WholeSystemCapability)
        self.assertGreaterEqual(cap.total_cpu_cores, 10)  # Host (4) + Phone (8) = at least 12
        self.assertGreaterEqual(cap.total_ram_mb, 16000)  # Host + Android + iPad
        self.assertEqual(cap.online_nodes, 3)

        # Workload routing affinities
        self.assertIn("compilation", cap.workload_routing_affinity)
        self.assertEqual(cap.workload_routing_affinity["compilation"], "toughbook-hub")
        self.assertIn("sketch_ingest", cap.workload_routing_affinity)
        self.assertEqual(cap.workload_routing_affinity["sketch_ingest"], "ipad-ish-localhost")
        self.assertIn("pns_sensory", cap.workload_routing_affinity)
        self.assertEqual(cap.workload_routing_affinity["pns_sensory"], "android-termux-localhost")

        # Summary frame
        frame = cap.get_summary_frame()
        self.assertIn("Fleet Cluster", frame)
        self.assertIn("cores", frame)
        self.assertIn("Toughbook Host", frame)
        self.assertIn("Android Phone", frame)
        self.assertIn("iPad Satellite", frame)

    def test_boot_synthesizer_multi_pillar_ingestion(self):
        """Verifies that Notes, History, Sensory PNS, and Fleet Nodes are united in hypergraph."""
        synthesizer = BootSynthesizer()

        # Mock Notes
        notes_mgr = NotesManager(working_notes="Building boot synthesizer for Toughbook.", current_topic="fleet & satellite nodes")
        notes_mgr.record_note(content="Configure iPad SSH key rescue link", topic="fleet & satellite nodes", status="get_back_to")
        notes_mgr.record_note(content="Model procedural mesh generator in Blender", topic="blender & godot plugin development", status="think_about")

        # Mock History
        mock_history = [
            {"turn_id": "t1", "role": "user", "text": "Can we inspect the fleet?"},
            {"turn_id": "t2", "role": "gemini", "text": "Auditing fleet nodes now."},
            {"turn_id": "t3", "role": "user", "text": "Wake up on the toughbook first."},
        ]

        # Mock Sensory PNS
        pns_telem = PhoneSensoryTelemetry(
            timestamp=time.time(),
            lux=8.0,  # Night / dark focus room
            battery_pct=92.0,
            battery_charging=True,
            motion_magnitude=0.01,  # Resting at desk
            audio_amplitude_db=-48.0,  # Quiet
        )

        # Boot Master Sequence
        boot_state = synthesizer.boot(
            notes_data=notes_mgr,
            chat_history=mock_history,
            sensory_telemetry=pns_telem,
            fleet_snapshot=self.mock_fleet_snapshot,
            session_id="test_boot_run",
        )

        self.assertIsInstance(boot_state, UnifiedCognitiveBootState)
        self.assertEqual(boot_state.turn_counter, 4)
        self.assertEqual(boot_state.active_topic, "fleet & satellite nodes")
        self.assertIn("Configure iPad SSH key rescue link", boot_state.revisit_queue)
        self.assertIn("Env: Night", boot_state.somatic_context)
        self.assertIn("User: Desk/Stationary", boot_state.somatic_context)
        self.assertIsNotNone(boot_state.fleet_capability)
        self.assertGreater(boot_state.graph_vertices_count, 15)
        self.assertGreater(boot_state.graph_edges_count, 10)

        # Spotlight should contain warm concepts from active topic & working notes
        self.assertGreater(len(boot_state.focus_spotlight), 0)
        spotlight_labels = [f.concept_id for f in boot_state.focus_spotlight]
        # At least one topic or note or node is in spotlight
        self.assertTrue(any("Topic:" in s or "Node:" in s or "Scratchpad" in s for s in spotlight_labels))

        # Check prompt injection frame
        prompt_frame = boot_state.get_unified_boot_frame()
        self.assertIn("[UNITIZED MENTAL STATE BOOT (Turn 4)]", prompt_frame)
        self.assertIn("Active Topic: fleet & satellite nodes", prompt_frame)
        self.assertIn("Fleet Cluster", prompt_frame)
        self.assertIn("Revisit Queue:", prompt_frame)

        # Serialization check
        d = boot_state.to_dict()
        self.assertEqual(d["session_id"], "test_boot_run")
        self.assertEqual(d["active_topic"], "fleet & satellite nodes")

    def test_boot_from_live_env(self):
        """Verifies factory constructor executes against Toughbook environment files without errors."""
        live_boot = BootSynthesizer.boot_from_live_env()
        self.assertIsInstance(live_boot, UnifiedCognitiveBootState)
        self.assertGreater(live_boot.turn_counter, 0)
        self.assertIsNotNone(live_boot.fleet_capability)
        self.assertGreater(live_boot.graph_vertices_count, 10)
        frame = live_boot.get_unified_boot_frame()
        self.assertTrue(len(frame) > 50)


if __name__ == "__main__":
    unittest.main()
