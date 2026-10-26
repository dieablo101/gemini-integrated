"""Tests for the Grim DAW Plugin."""

import unittest
from pathlib import Path
import tempfile
import os

from gemini_app.plugins.grim import GrimEngine


class TestGrimEngine(unittest.TestCase):
    def setUp(self):
        self.grim = GrimEngine()

    def test_grim_status(self):
        status = self.grim.get_status()
        self.assertIn("daw", status)
        self.assertEqual(status["daw"], "Grim Audio Subsystem")
        self.assertIn("default_sample_rate", status)
        self.assertEqual(status["default_sample_rate"], 44100)
        self.assertIn("workspace_type", status)
        self.assertIn(status["workspace_type"], ["standalone", "games", "embedded"])

    def test_workspace_resolution_priority(self):
        self.assertIsNotNone(self.grim.workspace_path)
        self.assertEqual(self.grim.workspace_type, "standalone")
        self.assertTrue(str(self.grim.workspace_path).endswith("Projects/grim"))
        if self.grim.bridge_script:
            self.assertTrue(str(self.grim.bridge_script).endswith("grim_reaper.py"))

    def test_create_project_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rpp_path = os.path.join(tmpdir, "test_session.rpp")
            res = self.grim.create_project_template("test_session", rpp_path, bpm=130.0)
            self.assertEqual(res["status"], "success")
            self.assertTrue(os.path.exists(rpp_path))
            with open(rpp_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("<REAPER_PROJECT", content)
            self.assertIn('NAME "ambient"', content)
            self.assertIn('NAME "drums"', content)
            self.assertIn("130.000000 4 4", content)

    def test_synthesize_dsp_sample(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "impact.wav")
            res = self.grim.synthesize_dsp_sample(wav_path, kind="impact", duration=0.1)
            self.assertEqual(res["status"], "success")
            self.assertTrue(os.path.exists(wav_path))
            self.assertGreater(os.path.getsize(wav_path), 100)


if __name__ == "__main__":
    unittest.main()
