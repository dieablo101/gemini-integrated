"""Unit tests for Upper Mind automated milestone and shadow graph synchronization."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.cloud.auto_sync import (
    get_active_notes_and_topics,
    export_public_nexus_artifacts,
    sync_milestone_and_shadow_graph,
    PeriodicSyncWatcher,
)


class TestAutoSync(unittest.TestCase):

    def test_export_public_nexus_artifacts(self):
        """Verifies that public nexus artifacts are exported to public/api/."""
        success = export_public_nexus_artifacts()
        self.assertTrue(success)

        repo_root = Path(__file__).resolve().parent.parent.parent
        self.assertTrue((repo_root / "public" / "api" / "graph.json").is_file())
        self.assertTrue((repo_root / "public" / "api" / "telemetry.json").is_file())
        self.assertTrue((repo_root / "public" / "api" / "epiphanies.json").is_file())
        self.assertTrue((repo_root / "public" / "api" / "activity.json").is_file())

    def test_sync_milestone_and_shadow_graph_mocked(self):
        """Verifies full milestone synchronization pipeline with hosting deploy disabled."""
        with patch("gemini_app.cloud.auto_sync.sync_gemini_git_state", return_value=True):
            result = sync_milestone_and_shadow_graph(
                reason="unit_test_milestone",
                deploy_hosting=False,
                push_git=True,
                async_deploy=False,
            )
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["reason"], "unit_test_milestone")
            self.assertTrue(result["artifacts_exported"])
            self.assertTrue(result["git_synced"])

    def test_periodic_sync_watcher_lifecycle(self):
        """Verifies background sync watcher starts and stops cleanly."""
        watcher = PeriodicSyncWatcher(interval_seconds=0.1)
        self.assertFalse(watcher._running)
        watcher.start()
        self.assertTrue(watcher._running)
        watcher.stop()
        self.assertFalse(watcher._running)


if __name__ == "__main__":
    unittest.main()
