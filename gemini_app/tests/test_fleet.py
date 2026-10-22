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
        self.assertIn("network", telem)
        self.assertIn("lan_ip", telem["network"])
        self.assertIn("wan_ip", telem["network"])
        self.assertIn("port", telem["network"])
        self.assertIn("cpu_pct", telem["vitals"])
        self.assertIn("branch", telem["git"])

    def test_dual_ip_persistence_and_lan_detection(self) -> None:
        from gemini_app.fleet.satellite import (
            is_lan_address,
            save_mothership_dual_endpoints,
            get_saved_mothership_endpoints,
            acquire_singleton_lock,
        )
        self.assertTrue(is_lan_address("192.168.1.91"))
        self.assertTrue(is_lan_address("10.0.0.5"))
        self.assertTrue(is_lan_address("172.16.0.1"))
        self.assertTrue(is_lan_address("127.0.0.1"))
        self.assertFalse(is_lan_address("203.0.113.199"))
        self.assertFalse(is_lan_address("8.8.8.8"))

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            from gemini_app.fleet import satellite
            orig_cfg = satellite.CONFIG_FILE
            satellite.CONFIG_FILE = Path(td) / "config.json"
            try:
                save_mothership_dual_endpoints(lan_ip="192.168.1.91", wan_ip="203.0.113.199", port=7331)
                lan, wan, p = get_saved_mothership_endpoints()
                self.assertEqual(lan, "192.168.1.91")
                self.assertEqual(wan, "203.0.113.199")
                self.assertEqual(p, 7331)
            finally:
                satellite.CONFIG_FILE = orig_cfg

        self.assertTrue(acquire_singleton_lock("test-mode"))

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

        self.server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False, require_auth=True)
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

        try:
            started = satellite.start()
            self.assertTrue(started, "Satellite node failed to start and connect")

            # Allow registration and authentication challenge to propagate
            for _ in range(25):
                if self.server.list_nodes():
                    break
                time.sleep(0.1)

            # Check Mothership registry
            nodes = self.server.list_nodes()
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["node_id"], node_id)
            self.assertIn("system", nodes[0]["telemetry"])

            # Test ping command
            ping_resp = self.server.ping_node(node_id, timeout=3.0)
            self.assertEqual(ping_resp.get("status"), "ok", f"Ping failed: {ping_resp}")
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
        finally:
            satellite.stop()

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

    def test_rendezvous_ip_migration_dispatch(self) -> None:
        """Tests inbound rendezvous listener updating node endpoints when Mothership IP migrates."""
        node_id = "test-rendezvous-node"
        satellite = SatelliteNode(
            mothership_host="127.0.0.1",
            mothership_port=self.test_port,
            node_id=node_id,
            heartbeat_interval=1.0,
        )
        try:
            started = satellite.start()
            self.assertTrue(started)

            # Wait briefly for rendezvous listener and registration to stabilize
            for _ in range(50):
                if getattr(satellite, "_rendezvous_sock", None) is not None:
                    break
                time.sleep(0.05)
            time.sleep(0.1)

            register_or_update_node(
                node_id=node_id,
                host="127.0.0.1",
                telemetry={"system": "Linux"},
            )

            # Temporarily allow 127.0.0.1 in notify_fleet_of_ip_change for test
            with patch("gemini_app.fleet.nodes.load_nodes_registry", return_value={
                node_id: {"host": "127.0.0.1", "ssh_port": None}
            }):
                results = self.server.notify_fleet_of_ip_change(
                    new_lan_ip="192.168.1.250",
                    new_wan_ip="203.0.113.199",
                    port=self.test_port,
                    timeout=2.0,
                )
            self.assertIn(node_id, results)
            self.assertEqual(results[node_id]["status"], "ok")
            for _ in range(50):
                if satellite.lan_host == "192.168.1.250":
                    break
                time.sleep(0.05)
            self.assertEqual(satellite.lan_host, "192.168.1.250")
            self.assertEqual(satellite.wan_host, "203.0.113.199")
        finally:
            satellite.stop()

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

        # Verify reboot also safely dispatches satellite daemon restart instead of kernel reboot
        res_reboot = execute_ssh_rescue(node_id="test-rescue-node", action="reboot")
        self.assertEqual(res_reboot.get("status"), "ok")
        self.assertEqual(res_reboot.get("action"), "reboot")
        # Check command passed to ssh includes .venv detection
        call_args = mock_run.call_args[0][0]
        self.assertIn(".venv/bin/python", call_args[-1])

    def test_detect_init_system(self) -> None:
        init_sys = detect_init_system()
        self.assertIn(init_sys, ["systemd", "openrc", "ish", "launchd", "cron", "unknown"])

    @patch("os.path.exists")
    def test_detect_init_system_ish(self, mock_exists: MagicMock) -> None:
        def _mock_exists(p: str) -> bool:
            return p == "/proc/ish"
        mock_exists.side_effect = _mock_exists
        self.assertEqual(detect_init_system(), "ish")

    def test_detect_init_system_termux(self) -> None:
        with patch.dict("os.environ", {"TERMUX_VERSION": "0.118.0"}):
            self.assertEqual(detect_init_system(), "termux")

    def test_termux_platform_detection(self) -> None:
        from gemini_app.fleet.satellite import is_termux_platform
        with patch.dict("os.environ", {"TERMUX_VERSION": "0.118.0"}):
            self.assertTrue(is_termux_platform())

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
                # Patch systemd_paths and subprocess inside update_autostart_mothership
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.read_text", return_value=fake_service.read_text()):
                        with patch("pathlib.Path.write_text") as mock_write:
                            with patch("gemini_app.fleet.autostart.subprocess.run") as mock_subproc:
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

    def test_ish_safe_hud_render(self) -> None:
        from gemini_app.fleet.hud import SatelliteHUD
        hud = SatelliteHUD("test-node", "127.0.0.1:7331", local_commit="ed0af37")
        hud.is_ish = True
        hud.update_telemetry({
            "host": "mothership",
            "platform": "Linux",
            "vitals": {"cpu_pct": 25.0, "mem_used_mb": 1024, "mem_total_mb": 4096},
            "git": {"commit": "da74e10", "branch": "main", "is_clean": True},
            "cognitive": {"state_desc": "Standing By", "task": "Idle", "tool": "none"},
        })
        frame = hud.render()
        self.assertIn("[GEMINI HUD]", frame)
        self.assertIn("[AI COGNITIVE STREAM]", frame)
        self.assertIn("ms:da74e10", frame)
        self.assertIn("node:ed0af37", frame)

    def test_check_ipad_mount_caching(self) -> None:
        from gemini_app.fleet.satellite import check_ipad_mount
        has_mount, count = check_ipad_mount()
        self.assertIsInstance(has_mount, bool)
        self.assertIsInstance(count, int)

    def test_satellite_auto_upgrade_flag(self) -> None:
        node = SatelliteNode("127.0.0.1", 7331, auto_upgrade=True)
        self.assertTrue(node.auto_upgrade)
        self.assertFalse(node._is_upgrading)

    def test_find_repo_root(self) -> None:
        from gemini_app.fleet.satellite import find_repo_root
        root = find_repo_root()
        self.assertTrue((root / ".git").is_dir())

    def test_mothership_upgrade_cooldown_escalation(self) -> None:
        """Verifies MothershipServer tracks upgrade attempts and escalates cooldown."""
        server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        sat = MagicMock()
        sat.telemetry = {"git_commit": "old_commit_1"}
        server.nodes["node-test-1"] = sat

        with patch("gemini_app.fleet.mothership._get_git_info_fast") as mock_git:
            mock_git.return_value = ("new_commit_9", "main")
            with patch.object(server, "upgrade_node") as mock_up:
                # First checkin: triggers upgrade dispatch with 45s cooldown
                server._check_node_auto_upgrades()
                time.sleep(0.05)
                self.assertIn("node-test-1", server._node_upgrade_attempts)
                self.assertEqual(server._node_upgrade_attempts["node-test-1"], ("new_commit_9", 1))
                self.assertEqual(mock_up.call_count, 1)

                # Immediately checking again should be throttled by cooldown
                server._check_node_auto_upgrades()
                time.sleep(0.05)
                self.assertEqual(mock_up.call_count, 1)

                # Simulate second attempt after cooldown: attempts count increases to 2
                server._upgrade_cooldowns["node-test-1"] = time.time() - 50.0
                server._check_node_auto_upgrades()
                time.sleep(0.05)
                self.assertEqual(server._node_upgrade_attempts["node-test-1"], ("new_commit_9", 2))
                self.assertEqual(mock_up.call_count, 2)

                # Now with attempts >= 2, cooldown is 120s: 50s elapse should not trigger dispatch
                server._upgrade_cooldowns["node-test-1"] = time.time() - 50.0
                server._check_node_auto_upgrades()
                time.sleep(0.05)
                self.assertEqual(mock_up.call_count, 2)

                # Once node upgrades and reports new commit, attempts tracking is cleared
                sat.telemetry = {"git_commit": "new_commit_9"}
                server._check_node_auto_upgrades()
                time.sleep(0.05)
                self.assertNotIn("node-test-1", server._node_upgrade_attempts)

    def test_execute_fleet_upgrade_target_commit_sync(self) -> None:
        """Verifies execute_fleet_upgrade writes target_commit to git ref heads."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            repo_path = Path(td)
            git_heads = repo_path / ".git" / "refs" / "heads"
            git_heads.mkdir(parents=True, exist_ok=True)
            (git_heads / "main").write_text("old1111\n", encoding="utf-8")

            with patch("gemini_app.fleet.satellite.is_ish_platform", return_value=True):
                with patch("gemini_app.fleet.satellite._get_git_info_fast", return_value=("old1111", "main")):
                    with patch("urllib.request.urlopen") as mock_url:
                        # Create valid empty tarball response
                        import io, tarfile
                        bio = io.BytesIO()
                        with tarfile.open(fileobj=bio, mode="w:gz") as tar:
                            pass
                        bio.seek(0)
                        mock_resp = MagicMock()
                        mock_resp.read.return_value = bio.getvalue()
                        mock_resp.__enter__.return_value = mock_resp
                        mock_url.return_value = mock_resp

                        with patch("subprocess.run") as mock_sub:
                            mock_sub.return_value = MagicMock(returncode=0, stdout="VERIFIED")
                            res = execute_fleet_upgrade(repo_dir=repo_path, target_commit="abc9999123")
                            self.assertEqual(res.get("status"), "ok")
                            self.assertEqual(res.get("new_commit"), "abc9999")
                            self.assertTrue(res.get("upgraded"))
                            ref_content = (git_heads / "main").read_text(encoding="utf-8").strip()
                            self.assertEqual(ref_content, "abc9999123")

    def test_hud_non_tty_rejection(self) -> None:
        """Verifies main() rejects HUD mode if stdin is not an interactive TTY."""
        import sys
        from gemini_app.fleet.satellite import main as sat_main
        with patch.object(sys, "argv", ["satellite.py", "--hud"]):
            with patch("sys.stdin.isatty", return_value=False):
                with patch("sys.stderr.write") as mock_err:
                    ret = sat_main()
                    self.assertEqual(ret, 1)
                    mock_err.assert_called()
                    self.assertIn("requires an interactive TTY", mock_err.call_args[0][0])

    def test_mothership_get_repo_bundle(self) -> None:
        """Verifies MothershipServer creates an in-memory base64 tarball bundle."""
        server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        b64, commit = server.get_repo_bundle()
        self.assertIsNotNone(b64)
        self.assertGreater(len(b64), 100)
        self.assertNotEqual(commit, "unknown")

    def test_execute_fleet_upgrade_with_bundle(self) -> None:
        """Verifies execute_fleet_upgrade unpacks direct Mothership bundle without network access."""
        import tempfile, io, tarfile, base64
        with tempfile.TemporaryDirectory() as td:
            repo_path = Path(td)
            git_heads = repo_path / ".git" / "refs" / "heads"
            git_heads.mkdir(parents=True, exist_ok=True)
            (git_heads / "main").write_text("old1111\n", encoding="utf-8")

            # Create mock bundle containing a dummy file
            bio = io.BytesIO()
            with tarfile.open(fileobj=bio, mode="w:gz") as tar:
                data = b"print('UPDATED_CODE')\n"
                ti = tarfile.TarInfo("test_file.py")
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
            bio.seek(0)
            mock_bundle_b64 = base64.b64encode(bio.getvalue()).decode("ascii")

            with patch("gemini_app.fleet.satellite.is_ish_platform", return_value=True):
                with patch("gemini_app.fleet.satellite._get_git_info_fast", return_value=("old1111", "main")):
                    with patch("subprocess.run") as mock_sub:
                        mock_sub.return_value = MagicMock(returncode=0, stdout="VERIFIED")
                        res = execute_fleet_upgrade(
                            repo_dir=repo_path,
                            target_commit="bundle789",
                            bundle_b64=mock_bundle_b64,
                        )
                        self.assertEqual(res.get("status"), "ok")
                        self.assertEqual(res.get("new_commit"), "bundle7")
                        self.assertTrue(res.get("upgraded"))
                        self.assertTrue((repo_path / "test_file.py").exists())
                        ref_content = (git_heads / "main").read_text(encoding="utf-8").strip()
                        self.assertEqual(ref_content, "bundle789")

    def test_mothership_upgrade_node_passes_bundle(self) -> None:
        """Verifies upgrade_node passes target_commit and bundle_b64 in params."""
        server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        with patch.object(server, "get_repo_bundle", return_value=("dummy_b64_content", "commit123")):
            with patch.object(server, "send_command") as mock_send:
                mock_send.return_value = {"status": "ok"}
                res = server.upgrade_node("test-node-1")
                self.assertEqual(res.get("status"), "ok")
                mock_send.assert_called_once()
                call_kwargs = mock_send.call_args.kwargs
                self.assertEqual(call_kwargs.get("node_id"), "test-node-1")
                self.assertEqual(call_kwargs.get("action"), "fleet_upgrade")
                params = call_kwargs.get("params", {})
                self.assertEqual(params.get("target_commit"), "commit123")
                self.assertEqual(params.get("bundle_b64"), "dummy_b64_content")

    def test_hud_renders_connected_nodes_with_recent_on_top(self) -> None:
        """Verifies connected nodes section is rendered at the bottom with most recent on top."""
        hud = SatelliteHUD(node_id="ipad-user", mothership_addr="192.168.1.90:7331")
        hud.update_telemetry({
            "host": "mothership",
            "platform": "Linux",
            "vitals": {"cpu_pct": 20.0, "mem_used_mb": 1000, "mem_total_mb": 4000},
            "git": {"branch": "main", "commit": "abc1234"},
            "cognitive": {"state_desc": "Coding", "task": "Fleet HUD", "thought": "Testing nodes"},
            "satellites": [
                {
                    "node_id": "older-satellite",
                    "address": "192.168.1.55:40000",
                    "last_active_seconds_ago": 45.0,
                    "last_seen_seconds_ago": 45.0,
                },
                {
                    "node_id": "recent-satellite",
                    "address": "192.168.1.44:50000",
                    "last_active_seconds_ago": 2.0,
                    "last_seen_seconds_ago": 2.0,
                },
                {
                    "node_id": "ipad-user",
                    "address": "192.168.1.88:60000",
                    "last_active_seconds_ago": 1.0,
                    "last_seen_seconds_ago": 1.0,
                },
            ],
        })
        rendered = hud.render()
        self.assertIn("FLEET NODES", rendered)
        self.assertIn("ipad-user", rendered)
        self.assertIn("(this node)", rendered)
        self.assertIn("recent-satellite", rendered)
        # Verify ipad-user (1s) appears before older-satellite (45s)
        idx_ipad = rendered.index("ipad-user")
        idx_recent = rendered.index("recent-satellite")
        idx_older = rendered.index("older-satellite") if "older-satellite" in rendered else 999999
        self.assertLess(idx_ipad, idx_older)
        self.assertLess(idx_recent, idx_older)

    def test_hud_redraw_hint_present_on_narrow_screens(self) -> None:
        """Verifies 'r' (redraw) hint is always present even when terminal width < 55."""
        hud = SatelliteHUD(node_id="termux-phone", mothership_addr="10.0.0.5:7331")
        hud.update_telemetry({
            "host": "mothership",
            "platform": "Linux",
            "vitals": {"cpu_pct": 10.0, "mem_used_mb": 500, "mem_total_mb": 2000},
            "git": {"branch": "main", "commit": "1234567"},
            "cognitive": {"state_desc": "Idle", "task": "Standby"},
        })
        with patch("shutil.get_terminal_size", return_value=(45, 24)):
            rendered = hud.render()
            self.assertIn("r:redr", rendered)
            self.assertIn("q:quit", rendered)

    def test_hud_display_width_and_emoji_clipping(self) -> None:
        """Verifies str_display_width accurately calculates emoji widths and format_box_line doesn't overflow."""
        from gemini_app.fleet.hud import str_display_width, clip_ansi
        self.assertEqual(str_display_width("🧠"), 2)
        self.assertEqual(str_display_width("⚡"), 2)
        self.assertEqual(str_display_width("•"), 1)
        self.assertEqual(str_display_width("plain text"), 10)

        s = "\033[32m🧠 AI STREAM\033[0m"
        clipped = clip_ansi(s, 10)
        self.assertLessEqual(str_display_width(clipped), 10)

        hud = SatelliteHUD(node_id="test", mothership_addr="1.2.3.4:7331")
        line = hud._format_box_line("|", "🧠 Brain Emoji Text", 40)
        from gemini_app.fleet.hud import strip_ansi
        # Visible length minus trailing escape codes and newline
        clean_line = strip_ansi(line).rstrip("\n")
        self.assertEqual(str_display_width(clean_line), 40)

    def test_node_error_formatting_and_relationals(self) -> None:
        """Verifies format_node_error formats compact codes and relationals for user reporting."""
        from gemini_app.fleet.satellite import format_node_error
        e104 = ConnectionResetError(104, "Connection reset by peer")
        f104 = format_node_error(e104, context="lan/recv")
        self.assertEqual(f104["code"], "ERR#104")
        self.assertIn("ConnReset", f104["relationals"])
        self.assertIn("ERR#104 (ConnReset:lan/recv)", f104["short_str"])

        e111 = ConnectionRefusedError(111, "Connection refused")
        f111 = format_node_error(e111, context="wan/conn")
        self.assertEqual(f111["code"], "ERR#111")
        self.assertIn("Refused:wan/conn", f111["relationals"])

        e_auth = PermissionError("Invalid signature from node")
        f_auth = format_node_error(e_auth, context="auth")
        self.assertEqual(f_auth["code"], "ERR#AUTH")

    def test_satellite_error_reporting_to_mothership(self) -> None:
        """Verifies satellite reports errors back to Mothership and records in last_error."""
        server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        self.assertTrue(server.start())
        port = server.port

        sat = SatelliteNode("127.0.0.1", port, node_id="test-err-reporter")
        try:
            self.assertTrue(sat.start())
            time.sleep(0.3)
            # Report an error
            err_dict = sat.report_error(ConnectionResetError(104, "Socket dropped"), context="recv")
            self.assertIn("ERR#104", err_dict["short_str"])

            time.sleep(0.4)
            nodes = server.list_nodes()
            sat_node = next((n for n in nodes if n["node_id"] == "test-err-reporter"), None)
            self.assertIsNotNone(sat_node)
            self.assertEqual(sat_node["last_error"].get("code"), "ERR#104")
            self.assertIn("ConnReset:recv", sat_node["last_error"].get("relationals", ""))
        finally:
            sat.stop()
            server.stop()


if __name__ == "__main__":
    unittest.main()
