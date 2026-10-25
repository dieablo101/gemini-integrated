"""Unit tests for the iPad Multimodal Sketch-to-Code Pipeline."""

import base64
import os
from pathlib import Path
import tempfile
import unittest

from gemini_app.fleet.sketch_pipeline import (
    generate_scaffold_prompt,
    get_sketch_directories,
    ingest_sketch,
    list_sketches,
    scaffold_sketch_to_code,
    sync_ipad_sketches,
)
from gemini_app.tools.registry import ToolRegistry


class TestSketchPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp_dir.name)
        self.mock_sketches = self.base / "sketches"
        self.mock_sketches.mkdir(parents=True, exist_ok=True)

        # Create sample PNG sketch
        self.sample_png = self.mock_sketches / "dashboard_concept.png"
        self.sample_png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfake_png_data")

        # Create sample SVG sketch
        self.sample_svg = self.mock_sketches / "form_wireframe.svg"
        self.sample_svg.write_text('<svg><rect width="100" height="100"/></svg>', encoding="utf-8")

        # Create non-image file that should be ignored
        self.ignored_txt = self.mock_sketches / "notes.txt"
        self.ignored_txt.write_text("not an image", encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_list_sketches_filters_and_orders(self):
        sketches = list_sketches(search_dirs=[self.mock_sketches])
        self.assertEqual(len(sketches), 2)
        names = [s["name"] for s in sketches]
        self.assertIn("dashboard_concept.png", names)
        self.assertIn("form_wireframe.svg", names)
        self.assertNotIn("notes.txt", names)

    def test_ingest_sketch_png(self):
        res = ingest_sketch(str(self.sample_png), copy_to_vault=False)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("format"), "png")
        self.assertEqual(res.get("mime_type"), "image/png")
        self.assertTrue(res.get("base64_payload"))
        decoded = base64.b64decode(res["base64_payload"])
        self.assertTrue(decoded.startswith(b"\x89PNG"))

    def test_ingest_sketch_svg(self):
        res = ingest_sketch(str(self.sample_svg), copy_to_vault=False)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("format"), "svg")
        self.assertTrue(res.get("is_svg"))
        self.assertIn("<rect", res.get("svg_content", ""))

    def test_ingest_sketch_not_found(self):
        res = ingest_sketch("non_existent_sketch.png", copy_to_vault=False)
        self.assertEqual(res.get("status"), "error")
        self.assertIn("not found", res.get("message", "").lower())

    def test_scaffold_sketch_to_code_textual(self):
        res = scaffold_sketch_to_code(str(self.sample_png), target_framework="textual")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("target_framework"), "textual")
        self.assertTrue(res.get("has_base64_payload"))
        self.assertIn("Textual widget layout", res.get("scaffold_prompt", ""))
        self.assertTrue(res.get("recommended_output", "").endswith(".py"))

    def test_scaffold_sketch_to_code_html(self):
        res = scaffold_sketch_to_code(str(self.sample_png), target_framework="html")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("target_framework"), "html")
        self.assertIn("HTML5 + CSS3", res.get("scaffold_prompt", ""))
        self.assertTrue(res.get("recommended_output", "").endswith(".html"))

    def test_tool_registry_manage_fleet_nodes_sketch_actions(self):
        reg = ToolRegistry(working_dir=str(self.base), history=[])
        tools_list, tools = reg.get_tool_callables()
        manage_fleet = tools["manage_fleet_nodes"]

        # 1. Action: list_sketches
        list_res = manage_fleet(action="list_sketches")
        self.assertEqual(list_res.get("status"), "success")
        self.assertIsInstance(list_res.get("sketches"), list)

        # 2. Action: ingest_sketch
        ingest_res = manage_fleet(action="ingest_sketch", command=str(self.sample_png))
        self.assertEqual(ingest_res.get("status"), "success")
        self.assertEqual(ingest_res.get("name"), "dashboard_concept.png")

        # 3. Action: scaffold_sketch
        scaffold_res = manage_fleet(action="scaffold_sketch", command=str(self.sample_png), host="textual")
        self.assertEqual(scaffold_res.get("status"), "success")
        self.assertEqual(scaffold_res.get("target_framework"), "textual")


if __name__ == "__main__":
    unittest.main()
