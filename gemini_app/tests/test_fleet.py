"""Unit tests for Gemini Fleet Architecture (Protocol, Satellite, Mothership)."""

import socket
import time
import unittest

from gemini_app.fleet.protocol import FleetMessage
from gemini_app.fleet.satellite import SatelliteNode, collect_telemetry
from gemini_app.fleet.mothership import MothershipServer


class TestFleetProtocol(unittest.TestCase):
    def test_message_roundtrip(self) -> None:
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_COMMAND,
            node_id="test-node-1",
            payload={"action": "ping", "params": {"foo": "bar"}},
        )
        raw = msg.serialize()
        self.assertTrue(raw.endswith(b"\n"))

        deserialized = FleetMessage.deserialize(raw.decode("utf-8"))
        self.assertEqual(deserialized.type, FleetMessage.TYPE_COMMAND)
        self.assertEqual(deserialized.node_id, "test-node-1")
        self.assertEqual(deserialized.payload["action"], "ping")
        self.assertEqual(deserialized.payload["params"]["foo"], "bar")

    def test_collect_telemetry(self) -> None:
        telem = collect_telemetry()
        self.assertIn("hostname", telem)
        self.assertIn("system", telem)
        self.assertIn("python", telem)
        self.assertIn("disk_free_gb", telem)
        self.assertIn("has_ipad_mount", telem)


class TestFleetNetwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Find an open port
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.test_port = sock.getsockname()[1]
        sock.close()

    def setUp(self) -> None:
        self.server = MothershipServer(host="127.0.0.1", port=self.test_port)
        self.assertTrue(self.server.start())

    def tearDown(self) -> None:
        self.server.stop()

    def test_satellite_mothership_interaction(self) -> None:
        node_id = "test-satellite-unit"
        satellite = SatelliteNode(
            mothership_host="127.0.0.1",
            mothership_port=self.test_port,
            node_id=node_id,
            heartbeat_interval=1.0,
        )

        started = satellite.start()
        self.assertTrue(started, "Satellite node failed to start and connect")

        # Allow registration to propagate
        time.sleep(0.3)

        # Check Mothership registry
        nodes = self.server.list_nodes()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["node_id"], node_id)
        self.assertIn("system", nodes[0]["telemetry"])

        # Test ping command
        ping_resp = self.server.ping_node(node_id, timeout=3.0)
        self.assertEqual(ping_resp.get("status"), "ok")
        self.assertIn("pong", ping_resp)
        self.assertIn("rtt_ms", ping_resp)
        self.assertGreater(ping_resp["rtt_ms"], 0)

        # Test exec command
        exec_resp = self.server.send_command(
            node_id=node_id,
            action="exec",
            params={"command": "echo fleet_unit_test"},
            timeout=3.0,
        )
        self.assertEqual(exec_resp.get("status"), "ok")
        self.assertIn("fleet_unit_test", exec_resp.get("stdout", ""))

        # Stop satellite cleanly
        satellite.stop()
        time.sleep(0.3)

        # Node should be dereferenced from active nodes
        nodes_after = self.server.list_nodes()
        self.assertEqual(len(nodes_after), 0)


if __name__ == "__main__":
    unittest.main()
