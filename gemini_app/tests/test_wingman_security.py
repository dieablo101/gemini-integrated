"""Unit tests for Wingman Zero-Trust Authentication, Pairing Modals, and Homebase Passkeys."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from gemini_app.fleet.wingman_auth import (
    generate_session_token,
    is_device_trusted,
    list_trusted_devices,
    load_trusted_devices,
    revoke_trusted_device,
    save_trusted_devices,
    trust_device,
    verify_homebase_passkey,
)
from gemini_app.fleet.protocol import FleetMessage
from gemini_app.fleet.mothership import MothershipServer
from gemini_app.webapplet.applets.wingman import WingmanApplet
from gemini_app.webapplet.engine import WebAppletEngine
from gemini_app.ui.modals.wingman_auth import WingmanAuthModal


class TestWingmanSecurity(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fake_vault = Path(self.tmp_dir.name)
        self.trusted_file = self.fake_vault / "trusted_wingman_devices.json"

        self.vault_patch = patch("gemini_app.fleet.wingman_auth.VAULT_DIR", self.fake_vault)
        self.file_patch = patch("gemini_app.fleet.wingman_auth.TRUSTED_WINGMAN_FILE", self.trusted_file)
        self.vault_patch.start()
        self.file_patch.start()

    def tearDown(self) -> None:
        self.file_patch.stop()
        self.vault_patch.stop()
        self.tmp_dir.cleanup()

    def test_loopback_is_always_trusted(self) -> None:
        self.assertTrue(is_device_trusted("127.0.0.1"))
        self.assertTrue(is_device_trusted("::1"))
        self.assertTrue(is_device_trusted("localhost"))
        self.assertTrue(is_device_trusted("local"))
        self.assertFalse(is_device_trusted("192.168.1.105"))

    def test_trust_and_revoke_device(self) -> None:
        client_ip = "192.168.1.42"
        node_id = "ipad-studio"
        self.assertFalse(is_device_trusted(client_ip))

        entry = trust_device(
            identifier=client_ip,
            node_id=node_id,
            client_ip=client_ip,
            label="iPad Studio Studio Pro",
        )
        self.assertEqual(entry["node_id"], node_id)
        self.assertTrue(is_device_trusted(client_ip))

        devs = list_trusted_devices()
        self.assertTrue(any(d["client_ip"] == client_ip for d in devs))

        # Revoke
        revoked = revoke_trusted_device(client_ip)
        self.assertTrue(revoked)
        self.assertFalse(is_device_trusted(client_ip))

    def test_homebase_passkey_verification(self) -> None:
        # Without vault configured
        with patch("gemini_app.vault.is_vault_configured", return_value=False):
            self.assertFalse(verify_homebase_passkey("secret-pass"))

        # With vault configured
        with patch("gemini_app.vault.is_vault_configured", return_value=True), \
             patch("gemini_app.vault.verify_vault_passkey", side_effect=lambda p: p == "mothership-key-123"):
            self.assertTrue(verify_homebase_passkey("mothership-key-123"))
            self.assertFalse(verify_homebase_passkey("wrong-key"))

    def test_generate_session_token(self) -> None:
        tok1 = generate_session_token("node1", "192.168.1.50")
        tok2 = generate_session_token("node1", "192.168.1.50")
        self.assertEqual(len(tok1), 64)
        self.assertNotEqual(tok1, tok2)

    def test_wingman_applet_zero_trust_flow(self) -> None:
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        self.assertTrue(applet.start())
        try:
            auth_requests = []
            applet.on_auth_request(lambda req: auth_requests.append(req))

            # Simulate unauthenticated browser GET request from remote IP
            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.77", 49123)
            mock_handler.headers = {"User-Agent": "Mozilla/5.0 Safari/605.1.15"}

            html = applet._handle_index(mock_handler, {})
            self.assertIn("Awaiting Mothership Console Authorization...", html)

            # Trigger session check from remote IP
            sess_data = applet._handle_session_check(mock_handler, {})
            self.assertEqual(sess_data["status"], "pending")
            self.assertEqual(len(auth_requests), 1)

            req = auth_requests[0]
            req_id = req["auth_req_id"]
            self.assertEqual(req["client_ip"], "192.168.1.77")

            # Check status poll while pending
            status_pending = applet._handle_auth_status(mock_handler, {"req_id": [req_id]})
            self.assertEqual(status_pending["status"], "pending")

            # Operator on Mothership accepts the connection
            res = applet.resolve_auth_request(req_id, decision="accept")
            self.assertEqual(res["status"], "approved")
            self.assertTrue("token" in res)
            token = res["token"]

            # Check status poll after approval
            status_approved = applet._handle_auth_status(mock_handler, {"req_id": [req_id]})
            self.assertEqual(status_approved["status"], "approved")
            self.assertEqual(status_approved["token"], token)

            # Subsequent session check with approved token
            mock_handler.headers["Authorization"] = f"Bearer {token}"
            sess_resume = applet._handle_session_check(mock_handler, {"token": [token]})
            self.assertTrue(sess_resume["authenticated"])
            self.assertEqual(sess_resume["status"], "authorized")

            # Test passkey verification route
            with patch("gemini_app.vault.is_vault_configured", return_value=True), \
                 patch("gemini_app.vault.verify_vault_passkey", side_effect=lambda p: p == "secret123"):
                resp_valid = applet._handle_verify_passkey(mock_handler, {}, {"passkey": "secret123", "prompt_id": req_id})
                self.assertTrue(resp_valid["valid"])
                self.assertEqual(resp_valid["status"], "ok")

                resp_invalid = applet._handle_verify_passkey(mock_handler, {}, {"passkey": "wrong"})
                self.assertFalse(resp_invalid["valid"])
                self.assertEqual(resp_invalid["status"], "invalid")
        finally:
            applet.stop()

    def test_wingman_applet_deny_flow(self) -> None:
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        self.assertTrue(applet.start())
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.88", 50123)
            mock_handler.headers = {}

            applet._handle_session_check(mock_handler, {})
            req_id = list(applet.security.sessions.keys())[0]

            res = applet.resolve_auth_request(req_id, decision="deny")
            self.assertEqual(res["status"], "denied")

            status = applet._handle_auth_status(mock_handler, {"req_id": [req_id]})
            self.assertEqual(status["status"], "denied")
        finally:
            applet.stop()

    def test_mothership_server_wingman_auth_dispatch(self) -> None:
        server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        received_requests = []
        server.on_wingman_auth(lambda r: received_requests.append(r))

        # Simulate incoming FleetMessage TYPE_EVENT: wingman_auth_request
        mock_satellite = MagicMock()
        mock_satellite.send.return_value = True

        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="ipad-pro",
            payload={
                "event": "wingman_auth_request",
                "auth_req_id": "wauth-test-99",
                "client_ip": "192.168.1.120",
                "user_agent": "Safari iOS",
                "timestamp": time.time(),
            },
        )

        with server.lock:
            server.nodes["ipad-pro"] = mock_satellite

        # Directly invoke client message handling logic
        with patch.object(server, "send_command", return_value={"status": "approved"}):
            # Dispatch command test
            decision_res = server.authorize_wingman(
                node_id="ipad-pro",
                auth_req_id="wauth-test-99",
                decision="accept",
                trust=True,
            )
            self.assertEqual(decision_res["status"], "approved")

    def test_wingman_auth_modal(self) -> None:
        auth_data = {
            "node_id": "ipad-studio",
            "client_ip": "192.168.1.55",
            "auth_req_id": "wauth-xyz123",
            "user_agent": "Mozilla/5.0 (iPad; CPU OS 17_4)",
            "timestamp": time.time(),
        }
        modal = WingmanAuthModal(auth_data=auth_data)
        self.assertEqual(modal.node_id, "ipad-studio")
        self.assertEqual(modal.client_ip, "192.168.1.55")
        self.assertEqual(modal.auth_req_id, "wauth-xyz123")

        # Test action callbacks
        dismiss_results = []
        modal.dismiss = lambda res: dismiss_results.append(res)

        modal.action_accept()
        self.assertEqual(dismiss_results, ["accept"])

        modal.action_trust()
        self.assertEqual(dismiss_results, ["accept", "trust"])

        modal.action_deny()
        self.assertEqual(dismiss_results, ["accept", "trust", "deny"])

    def test_wingman_ui_contains_dropdown_and_chat_view(self) -> None:
        """Verifies UI includes the Work vs Chat dropdown and bilateral chat stream containers."""
        applet = WingmanApplet(port=0, node_id="test-node")
        self.assertTrue(applet.start())
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("127.0.0.1", 52100)
            mock_handler.headers = {}
            html = applet._handle_index(mock_handler, {})

            # Dropdown menu & selector
            self.assertIn("modeDropdownWrapper", html)
            self.assertIn("modeBtn", html)
            self.assertIn("Work", html)
            self.assertIn("Chat", html)

            # Dual views
            self.assertIn("workView", html)
            self.assertIn("chatView", html)
            self.assertIn("chatFeed", html)
            self.assertIn("chatInput", html)

            # Security gate & passkey unlock elements
            self.assertIn("securityGate", html)
            self.assertIn("passkeyInput", html)
            self.assertIn("trustDeviceCheck", html)
        finally:
            applet.stop()

    def test_wingman_chat_stream_and_history(self) -> None:
        """Verifies chat message reception, callbacks, and history storage."""
        applet = WingmanApplet(port=0, node_id="test-node")
        self.assertTrue(applet.start())
        try:
            received_chat = []
            applet.on_chat_message(lambda s, t, b: received_chat.append((s, t)))

            mock_handler = MagicMock()
            mock_handler.client_address = ("127.0.0.1", 52200)

            # Post a chat message
            res = applet._handle_chat(mock_handler, {}, {
                "sender": "operator",
                "text": "Hello Gemini from remote satellite!",
            })
            self.assertEqual(res["status"], "ok")
            self.assertIn("message_id", res)
            self.assertEqual(len(received_chat), 1)
            self.assertEqual(received_chat[0], ("operator", "Hello Gemini from remote satellite!"))

            # Check chat history
            hist_res = applet._handle_chat_history(mock_handler, {})
            self.assertEqual(hist_res["status"], "ok")
            self.assertEqual(len(hist_res["history"]), 1)
            self.assertEqual(hist_res["history"][0]["text"], "Hello Gemini from remote satellite!")

            # Test push_chat_message from core
            core_msg_id = applet.push_chat_message("gemini", "Standing by to execute workflow.", is_user=False)
            self.assertTrue(core_msg_id.startswith("msg-"))

            hist_res2 = applet._handle_chat_history(mock_handler, {})
            self.assertEqual(len(hist_res2["history"]), 2)
        finally:
            applet.stop()

    def test_wingman_pbkdf2_passkey_direct_auth(self) -> None:
        """Verifies direct passkey entry verifies PBKDF2 hash and unlocks session."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        self.assertTrue(applet.start())
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.180", 52300)
            mock_handler.headers = {"User-Agent": "Mobile Safari"}

            # First hit creates pending session
            sess_res = applet._handle_session_check(mock_handler, {})
            self.assertFalse(sess_res["authenticated"])
            sess_id = sess_res["session_id"]

            with patch("gemini_app.vault.is_vault_configured", return_value=True), \
                 patch("gemini_app.vault.verify_vault_passkey", side_effect=lambda p: p == "correct-passkey"):
                # Invalid passkey
                bad_auth = applet._handle_passkey_auth(mock_handler, {}, {
                    "session_id": sess_id,
                    "passkey": "wrong-passkey",
                })
                self.assertEqual(bad_auth["status"], "error")

                # Correct passkey with trust_device
                good_auth = applet._handle_passkey_auth(mock_handler, {}, {
                    "session_id": sess_id,
                    "passkey": "correct-passkey",
                    "trust_device": True,
                })
                self.assertEqual(good_auth["status"], "ok")
                self.assertTrue("token" in good_auth)

                # Session is now authenticated
                token = good_auth["token"]
                mock_handler.headers["X-Wingman-Token"] = token
                check_after = applet._handle_session_check(mock_handler, {})
                self.assertTrue(check_after["authenticated"])
                self.assertEqual(check_after["token"], token)
        finally:
            applet.stop()


if __name__ == "__main__":
    unittest.main()
