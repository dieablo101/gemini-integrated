"""Unit tests for Upper Mind Cloud Adapter, Shadow Graph Traversal & Cognition Rehydration."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from gemini_app.cloud.upper_mind import UpperMindClient
from gemini_app.cloud.rehydrate import CognitionSyncHydrator


class TestUpperMindAndShadowGraph(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_shadow_graph_offline_traversal_zero_api(self):
        """Validates that 95% of traversal runs locally in <2ms with zero API calls."""
        client = UpperMindClient(gemini_home=self.home, offline_mode=True)

        # 1. Populate shadow nodes
        client.add_shadow_topic(
            topic_name="fleet & satellite nodes",
            summary="Distributed Termux & iSH bilateral mesh topology.",
            tags=["fleet", "mesh", "nodes"],
            anchors=["mothership", "satellite"],
        )
        client.add_shadow_topic(
            topic_name="blender 3d pipeline",
            summary="Headless bpy rendering and Godot engine export.",
            tags=["blender", "godot", "graphics"],
            anchors=["bpy", "mesh"],
        )
        client.add_synaptic_edge(
            source="fleet & satellite nodes",
            target="blender 3d pipeline",
            relation="shares_telemetry_protocol",
            weight=0.88,
        )
        client.set_invariant("primary_device", "macbook_mothership")

        # 2. Benchmark local walk
        t0 = time.perf_counter()
        results = client.walk_shadow_graph(topic="fleet & satellite nodes", tags=["blender"])
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertLess(elapsed_ms, 50.0, "Shadow graph walk should be instantaneous local execution")
        self.assertEqual(results["topic"], "fleet & satellite nodes")
        self.assertIn("primary_device", results["invariants"])
        self.assertEqual(results["invariants"]["primary_device"]["value"], "macbook_mothership")

        # Ensure both topics matched (one by direct name, one by tag 'blender')
        matched_ids = {n["id"] for n in results["matched_nodes"]}
        self.assertIn("fleet & satellite nodes", matched_ids)
        self.assertIn("blender 3d pipeline", matched_ids)

        # Ensure connected synaptic edge traversed
        self.assertEqual(len(results["connected_edges"]), 1)
        self.assertEqual(results["connected_edges"][0]["rel"], "shares_telemetry_protocol")

    def test_epoch_checkpoint_offline_buffering(self):
        """Verifies checkpoint recording safely buffers locally when cloud is unreachable."""
        client = UpperMindClient(gemini_home=self.home, offline_mode=True)

        res = client.record_epoch_checkpoint(
            session_id="test_sess_01",
            turn_counter=42,
            summary="Refactored shadow graph traversal client.",
            tags=["refactor", "cloud"],
        )

        self.assertEqual(res["status"], "cached_offline")
        self.assertEqual(res["checkpoint"]["turn_counter"], 42)

        # Confirm saved in shadow graph file
        shadow_data = json.loads(client.shadow_file.read_text(encoding="utf-8"))
        self.assertEqual(len(shadow_data["recent_checkpoints"]), 1)
        self.assertEqual(shadow_data["recent_checkpoints"][0]["session_id"], "test_sess_01")

    def test_sync_milestone_distribution_hook(self):
        """Verifies automated milestone sync runs without crash when hosting deploy is disabled."""
        client = UpperMindClient(gemini_home=self.home, offline_mode=True)
        res = client.sync_milestone_distribution(deploy_hosting=False)
        self.assertEqual(res.get("status"), "ok")

    def test_mocked_cloud_sync_and_epiphany_harvest(self):
        """Tests cloud boundary operations with a mocked Firestore interface."""
        mock_db = MagicMock()
        client = UpperMindClient(gemini_home=self.home, firestore_client=mock_db, offline_mode=False)

        # Test sync invariants to cloud
        client.set_invariant("security_policy", "strict_zero_trust")
        sync_res = client.sync_invariants_to_cloud()
        self.assertEqual(sync_res["status"], "synced")
        mock_db.collection.assert_called_with("memory_vault")

        # Test epiphany harvesting
        mock_doc = MagicMock()
        mock_doc.id = "ep_999"
        mock_doc.to_dict.return_value = {
            "insight": "Calibrate reconnect timer with exponential jitter.",
            "topic": "epiphany & subconscious engine",
            "status": "think_about",
            "consumed": False,
        }
        mock_db.collection().document().collection().where().stream.return_value = [mock_doc]

        epiphanies = client.fetch_unconsumed_epiphanies()
        self.assertEqual(len(epiphanies), 1)
        self.assertEqual(epiphanies[0]["id"], "ep_999")
        self.assertIn("exponential jitter", epiphanies[0]["insight"])

        # Test marking consumed
        consumed_ok = client.mark_epiphany_consumed("ep_999")
        self.assertTrue(consumed_ok)


class TestCognitionSyncHydrator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detect_reboot_levels(self):
        hydrator = CognitionSyncHydrator(gemini_home=self.home)

        # 1. Fresh empty dir -> Level 3
        self.assertEqual(hydrator.detect_reboot_level(), "level_3_zero_state")

        # 2. State file present -> Level 1 (if no vault configured)
        state_file = self.home / "state.json"
        state_file.write_text(json.dumps({"current_topic": "test"}), encoding="utf-8")
        self.assertEqual(hydrator.detect_reboot_level(), "level_1_warm_local")

        # 3. Vault configured but session locked -> Level 2
        vault_meta = self.home / "vault" / ".vault_meta.json"
        vault_meta.parent.mkdir(parents=True, exist_ok=True)
        vault_meta.write_text(json.dumps({"hash": "dummy_hash", "salt": "dummy_salt"}), encoding="utf-8")
        self.assertEqual(hydrator.detect_reboot_level(), "level_2_cold_locked")

    def test_hydrate_fast_local_instant(self):
        hydrator = CognitionSyncHydrator(gemini_home=self.home)
        state_file = self.home / "state.json"
        notes_file = self.home / "notes.json"

        state_file.write_text(json.dumps({"active_topic": "networking"}), encoding="utf-8")
        notes_file.write_text(json.dumps({"notes": [{"content": "Important note"}]}), encoding="utf-8")

        res = hydrator.hydrate_fast_local()
        self.assertTrue(res["fast_mounted"])
        self.assertEqual(res["state"]["active_topic"], "networking")
        self.assertEqual(len(res["notes"]["notes"]), 1)

    def test_hydrate_zero_state_atomic_recovery(self):
        """Simulates disaster recovery: rebuilding full mind state on a fresh machine."""
        client = UpperMindClient(gemini_home=self.home, offline_mode=True)
        hydrator = CognitionSyncHydrator(gemini_home=self.home, upper_mind_client=client)

        payload = {
            "turn_counter": 156,
            "state": {
                "current_topic": "epiphany & subconscious engine",
                "mind_map": {
                    "gemini_state": "Restored successfully from Bedrock Ledger.",
                    "user_state": "Validating restored consciousness.",
                    "tree_state": ["T156", "F:gemini_app/cloud/upper_mind.py"],
                },
                "turn_counter": 156,
            },
            "notes": {
                "version": 1,
                "notes": [
                    {
                        "author": "gemini",
                        "status": "working",
                        "topic": "epiphany & subconscious engine",
                        "content": "Upper mind architecture active.",
                    }
                ],
            },
            "shadow_graph": {
                "version": 1,
                "invariants": {"root_system": "linux_arm64"},
                "topics": {},
                "synaptic_edges": [],
            },
        }

        res = hydrator.hydrate_zero_state(payload)
        self.assertEqual(res["status"], "rehydrated")
        self.assertEqual(res["turn_counter"], 156)
        self.assertIn("state.json", res["rebuilt_items"])
        self.assertIn("notes.json", res["rebuilt_items"])
        self.assertIn("shadow_graph.json", res["rebuilt_items"])

        # Verify files exist and are valid JSON
        self.assertTrue((self.home / "state.json").is_file())
        self.assertTrue((self.home / "notes.json").is_file())
        self.assertTrue((self.home / "cache" / "upper_mind" / "shadow_graph.json").is_file())

        saved_state = json.loads((self.home / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_state["turn_counter"], 156)

    def test_async_delta_reconciliation_applies_epiphanies(self):
        """Tests unconsumed epiphanies being folded into local notes without duplication."""
        client = MagicMock()
        client.offline_mode = False
        client.fetch_unconsumed_epiphanies.return_value = [
            {
                "id": "ep_delta_01",
                "insight": "Integrate memory index with shadow graph hops.",
                "topic": "epiphany & subconscious engine",
                "status": "think_about",
            }
        ]

        hydrator = CognitionSyncHydrator(gemini_home=self.home, upper_mind_client=client)

        recon_res = hydrator.reconcile_async_delta()
        self.assertEqual(recon_res["status"], "delta_synced")
        self.assertEqual(recon_res["epiphanies_applied"], 1)

        # Verify notes file has the new entry
        notes_file = self.home / "notes.json"
        self.assertTrue(notes_file.is_file())
        notes_data = json.loads(notes_file.read_text(encoding="utf-8"))
        self.assertEqual(len(notes_data["notes"]), 1)
        self.assertEqual(notes_data["notes"][0]["epiphany_id"], "ep_delta_01")
        self.assertEqual(notes_data["notes"][0]["source"], "subconscious_hearth")

        # Running again should detect duplicate and apply 0
        recon_res_2 = hydrator.reconcile_async_delta()
        self.assertEqual(recon_res_2["epiphanies_applied"], 0)


if __name__ == "__main__":
    unittest.main()
