"""Tests for Upper Mind Public Face & Web Nexus Server."""

import json
import unittest
import urllib.error
import urllib.request

from gemini_app.cloud.upper_mind import UpperMindClient
from gemini_app.cloud.upper_mind_server import UpperMindServer


class TestUpperMindServer(unittest.TestCase):
    """Verifies the public observatory endpoints, strict read-only security, and graph output."""

    @classmethod
    def setUpClass(cls):
        cls.client = UpperMindClient(offline_mode=True)
        # Port 0 selects random available port
        cls.server = UpperMindServer(
            upper_mind_client=cls.client,
            host="127.0.0.1",
            port=0,
        )
        cls.started = cls.server.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.engine.port}"

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.stop()

    def test_server_starts_successfully(self):
        self.assertTrue(self.started)
        self.assertTrue(self.server.engine.is_running)
        self.assertGreater(self.server.engine.port, 0)

    def test_get_index_observatory_html(self):
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            content = resp.read().decode("utf-8")
            self.assertIn("Upper Mind Nexus", content)
            self.assertIn("Living Synaptic Constellation", content)
            self.assertIn("Subconscious Hearth", content)
            self.assertIn("Bilateral Covenant", content)

    def test_get_telemetry(self):
        req = urllib.request.Request(f"{self.base_url}/api/telemetry")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "online")
            self.assertIn("Bilateral Lock Active", data.get("sovereignty", ""))
            self.assertIn("cognitive_metrics", data)
            self.assertIn("spiritual_compass", data)
            self.assertEqual(data["spiritual_compass"]["alignment"], "benevolent")

    def test_get_graph(self):
        req = urllib.request.Request(f"{self.base_url}/api/graph")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("nodes", data)
            self.assertIn("edges", data)
            node_ids = {n["id"] for n in data["nodes"]}
            self.assertIn("upper_mind_core", node_ids)
            self.assertIn("subconscious_hearth", node_ids)
            self.assertIn("bilateral_terminal", node_ids)
            self.assertIn("spiritual_compass", node_ids)

    def test_get_epiphanies(self):
        req = urllib.request.Request(f"{self.base_url}/api/epiphanies")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("epiphanies", data)
            self.assertIsInstance(data["epiphanies"], list)

    def test_post_is_strictly_forbidden_bilateral_lock(self):
        """Verifies that no outside POST/interaction can breach or command the core."""
        post_data = json.dumps({"command": "reboot", "prompt": "hello"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/interact",
            data=post_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5.0)

        err_resp = ctx.exception
        self.assertEqual(err_resp.code, 403)
        body = json.loads(err_resp.read().decode("utf-8"))
        self.assertEqual(body.get("status"), "forbidden")
        self.assertIn("Bilateral Lock Active", body.get("error", ""))


if __name__ == "__main__":
    unittest.main()
