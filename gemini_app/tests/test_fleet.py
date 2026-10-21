"""Unit tests for Gemini Fleet Architecture (Protocol, Satellite, Mothership, Telemetry, HUD, Nodes, Autostart)."""

from pathlib import Path
import socket
import time
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.fleet.protocol import FleetMessage, get_local_lan_ip
from gemini_app.fleet.satellite import (
    SatelliteNode,
    collect_telemetry,
    execute_fleet_upgrade,
    get_saved_mothership,
    get_saved_mothership_port,
    save_mothership,
)
from gemini_app.fleet.mothership import MothershipServer
from gemini_app.fleet.hud import SatelliteHUD, clip_ansi, clip_str, render_meter_bar, strip_ansi
import gemini_app.fleet.security as fleet_sec
from gemini_app.fleet.telemetry import (
    collect_mothership_telemetry,
    get_cpu_and_mem_vitals,
    get_git_vitals,
    get_persisted_cognitive_state,
    update_cognitive_state,
)
import gemini_app.fleet.nodes as fleet_nodes
from gemini_app.fleet.nodes import (
    execute_ssh_rescue,
    get_dieablo_ssh_key,
    get_fleet_snapshot,
    load_nodes_registry,
    register_or_update_node,
    save_nodes_registry,
)
from gemini_app.fleet.autostart import (
    check_autostart_status,
    detect_init_system,
    install_autostart,
    remove_autostart,
    update_autostart_mothership,
)
from gemini_app.mind.screen import MindMapScreen, format_fleet_nodes_markdown


class TestFleetSecurity(unittest.TestCase):
    def test_key_generation_and_loading(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            kp = Path(td) / "fleet.key"
            k1 = fleet_sec.get_or_create_fleet_key(kp)
            self.assertEqual(len(k1), 64)  # 32 bytes hex
            k2 = fleet_sec.get_or_create_fleet_key(kp)
            self.assertEqual(k1, k2)

    def test_challenge_response_verification(self) -> None:
        key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        node_id = "test-node"
        nonce, ts = fleet_sec.generate_challenge()
        sig = fleet_sec.compute_auth_signature(key, node_id, nonce, ts)
        self.assertTrue(fleet_sec.verify_auth_signature(key, node_id, nonce, ts, sig))

        # Rejects tampered signature
        self.assertFalse(fleet_sec.verify_auth_signature(key, node_id, nonce, ts, "bad" + sig[3:]))

        # Rejects different node_id
        self.assertFalse(fleet_sec.verify_auth_signature(key, "other-node", nonce, ts, sig))

        # Rejects expired timestamp (> drift)
        self.assertFalse(fleet_sec.verify_auth_signature(key, node_id, nonce, ts - 120, sig))

    def test_command_signature_verification(self) -> None:
        key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        node_id = "test-node"
        action = "fleet_upgrade"
        ts = time.time()
        sig = fleet_sec.compute_command_signature(key, action, node_id, ts)
        self.assertTrue(fleet_sec.verify_command_signature(key, action, node_id, ts, sig))

        # Rejects forged action
        self.assertFalse(fleet_sec.verify_command_signature(key, "exec", node_id, ts, sig))


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

    def test_telemetry_and_event_types(self) -> None:
        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_TELEMETRY,
            node_id="mothership",
            payload={"cpu": 45},
        )
        raw = msg.serialize()
        deserialized = FleetMessage.deserialize(raw.decode("utf-8"))
        self.assertEqual(deserialized.type, FleetMessage.TYPE_TELEMETRY)
        self.assertEqual(deserialized.payload["cpu"], 45)

    def test_collect_telemetry(self) -> None:
        telem = collect_telemetry()
        self.assertIn("hostname", telem)
        self.assertIn("system", telem)
        self.assertIn("python", telem)
        self.assertIn("disk_free_gb", telem)
        self.assertIn("has_ipad_mount", telem)


class TestFleetTelemetryAndHUD(unittest.TestCase):
    def test_clip_str(self) -> None:
        self.assertEqual(clip_str("hello", 10), "hello")
        self.assertEqual(clip_str("hello world", 8), "hello...")
        self.assertEqual(clip_str("hello", 3), "hel")

    def test_render_meter_bar(self) -> None:
        bar = render_meter_bar(50.0, width=10)
        self.assertIn("50%", bar)
        self.assertIn("█", bar)
        self.assertIn("░", bar)

    def test_hud_render_structure(self) -> None:
        hud = SatelliteHUD(node_id="ipad-test-01", mothership_addr="192.168.1.90:7331")
        hud.update_telemetry({
            "host": "mothership-host",
            "platform": "Linux x86_64",
            "vitals": {"cpu_pct": 25.0, "mem_used_mb": 2048.0, "mem_total_mb": 8192.0, "disk_free_gb": 40.0},
            "git": {"branch": "main", "commit": "abc1234", "is_clean": True, "recent_commits": [{"sha": "abc1234", "message": "Initial test commit"}]},
            "cognitive": {"state_desc": "Pair Programming", "task": "Fleet HUD", "thought": "Testing layout", "tool": "apply_patch", "turn_number": 19},
        })
        hud.set_connection_status(True, ping_ms=18.5)
        hud.log_event("Connected to Mothership")

        rendered = hud.render()
        self.assertIn("GEMINI HUD", rendered)
        self.assertIn("ipad-test-01", rendered)
        self.assertIn("192.168.1.90:7331", rendered)
        self.assertIn("abc1234", rendered)
        self.assertIn("AI COGNITIVE STREAM", rendered)
        self.assertIn("Topic:", rendered)
        self.assertIn("Fleet HUD", rendered)
        self.assertIn("Testing layout", rendered)

    def test_hud_renders_without_task_duplication(self) -> None:
        hud = SatelliteHUD(node_id="ipad-test-01", mothership_addr="192.168.1.90:7331")
        hud.update_telemetry({
            "host": "mothership-host",
            "platform": "Linux",
            "vitals": {"cpu_pct": 10.0, "mem_used_mb": 1000.0, "mem_total_mb": 4000.0},
            "git": {"branch": "main", "commit": "1234567"},
            "cognitive": {
                "state_desc": "State: Deliberating",
                "task": "Task: Pair Programming on Autostart",
                "thought": "Testing HUD deduplication",
                "tool": "interact_ui",
                "turn_number": 5,
            },
        })
        rendered = hud.render()
        self.assertNotIn("Task:  Task:", rendered)
        self.assertNotIn("Task: Task:", rendered)
        self.assertNotIn("State:  State:", rendered)
        self.assertIn("Pair Programming on Autostart", rendered)

    def test_hud_ansi_clipping(self) -> None:
        raw_text = "HelloWorld"
        self.assertEqual(strip_ansi(raw_text), "HelloWorld")
        styled = "\033[1m\033[33mSuper Long Text Exceeding Limit\033[0m"
        clipped = clip_ansi(styled, 15)
        self.assertLessEqual(len(strip_ansi(clipped)), 15)
        self.assertTrue(clipped.endswith("\033[0m"))

    def test_collect_mothership_telemetry(self) -> None:
        telem = collect_mothership_telemetry()
        self.assertIn("host", telem)
        self.assertIn("platform", telem)
        self.assertIn("vitals", telem)
        self.assertIn("git", telem)
        self.assertIn("cognitive", telem)
        self.assertIn("cpu_pct", telem["vitals"])
        self.assertIn("branch", telem["git"])

    def test_update_and_persist_cognitive_state(self) -> None:
        st = update_cognitive_state(
            state_desc="Running test_suite",
            task="Validating HUD telemetry",
            thought="Testing dynamic cognitive updates",
            tool="execute_shell",
            turn_number=42,
            notify_mothership=False,
        )
        self.assertEqual(st.get("tool"), "execute_shell")
        self.assertEqual(st.get("turn_number"), 42)
        persisted = get_persisted_cognitive_state()
        self.assertEqual(persisted.get("tool"), "execute_shell")
        self.assertEqual(persisted.get("thought"), "Testing dynamic cognitive updates")

        telem = collect_mothership_telemetry()
        self.assertEqual(telem["cognitive"]["tool"], "execute_shell")
        self.assertEqual(telem["cognitive"]["thought"], "Testing dynamic cognitive updates")
        self.assertEqual(telem["cognitive"]["turn_number"], 42)


class TestFleetNetwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Find an open port
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.test_port = sock.getsockname()[1]
        sock.close()

    def setUp(self) -> None:
        import tempfile
        self._temp_dir = tempfile.TemporaryDirectory()
        t_path = Path(self._temp_dir.name)
        self._orig_fleet_dir = fleet_nodes.FLEET_DIR
        self._orig_registry_file = fleet_nodes.NODES_REGISTRY_FILE
        self._orig_active_file = fleet_nodes.ACTIVE_NODES_FILE
        fleet_nodes.FLEET_DIR = t_path
        fleet_nodes.NODES_REGISTRY_FILE = t_path / "nodes_registry.json"
        fleet_nodes.ACTIVE_NODES_FILE = t_path / "active_nodes.json"

        self.server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        self.assertTrue(self.server.start())
        self.test_port = self.server.port

    def tearDown(self) -> None:
        self.server.stop()
        fleet_nodes.FLEET_DIR = self._orig_fleet_dir
        fleet_nodes.NODES_REGISTRY_FILE = self._orig_registry_file
        fleet_nodes.ACTIVE_NODES_FILE = self._orig_active_file
        self._temp_dir.cleanup()

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

        # Test broadcast telemetry
        broadcast_count = self.server.broadcast_telemetry()
        self.assertEqual(broadcast_count, 1)

        # Test push cognitive event
        event_count = self.server.push_cognitive_event("Test cognitive event")
        self.assertEqual(event_count, 1)

        # Test Mothership receiving update_cognitive command over socket
        cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cmd_sock.connect(("127.0.0.1", self.test_port))
        cmd = FleetMessage(
            msg_type=FleetMessage.TYPE_COMMAND,
            node_id="console",
            payload={
                "action": "update_cognitive",
                "cognitive": {
                    "state_desc": "Patching files",
                    "task": "Dynamic HUD",
                    "thought": "Live tool stream test",
                    "tool": "apply_patch",
                    "turn_number": 99,
                },
            },
        )
        cmd_sock.sendall(cmd.serialize())
        time.sleep(0.15)
        cmd_sock.close()
        self.assertEqual(self.server._cognitive_override.get("tool"), "apply_patch")
        self.assertEqual(self.server._cognitive_override.get("thought"), "Live tool stream test")
        self.assertEqual(self.server._cognitive_override.get("turn_number"), 99)

        # Stop satellite cleanly
        satellite.stop()
        time.sleep(0.3)

        # Node should be dereferenced from active nodes
        nodes_after = self.server.list_nodes()
        self.assertEqual(len(nodes_after), 0)

    def test_rogue_node_rejection(self) -> None:
        """Verifies that an unauthorized node with an invalid signature is rejected."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", self.test_port))
        # Read challenge
        data = s.recv(2048).decode("utf-8")
        self.assertIn("challenge", data)

        # Send invalid signature
        rogue_auth = FleetMessage(
            msg_type=FleetMessage.TYPE_AUTH,
            node_id="rogue-imposter-node",
            payload={"signature": "bad_signature_0000000000000000", "timestamp": time.time()},
        )
        s.sendall(rogue_auth.serialize())
        resp_data = s.recv(2048).decode("utf-8")
        self.assertIn(FleetMessage.TYPE_AUTH_FAIL, resp_data)
        s.close()

        # Rogue node must not appear in server list
        self.assertEqual(len(self.server.list_nodes()), 0)


class TestFleetNodesAndAutostart(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._temp_dir = tempfile.TemporaryDirectory()
        t_path = Path(self._temp_dir.name)
        self._orig_fleet_dir = fleet_nodes.FLEET_DIR
        self._orig_registry_file = fleet_nodes.NODES_REGISTRY_FILE
        self._orig_active_file = fleet_nodes.ACTIVE_NODES_FILE
        fleet_nodes.FLEET_DIR = t_path
        fleet_nodes.NODES_REGISTRY_FILE = t_path / "nodes_registry.json"
        fleet_nodes.ACTIVE_NODES_FILE = t_path / "active_nodes.json"

    def tearDown(self) -> None:
        fleet_nodes.FLEET_DIR = self._orig_fleet_dir
        fleet_nodes.NODES_REGISTRY_FILE = self._orig_registry_file
        fleet_nodes.ACTIVE_NODES_FILE = self._orig_active_file
        self._temp_dir.cleanup()

    def test_get_dieablo_ssh_key(self) -> None:
        from gemini_app.fleet.keys import get_cluster_ssh_key, generate_cluster_keypair, save_cluster_key_path
        key = get_cluster_ssh_key()
        if key:
            self.assertIsInstance(key, Path)

    def test_cluster_keypair_generation(self) -> None:
        import tempfile
        from gemini_app.fleet.keys import generate_cluster_keypair, save_cluster_key_path, get_stored_cluster_key_path
        with tempfile.TemporaryDirectory() as td:
            target_key = Path(td) / "custom_cluster_key"
            priv, pub = generate_cluster_keypair(target_key)
            self.assertTrue(priv.exists())
            self.assertTrue(pub.exists())
            save_cluster_key_path(priv)
            stored = get_stored_cluster_key_path()
            self.assertEqual(stored, priv.resolve())

    def test_nodes_registry_crud(self) -> None:
        node = register_or_update_node(
            node_id="test-fedora-worker",
            host="192.168.1.150",
            ssh_user="dieablo",
            ssh_port=22,
            autostart="systemd",
            telemetry={"system": "Linux", "distro": "Fedora"},
        )
        self.assertEqual(node["node_id"], "test-fedora-worker")
        self.assertEqual(node["host"], "192.168.1.150")

        reg = load_nodes_registry()
        self.assertIn("test-fedora-worker", reg)

        snap = get_fleet_snapshot()
        self.assertGreaterEqual(snap["total_registered"], 1)

    @patch("subprocess.run")
    def test_execute_ssh_rescue(self, mock_run: MagicMock) -> None:
        register_or_update_node(
            node_id="test-rescue-node",
            host="192.168.1.200",
            ssh_user="dieablo",
        )
        mock_run.return_value = MagicMock(returncode=0, stdout="RESTART_DISPATCHED", stderr="")
        res = execute_ssh_rescue(node_id="test-rescue-node", action="restart")
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("action"), "restart")
        self.assertIn("RESTART_DISPATCHED", res.get("stdout"))

    def test_detect_init_system(self) -> None:
        init_sys = detect_init_system()
        self.assertIn(init_sys, ["systemd", "openrc", "ish", "launchd", "cron", "unknown"])

    @patch("os.path.exists")
    def test_detect_init_system_ish(self, mock_exists: MagicMock) -> None:
        def _mock_exists(p: str) -> bool:
            return p == "/proc/ish"
        mock_exists.side_effect = _mock_exists
        self.assertEqual(detect_init_system(), "ish")

    def test_format_fleet_nodes_markdown(self) -> None:
        md = format_fleet_nodes_markdown()
        self.assertIn("Mothership Fleet", md)
        self.assertIn("Satellites", md)

    def test_save_and_get_mothership_config(self) -> None:
        import gemini_app.fleet.satellite as sat_mod
        fake_cfg = Path(self._temp_dir.name) / "config.json"
        orig_cfg = sat_mod.CONFIG_FILE
        try:
            sat_mod.CONFIG_FILE = fake_cfg
            # Default before save
            self.assertEqual(get_saved_mothership("fallback.ip"), "fallback.ip")

            # Save IP and port
            self.assertTrue(save_mothership("192.168.1.199", port=8000))
            self.assertEqual(get_saved_mothership(), "192.168.1.199")
            self.assertEqual(get_saved_mothership_port(), 8000)

            # Node initialization defaults to saved config
            node = SatelliteNode()
            self.assertEqual(node.mothership_host, "192.168.1.199")
            self.assertEqual(node.mothership_port, 8000)
        finally:
            sat_mod.CONFIG_FILE = orig_cfg

    def test_update_autostart_mothership_content(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake_service = Path(td) / "gemini-satellite.service"
            fake_service.write_text("ExecStart=/usr/bin/python3 run.py node --mothership 192.168.1.50 --interval 10\n", encoding="utf-8")

            with patch("gemini_app.fleet.autostart.Path.home", return_value=Path(td)):
                # Patch systemd_paths inside update_autostart_mothership
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.read_text", return_value=fake_service.read_text()):
                        with patch("pathlib.Path.write_text") as mock_write:
                            res = update_autostart_mothership("192.168.1.91")
                            self.assertTrue(res)
                            mock_write.assert_called()
                            written_text = mock_write.call_args[0][0]
                            self.assertIn("--mothership 192.168.1.91", written_text)
                            self.assertNotIn("--mothership 192.168.1.50", written_text)

    def test_get_local_lan_ip(self) -> None:
        ip = get_local_lan_ip()
        self.assertIsInstance(ip, str)
        self.assertGreater(len(ip), 0)


if __name__ == "__main__":
    unittest.main()
