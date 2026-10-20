"""Unit and visual verification tests for UI Snapshots and retention lifecycle."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

import gemini_app.config
from gemini_app.tools import snapshots
from gemini_app.ui.app import ChatApp


class TestSnapshotsLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.screenshots_dir = Path(self.temp_dir.name)

        # Mock SCREENSHOTS_DIR and INDEX_FILE in snapshots module and config
        self.orig_dir = snapshots.SCREENSHOTS_DIR
        self.orig_index = snapshots.INDEX_FILE
        self.orig_config_dir = gemini_app.config.SCREENSHOTS_DIR

        snapshots.SCREENSHOTS_DIR = self.screenshots_dir
        snapshots.INDEX_FILE = self.screenshots_dir / "snapshots_index.json"
        gemini_app.config.SCREENSHOTS_DIR = self.screenshots_dir

    def tearDown(self):
        snapshots.cleanup_test_snapshots()
        snapshots.SCREENSHOTS_DIR = self.orig_dir
        snapshots.INDEX_FILE = self.orig_index
        gemini_app.config.SCREENSHOTS_DIR = self.orig_config_dir
        self.temp_dir.cleanup()

    def test_ephemeral_snapshot_deleted_after_review(self):
        mock_app = MagicMock()
        mock_app.export_screenshot.return_value = "<svg><text x='10' y='20'>Console Output Line</text></svg>"
        mock_app.screen = MagicMock()
        mock_app.screen.__class__.__name__ = "ChatApp"

        # Capture via shortcut C-c ` (ephemeral)
        entry = snapshots.capture_ui_snapshot(mock_app, label="", taken_by="user", source="shortcut")
        self.assertFalse(entry["persistent"])
        self.assertTrue(entry["held"])

        svg_path = Path(entry["svg_path"])
        txt_path = Path(entry["txt_path"])
        self.assertTrue(svg_path.exists())
        self.assertTrue(txt_path.exists())
        self.assertEqual(len(snapshots.get_snapshot_index()), 1)

        # Review snapshot
        review_result = snapshots.review_held_snapshots(mark_as_reviewed=True)
        self.assertEqual(review_result["status"], "success")
        self.assertEqual(review_result["snapshots_reviewed"], 1)
        self.assertIn("Console Output Line", review_result["snapshots"][0]["screen_text"])

        # Check that ephemeral snapshot is deleted from disk and memory index
        self.assertFalse(svg_path.exists(), "Ephemeral SVG was not deleted from disk")
        self.assertFalse(txt_path.exists(), "Ephemeral TXT was not deleted from disk")
        self.assertEqual(len(snapshots.get_snapshot_index()), 0, "Ephemeral entry not removed from memory/index")

    def test_named_command_snapshot_preserved_after_review(self):
        mock_app = MagicMock()
        mock_app.export_screenshot.return_value = "<svg><text x='10' y='20'>Named Audit Line</text></svg>"
        mock_app.screen = MagicMock()
        mock_app.screen.__class__.__name__ = "ChatApp"

        # Capture via command with a name (persistent)
        entry = snapshots.capture_ui_snapshot(mock_app, label="my_audit_screen", taken_by="user", source="command")
        self.assertTrue(entry["persistent"])
        self.assertTrue(entry["held"])
        self.assertIn("my_audit_screen", entry["id"])

        svg_path = Path(entry["svg_path"])
        txt_path = Path(entry["txt_path"])
        self.assertTrue(svg_path.exists())
        self.assertTrue(txt_path.exists())

        # Review snapshot
        review_result = snapshots.review_held_snapshots(mark_as_reviewed=True)
        self.assertEqual(review_result["status"], "success")
        self.assertEqual(review_result["snapshots_reviewed"], 1)
        self.assertIn("Named Audit Line", review_result["snapshots"][0]["screen_text"])

        # Check that persistent snapshot is PRESERVED on disk and held is False
        self.assertTrue(svg_path.exists(), "Named command snapshot SVG should be preserved on disk")
        self.assertTrue(txt_path.exists(), "Named command snapshot TXT should be preserved on disk")
        index = snapshots.get_snapshot_index()
        self.assertEqual(len(index), 1, "Named command snapshot should remain in index")
        self.assertFalse(index[0]["held"], "Snapshot should be marked as reviewed (held=False)")
        self.assertEqual(index[0]["label"], "my_audit_screen")

    async def test_live_ui_visual_integrity_check(self):
        """End-to-end visual integrity check: mounts ChatApp, takes snapshot, validates rendering."""
        app = ChatApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Take a named snapshot of the live UI
            entry = snapshots.capture_ui_snapshot(app, label="visual_integrity_check", source="command")
            self.assertTrue(Path(entry["svg_path"]).exists())
            self.assertTrue(Path(entry["txt_path"]).exists())

            # Read text dump extracted from SVG
            txt_content = Path(entry["txt_path"]).read_text(encoding="utf-8")
            svg_content = Path(entry["svg_path"]).read_text(encoding="utf-8")

            # Check that SVG contains valid visual canvas and markup
            self.assertIn("<svg", svg_content)
            self.assertIn("</svg>", svg_content)

            # Check that essential console UI components are present in screen render
            self.assertTrue(
                any(key in txt_content for key in ["^q", "quit", "^c", "commands", "Mind", "Fork"]),
                f"Visual layout missing footer/navigation anchors. Dump:\n{txt_content}",
            )

    def test_cleanup_test_snapshots(self):
        mock_app = MagicMock()
        mock_app.export_screenshot.return_value = "<svg><text>Test Line</text></svg>"
        mock_app.screen = MagicMock()
        mock_app.screen.__class__.__name__ = "ChatApp"

        # Capture a test snapshot and a user persistent snapshot
        entry_test = snapshots.capture_ui_snapshot(mock_app, label="visual_integrity_check", source="command")
        entry_audit = snapshots.capture_ui_snapshot(mock_app, label="post_reboot_audit", source="command")
        entry_user = snapshots.capture_ui_snapshot(mock_app, label="user_important_shot", source="command")

        self.assertEqual(len(snapshots.get_snapshot_index()), 3)
        self.assertTrue(Path(entry_test["svg_path"]).exists())
        self.assertTrue(Path(entry_audit["svg_path"]).exists())
        self.assertTrue(Path(entry_user["svg_path"]).exists())

        # Run cleanup_test_snapshots
        purged = snapshots.cleanup_test_snapshots()
        self.assertEqual(purged, 2)

        # Test and audit files deleted
        self.assertFalse(Path(entry_test["svg_path"]).exists())
        self.assertFalse(Path(entry_audit["svg_path"]).exists())
        # User snapshot preserved
        self.assertTrue(Path(entry_user["svg_path"]).exists())

        remaining = snapshots.get_snapshot_index()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["label"], "user_important_shot")

    def test_prune_audit_snapshots(self):
        mock_app = MagicMock()
        mock_app.export_screenshot.return_value = "<svg><text>Audit Line</text></svg>"
        mock_app.screen = MagicMock()
        mock_app.screen.__class__.__name__ = "ChatApp"

        # Capture 3 audit snapshots
        e1 = snapshots.capture_ui_snapshot(mock_app, label="post_reboot_audit", source="command")
        e2 = snapshots.capture_ui_snapshot(mock_app, label="post_reboot_audit", source="command")

        # Because capture_ui_snapshot automatically prunes prior post_reboot_audits,
        # only the latest post_reboot_audit should survive!
        index = snapshots.get_snapshot_index()
        audit_entries = [e for e in index if e.get("label") == "post_reboot_audit"]
        self.assertEqual(len(audit_entries), 1)
        self.assertEqual(audit_entries[0]["id"], e2["id"])
        self.assertFalse(Path(e1["svg_path"]).exists())
        self.assertTrue(Path(e2["svg_path"]).exists())

    def test_delete_all_snapshots(self):
        mock_app = MagicMock()
        mock_app.export_screenshot.return_value = "<svg><text>Any Line</text></svg>"
        mock_app.screen = MagicMock()
        mock_app.screen.__class__.__name__ = "ChatApp"

        snapshots.capture_ui_snapshot(mock_app, label="snap1", source="command")
        snapshots.capture_ui_snapshot(mock_app, label="snap2", source="command")
        self.assertEqual(len(snapshots.get_snapshot_index()), 2)

        count = snapshots.delete_all_snapshots()
        self.assertEqual(count, 2)
        self.assertEqual(len(snapshots.get_snapshot_index()), 0)
        self.assertEqual(list(self.screenshots_dir.glob("snapshot_*")), [])


if __name__ == "__main__":
    unittest.main()
