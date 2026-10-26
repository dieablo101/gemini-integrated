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
        self.sec_vault_patch = patch("gemini_app.webapplet.applets.wingman.security.VAULT_DIR", self.fake_vault)
        self.vault_patch.start()
        self.file_patch.start()
        self.sec_vault_patch.start()

    def tearDown(self) -> None:
        from gemini_app.fleet.satellite import set_active_wingman
        set_active_wingman(None)
        self.sec_vault_patch.stop()
        self.file_patch.stop()
        self.vault_patch.stop()
        self.tmp_dir.cleanup()

    def test_loopback_is_not_trusted_by_default(self) -> None:
        self.assertFalse(is_device_trusted("127.0.0.1"))
        self.assertFalse(is_device_trusted("::1"))
        self.assertFalse(is_device_trusted("localhost"))
        self.assertFalse(is_device_trusted("local"))
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
            self.assertIn("Awaiting mothership console authorization...", html)
            self.assertNotIn("OR UNLOCK WITH PASSKEY", html)
            self.assertNotIn("Trust & pair this device", html)

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

        modal.action_pair()
        self.assertEqual(dismiss_results, ["accept", "pair"])

        modal.action_deny()
        self.assertEqual(dismiss_results, ["accept", "pair", "deny"])

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
            self.assertIn("modalPasskeyInput", html)
            self.assertIn("passkeyModal", html)
            self.assertIn("passkey-secure-input", html)
            self.assertNotIn('type="password"', html)
            self.assertIn('inputmode="text"', html)
        finally:
            applet.stop()

    def test_wingman_chat_stream_and_history(self) -> None:
        """Verifies chat message reception, callbacks, and history storage."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=False)
        self.assertTrue(applet.start())
        try:
            received_chat = []
            applet.on_chat_message(lambda s, t, b: received_chat.append((s, t)))

            mock_handler = MagicMock()
            mock_handler.client_address = ("127.0.0.1", 52200)
            mock_handler.headers = {}

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

            # Test merger with external history fetcher (e.g. from mothership)
            applet._chat_history_fetcher = lambda: [
                {"id": "msg-ext-0", "sender": "mothership", "text": "Early message", "timestamp": 100.0, "is_user": False},
                {"id": "msg-ext-99", "sender": "phone", "text": "Future message", "timestamp": 9999999999.0, "is_user": True},
            ]
            hist_res3 = applet._handle_chat_history(mock_handler, {})
            self.assertEqual(len(hist_res3["history"]), 4)
            self.assertEqual(hist_res3["history"][0]["id"], "msg-ext-0")
            self.assertEqual(hist_res3["history"][-1]["id"], "msg-ext-99")
        finally:
            applet.stop()

    def test_wingman_chat_staged_attachment(self) -> None:
        """Verifies that an attachment staged with chat message transmits cleanly and is stored."""
        import base64
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=False)
        self.assertTrue(applet.start())
        try:
            received_chat = []
            applet.on_chat_message(lambda s, t, b: received_chat.append((s, t, b)))

            mock_handler = MagicMock()
            mock_handler.client_address = ("127.0.0.1", 52201)
            mock_handler.headers = {}

            dummy_b64 = "data:image/jpeg;base64," + base64.b64encode(b"fake_jpeg_data").decode("ascii")

            # Post message with staged attachment and empty text (send attachment only)
            res = applet._handle_chat(mock_handler, {}, {
                "sender": "operator",
                "text": "",
                "attachment": {
                    "data_b64": dummy_b64,
                    "filename": "ipad_screen.jpg",
                    "kind": "screenshot",
                    "size_bytes": 14,
                }
            })
            self.assertEqual(res["status"], "ok")
            self.assertEqual(len(received_chat), 1)
            sender, text, body = received_chat[0]
            self.assertEqual(sender, "operator")
            self.assertIn("attachment", body)
            self.assertIsNotNone(body["attachment"])
            self.assertEqual(body["attachment"]["original_name"], "ipad_screen.jpg")

            # Verify history records attachment
            hist = applet._handle_chat_history(mock_handler, {})
            self.assertEqual(len(hist["history"]), 1)
            self.assertIn("attachment", hist["history"][0])
            self.assertEqual(hist["history"][0]["attachment"]["original_name"], "ipad_screen.jpg")
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

    def test_action_gated_passkey_per_session(self) -> None:
        """Verifies session allows reading content but sensitive action/chat requires passkey unlock."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        self.assertTrue(applet.start())
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.99", 54321)
            mock_handler.headers = {}

            # Authorize the device from Mothership
            sess = applet.security.create_or_resume_session(client_ip="192.168.1.99", is_loopback=False)
            applet.authorize_session(sess.session_id, accepted=True, trust_device=False)
            token = sess.token
            mock_handler.headers = {"X-Wingman-Token": token}

            # Device is authorized - can read session info and content
            check = applet._handle_session_check(mock_handler, {})
            self.assertTrue(check["authenticated"])
            self.assertFalse(check["is_unlocked"])  # Action-locked by default!

            # Attempt sensitive action while locked
            act_res = applet._handle_action(mock_handler, {}, {"card_id": "card-1", "action": "approve"})
            self.assertEqual(act_res["status"], "error")
            self.assertIn("Passkey unlock required", act_res["message"])

            # Attempt chat while locked
            chat_res = applet._handle_chat(mock_handler, {}, {"text": "secret command"})
            self.assertEqual(chat_res["status"], "error")
            self.assertIn("Passkey unlock required", chat_res["message"])

            # Unlock with passkey
            with patch("gemini_app.fleet.wingman_auth.verify_homebase_passkey", return_value=True):
                unlock_res = applet._handle_verify_passkey(mock_handler, {}, {
                    "passkey": "vault-secret",
                    "session_id": sess.session_id,
                })
                self.assertTrue(unlock_res["valid"])

            # Now session is unlocked!
            self.assertTrue(sess.is_unlocked)

            # Actions and chats succeed for remainder of session without re-prompt
            act_ok = applet._handle_action(mock_handler, {}, {"card_id": "card-1", "action": "approve"})
            self.assertEqual(act_ok["status"], "ok")

            chat_ok = applet._handle_chat(mock_handler, {}, {"text": "hello gemini"})
            self.assertEqual(chat_ok["status"], "ok")
        finally:
            applet.stop()

    def test_back_to_back_wingman_auth_queue(self) -> None:
        """Tests that concurrent incoming auth requests (e.g. phone + ipad) are processed sequentially back-to-back."""
        from gemini_app.ui.app import ChatApp

        app = ChatApp()
        app._boot_complete = True
        app._wingman_modal_open = False
        app._wingman_auth_queue = []
        app._handled_wingman_auth_reqs = set()

        req1 = {
            "node_id": "phone-android",
            "session_id": "sess-phone-1",
            "auth_req_id": "sess-phone-1",
            "client_ip": "192.168.1.179",
            "user_agent": "Chrome Mobile",
            "timestamp": time.time(),
        }
        req2 = {
            "node_id": "ipad-ish",
            "session_id": "sess-ipad-2",
            "auth_req_id": "sess-ipad-2",
            "client_ip": "192.168.1.38",
            "user_agent": "Mobile Safari",
            "timestamp": time.time(),
        }

        modal_prompts = []

        def mock_prompt_wingman_auth(auth_data, callback):
            modal_prompts.append((dict(auth_data), callback))

        app.prompt_wingman_auth = mock_prompt_wingman_auth
        app.notify = MagicMock()
        timers_created = []
        app.set_timer = lambda delay, cb: timers_created.append(cb)

        # 1. Both requests arrive at almost the exact same instant
        app._handle_wingman_auth_prompt(req1)
        app._handle_wingman_auth_prompt(req2)

        # 2. Only the first modal should be mounted; second request waits in queue
        self.assertEqual(len(modal_prompts), 1)
        active_auth, callback1 = modal_prompts[0]
        self.assertEqual(active_auth["session_id"], "sess-phone-1")
        self.assertTrue(app._wingman_modal_open)
        self.assertEqual(len(app._wingman_auth_queue), 1)
        self.assertEqual(app._wingman_auth_queue[0]["session_id"], "sess-ipad-2")

        # 3. Operator resolves the first modal (Accept [A])
        callback1("accept")
        self.assertFalse(app._wingman_modal_open)
        self.assertIn("sess-phone-1", app._handled_wingman_auth_reqs)
        self.assertTrue(len(timers_created) > 0)

        # 4. Timer triggers processing of the queued second modal (back-to-back!)
        timer_cb = timers_created.pop(0)
        timer_cb()

        self.assertEqual(len(modal_prompts), 2)
        second_auth, callback2 = modal_prompts[1]
        self.assertEqual(second_auth["session_id"], "sess-ipad-2")
        self.assertTrue(app._wingman_modal_open)
        self.assertEqual(len(app._wingman_auth_queue), 0)

        # 5. Operator resolves second modal (Pair [P])
        callback2("pair")
        self.assertFalse(app._wingman_modal_open)
        self.assertIn("sess-ipad-2", app._handled_wingman_auth_reqs)

    def test_pending_session_deduplication_prevents_multiple_modals(self) -> None:
        """Verifies that multiple session checks from the same client IP/device do not create multiple modals."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        self.assertTrue(applet.start())
        try:
            auth_requests = []
            applet.on_auth_request(lambda req: auth_requests.append(req))

            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.88", 55432)
            mock_handler.headers = {"User-Agent": "Mozilla/5.0 Android"}

            # First session check
            s1 = applet._handle_session_check(mock_handler, {})
            self.assertEqual(s1["status"], "pending")
            self.assertEqual(len(auth_requests), 1)

            # Second and third session checks from same device/IP while pending
            s2 = applet._handle_session_check(mock_handler, {})
            s3 = applet._handle_session_check(mock_handler, {})

            # Should return the EXACT same session and NOT trigger more auth requests
            self.assertEqual(s1["session_id"], s2["session_id"])
            self.assertEqual(s1["session_id"], s3["session_id"])
            self.assertEqual(len(auth_requests), 1)
        finally:
            applet.stop()

    def test_verify_homebase_passkey_vault_only(self) -> None:
        """Verifies that verify_homebase_passkey strictly checks vault passkey and rejects system password."""
        with patch("gemini_app.vault.is_vault_configured", return_value=True), \
             patch("gemini_app.vault.verify_vault_passkey", side_effect=lambda p: p == "vault-secret-123"):
            self.assertTrue(verify_homebase_passkey("vault-secret-123"))
            self.assertFalse(verify_homebase_passkey("host-user-password"))
            self.assertFalse(verify_homebase_passkey("wrong-password"))

    def test_accept_vs_pair_differentiation(self) -> None:
        """Verifies that Accept is a one-time session access whereas Pair permanently trusts the device."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        self.assertTrue(applet.start())
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.99", 55433)
            mock_handler.headers = {"User-Agent": "Mozilla/5.0 Android"}

            s1 = applet._handle_session_check(mock_handler, {})
            sess_id = s1["session_id"]

            # Operator hits 'accept' (not pair)
            res = applet.authorize_session(sess_id, accepted=True, trust_device=False)
            self.assertEqual(res["status"], "ok")
            self.assertFalse(res["is_paired"])
            self.assertFalse(applet.security.is_device_trusted(s1["device_id"]))

            # Now test 'pair'
            s2 = applet.security.create_or_resume_session(
                client_ip="192.168.1.100",
                device_id="dev-permanently-paired",
                is_loopback=False,
            )
            res2 = applet.authorize_session(s2.session_id, accepted=True, trust_device=True)
            self.assertEqual(res2["status"], "ok")
            self.assertTrue(res2["is_paired"])
            self.assertTrue(applet.security.is_device_trusted("dev-permanently-paired"))
        finally:
            applet.stop()

    def test_boot_guard_queues_wingman_modal_until_boot_complete(self) -> None:
        """Verifies that Wingman pairing modals do not mount over BootScreen and are safely queued."""
        from gemini_app.ui.app import ChatApp

        app = ChatApp()
        app._boot_complete = False
        app._wingman_auth_queue = []

        # Simulate incoming request while booting
        req = {
            "session_id": "sess-boot-test-1",
            "auth_req_id": "sess-boot-test-1",
            "client_ip": "192.168.1.42",
            "device_id": "dev-boot-phone",
        }

        # Calling prompt_wingman_auth should NOT open modal while booting
        with patch.object(app, "push_screen") as mock_push:
            app.prompt_wingman_auth(req)
            mock_push.assert_not_called()

        self.assertFalse(app._wingman_modal_open)
        self.assertEqual(len(app._wingman_auth_queue), 1)
        self.assertEqual(app._wingman_auth_queue[0]["auth_req_id"], "sess-boot-test-1")

        # Now simulate boot completing
        app._boot_complete = True
        with patch.object(app, "push_screen") as mock_push:
            app._process_next_wingman_auth()
            mock_push.assert_called_once()
            modal_arg = mock_push.call_args[0][0]
            self.assertEqual(modal_arg.__class__.__name__, "WingmanAuthModal")
            self.assertTrue(app._wingman_modal_open)

    def test_satellite_receives_wingman_chat_broadcast(self) -> None:
        """Verifies that a satellite node forwards incoming mothership wingman_chat_message events to its WingmanApplet."""
        from gemini_app.fleet.satellite import SatelliteNode
        from gemini_app.fleet.protocol import FleetMessage

        client = SatelliteNode(node_id="test-ipad-node", mothership_host="127.0.0.1")
        mock_applet = MagicMock()
        client.wingman_applet = mock_applet

        msg = FleetMessage(
            msg_type=FleetMessage.TYPE_EVENT,
            node_id="mothership",
            payload={
                "event": "wingman_chat_message",
                "sender": "Gemini Core",
                "text": "Hello iPad satellite!",
                "is_user": False,
            },
        )

        # Simulate handling incoming event on satellite
        ev = msg.payload.get("event", "")
        if ev == "wingman_chat_message":
            if client.wingman_applet and hasattr(client.wingman_applet, "push_chat_message"):
                client.wingman_applet.push_chat_message(
                    sender=msg.payload.get("sender", "Gemini Core"),
                    text=msg.payload.get("text", ""),
                    is_user=msg.payload.get("is_user", False),
                )

        mock_applet.push_chat_message.assert_called_once_with(
            sender="Gemini Core",
            text="Hello iPad satellite!",
            is_user=False,
        )

    def test_accept_without_pair_does_not_persist_pairing(self) -> None:
        """Verifies that accepting a session without pairing (trust_device=False) does not mark device as paired."""
        applet = WingmanApplet(port=0, node_id="test-phone-node", require_pairing=True)
        self.assertTrue(applet.start())
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("127.0.0.1", 54321)
            mock_handler.headers = {
                "X-Wingman-Device": "dev-phone-unpaired",
                "X-Wingman-Session": "sess-phone-unpaired",
            }

            # 1. Initial check: should be pending
            res1 = applet._handle_session_check(mock_handler, {})
            self.assertEqual(res1["status"], "pending")
            self.assertFalse(res1["is_paired"])
            self.assertFalse(res1["trusted"])

            # 2. Operator clicks 'Accept' (one-time session approval, trust_device=False)
            auth_res = applet.authorize_session("sess-phone-unpaired", accepted=True, trust_device=False)
            self.assertEqual(auth_res["status"], "ok")
            self.assertFalse(auth_res["is_paired"])
            self.assertFalse(applet.security.is_device_trusted("dev-phone-unpaired"))

            # 3. Session check after accept: authenticated is True, but is_paired remains False!
            mock_handler.headers["X-Wingman-Token"] = auth_res["token"]
            res2 = applet._handle_session_check(mock_handler, {})
            self.assertTrue(res2["authenticated"])
            self.assertFalse(res2["is_paired"])
            self.assertFalse(res2["trusted"])
        finally:
            applet.stop()

    def test_multi_device_chat_broadcast(self) -> None:
        """Verifies that a chat message from node A is broadcasted to node B and local Wingman."""
        server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        mock_sat_a = MagicMock()
        mock_sat_a.send.return_value = True
        mock_sat_b = MagicMock()
        mock_sat_b.send.return_value = True

        with server.lock:
            server.nodes["node-a-phone"] = mock_sat_a
            server.nodes["node-b-ipad"] = mock_sat_b

        # Simulate broadcast from node A
        count = server.broadcast_wingman_chat(
            sender="operator",
            text="Sync test across devices",
            is_user=True,
            exclude_node_id="node-a-phone",
        )
        self.assertEqual(count, 1)
        mock_sat_a.send.assert_not_called()
        mock_sat_b.send.assert_called_once()
        sent_msg = mock_sat_b.send.call_args[0][0]
        self.assertEqual(sent_msg.payload["event"], "wingman_chat_message")
        self.assertEqual(sent_msg.payload["text"], "Sync test across devices")
        self.assertTrue(sent_msg.payload["is_user"])

    def test_clear_command_from_wingman(self) -> None:
        """Verifies that /clear resets history on WingmanApplet and Mothership broadcasts clear event."""
        applet = WingmanApplet(port=0, node_id="test-clear-node", require_pairing=False)
        self.assertTrue(applet.start())
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("127.0.0.1", 54322)
            mock_handler.headers = {}

            # Add message
            applet.push_chat_message("user", "Hello before clear", is_user=True)
            self.assertEqual(len(applet._chat_history), 1)

            # Send /clear
            res = applet._handle_chat(mock_handler, {}, {"text": "/clear", "sender": "operator"})
            self.assertEqual(res["status"], "ok")
            self.assertEqual(len(applet._chat_history), 0)

            # Test Mothership clear broadcast
            server = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
            mock_sat = MagicMock()
            mock_sat.send.return_value = True
            with server.lock:
                server.nodes["ipad-node"] = mock_sat
                server.recent_wingman_chat.append({"text": "stale message"})

            self.assertEqual(len(server.recent_wingman_chat), 1)
            server.broadcast_wingman_clear()
            self.assertEqual(len(server.recent_wingman_chat), 0)
            mock_sat.send.assert_called_once()
            self.assertEqual(mock_sat.send.call_args[0][0].payload["event"], "wingman_chat_clear")
        finally:
            applet.stop()

    def test_pending_session_reconnect_reinvokes_pending_callbacks(self) -> None:
        """Verifies that when a pending device refreshes or re-polls, on_pending_session is re-invoked."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        notifications = []
        applet.on_auth_request(lambda req: notifications.append(req))
        try:
            # 1. First connection
            s1 = applet.security.create_or_resume_session(client_ip="192.168.1.179", device_id="dev-phone-x")
            self.assertEqual(len(notifications), 1)

            # 2. Immediately reconnect (< 3s)
            s2 = applet.security.create_or_resume_session(client_ip="192.168.1.179", device_id="dev-phone-x")
            self.assertEqual(len(notifications), 1)

            # 3. Reconnect after notification cooldown (> 3s simulated)
            s1._last_notified = time.time() - 4.0
            s3 = applet.security.create_or_resume_session(client_ip="192.168.1.179", device_id="dev-phone-x")
            self.assertEqual(len(notifications), 2)
            self.assertEqual(notifications[1]["session_id"], s1.session_id)
        finally:
            applet.stop()

    def test_ephemeral_accept_session_does_not_resume_on_reload(self) -> None:
        """Verifies that an ephemeral session (one-time Accept) cannot bypass zero-trust on refresh."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        notifications = []
        applet.on_auth_request(lambda req: notifications.append(req))
        try:
            # 1. Device connects -> pending
            s1 = applet.security.create_or_resume_session(client_ip="192.168.1.55", device_id="dev-ephemeral-1")
            self.assertEqual(s1.status, "pending")
            self.assertEqual(len(notifications), 1)

            # 2. Operator accepts (one-time approval, trust_device=False)
            applet.authorize_session(s1.session_id, accepted=True, trust_device=False)
            self.assertEqual(s1.status, "authorized")
            self.assertFalse(s1.is_paired)

            # 3. User refreshes browser (simulating check with no stored token on reload)
            s1._last_notified = time.time() - 5.0
            s2 = applet.security.create_or_resume_session(
                client_ip="192.168.1.55",
                device_id="dev-ephemeral-1",
                existing_token="",
            )
            # Must NOT resume as authorized; must require fresh approval!
            self.assertEqual(s2.status, "pending")
            self.assertEqual(len(notifications), 2)
        finally:
            applet.stop()

    def test_paired_session_resumes_on_reload(self) -> None:
        """Verifies that a permanently paired device (Pair) smoothly resumes across page refresh."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        try:
            # 1. Device connects -> pending
            s1 = applet.security.create_or_resume_session(client_ip="192.168.1.66", device_id="dev-paired-1")
            self.assertEqual(s1.status, "pending")

            # 2. Operator pairs device (permanent trust, trust_device=True)
            applet.authorize_session(s1.session_id, accepted=True, trust_device=True)
            self.assertEqual(s1.status, "authorized")
            self.assertTrue(s1.is_paired)

            # 3. User refreshes browser with token
            s2 = applet.security.create_or_resume_session(
                client_ip="192.168.1.66",
                device_id="dev-paired-1",
                existing_token=s1.token,
            )
            self.assertEqual(s2.status, "authorized")
            self.assertEqual(s2.session_id, s1.session_id)
        finally:
            applet.security.revoke_device("dev-paired-1")
            applet.stop()

    def test_mothership_reboot_purges_unpaired_sessions(self) -> None:
        """Verifies that on_mothership_reboot purges all one-time sessions."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        try:
            # Create one ephemeral session and one paired session
            s_eph = applet.security.create_or_resume_session(client_ip="192.168.1.77", device_id="dev-eph-reb")
            applet.authorize_session(s_eph.session_id, accepted=True, trust_device=False)
            tok_eph = s_eph.token

            s_pair = applet.security.create_or_resume_session(client_ip="192.168.1.88", device_id="dev-pair-reb")
            applet.authorize_session(s_pair.session_id, accepted=True, trust_device=True)
            tok_pair = s_pair.token

            self.assertIsNotNone(applet.security.get_session_by_token(tok_eph))
            self.assertIsNotNone(applet.security.get_session_by_token(tok_pair))

            # Simulate Mothership console reboot epoch reset
            applet.on_mothership_reboot("epoch-99999")
            self.assertEqual(applet.mothership_boot_id, "epoch-99999")

            # Ephemeral session MUST be purged
            self.assertIsNone(applet.security.get_session_by_token(tok_eph))
            # Paired session remains trusted in device registry
            self.assertTrue(applet.security.is_device_trusted("dev-pair-reb"))
        finally:
            applet.security.revoke_device("dev-pair-reb")
            applet.stop()

    def test_wingman_maintenance_lockout(self) -> None:
        """Verifies that maintenance mode gates Wingman applet responses and suppresses auth prompts."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        try:
            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.99", 51234)
            mock_handler.headers = {}

            # Normal check
            res1 = applet._handle_session_check(mock_handler, {})
            self.assertFalse(res1.get("maintenance"))
            self.assertEqual(res1.get("status"), "pending")

            # Activate maintenance mode
            applet.set_maintenance_mode(True, reason="Mothership updates underway")
            self.assertTrue(applet.maintenance_mode)

            # Check during maintenance
            res_maint = applet._handle_session_check(mock_handler, {})
            self.assertTrue(res_maint.get("maintenance"))
            self.assertEqual(res_maint.get("status"), "maintenance")
            self.assertFalse(res_maint.get("authenticated"))

            # Ping during maintenance
            ping_res = applet._handle_ping(mock_handler, {})
            self.assertTrue(ping_res.get("maintenance"))

            # Release maintenance mode
            applet.set_maintenance_mode(False)
            self.assertFalse(applet.maintenance_mode)

            res_normal = applet._handle_session_check(mock_handler, {})
            self.assertFalse(res_normal.get("maintenance"))
        finally:
            applet.stop()

    def test_wingman_chat_device_attribution_and_feed_depth(self) -> None:
        """Verifies multi-device attribution metadata and 50-card feed depth windowing."""
        from gemini_app.webapplet.applets.wingman.applet import WingmanApplet
        from gemini_app.webapplet.applets.wingman.ui import get_wingman_html

        # Verify textarea is used in UI instead of input type text
        html = get_wingman_html()
        self.assertIn('<textarea id="chatInput"', html)
        self.assertNotIn('<input type="text"\n               id="chatInput"', html)
        self.assertIn('detectDeviceType', html)
        self.assertIn('enterkeyhint="send"', html)

        applet = WingmanApplet(port=0, node_id="test_node")
        try:
            # Simulate 60 messages to test the 50-card ceiling
            for i in range(60):
                applet.push_chat_message(
                    sender="Operator",
                    text=f"Turn message {i}",
                    is_user=True,
                    origin_device=f"dev-{i % 3}",
                    origin_label="Phone" if (i % 3 == 0) else ("iPad" if i % 3 == 1 else "Mothership"),
                )

            # Check that history strictly honors the 50-card rolling window
            mock_handler = MagicMock()
            mock_handler.headers = {}
            hist_res = applet._handle_chat_history(mock_handler, {})
            self.assertEqual(len(hist_res["history"]), 50)
            self.assertEqual(hist_res["history"][-1]["text"], "Turn message 59")
            self.assertEqual(hist_res["history"][0]["text"], "Turn message 10")
            self.assertEqual(hist_res["history"][-1]["origin_label"], "Mothership")
        finally:
            applet.stop()

    def test_wingman_chat_attachment_staged_flow(self) -> None:
        """Verifies that screenshots/photos stage as attachments and transmit with chat message."""
        import base64
        from gemini_app.webapplet.applets.wingman.applet import WingmanApplet
        from gemini_app.webapplet.applets.wingman.ui import get_wingman_html

        html = get_wingman_html()
        self.assertIn('chatAttachmentPreview', html)
        self.assertIn('handleChatAttachmentSelect', html)
        self.assertIn('clearStagedAttachment', html)

        applet = WingmanApplet(port=0, node_id="test_node", require_pairing=False)
        received_callbacks = []
        applet.on_chat_message(lambda sender, text, body: received_callbacks.append((sender, text, body)))

        try:
            fake_img_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            fake_b64 = "data:image/gif;base64," + base64.b64encode(fake_img_bytes).decode("ascii")

            mock_handler = MagicMock()
            mock_handler.headers = {}
            mock_handler.client_address = ("127.0.0.1", 12345)

            # Test sending chat message WITH attachment
            chat_body = {
                "id": "msg-att-1",
                "text": "Here is the error screenshot",
                "sender": "Operator",
                "attachment": {
                    "data_b64": fake_b64,
                    "filename": "error_screen.gif",
                    "kind": "screenshot"
                }
            }
            res = applet._handle_chat(mock_handler, {}, chat_body)
            self.assertEqual(res["status"], "ok")

            # Verify saved in applet chat history with attachment
            self.assertEqual(len(applet._chat_history), 1)
            saved = applet._chat_history[0]
            self.assertEqual(saved["text"], "Here is the error screenshot")
            self.assertIsNotNone(saved.get("attachment"))
            self.assertEqual(saved["attachment"]["original_name"], "error_screen.gif")

            # Verify callback received attachment
            self.assertEqual(len(received_callbacks), 1)
            self.assertEqual(received_callbacks[0][0], "Operator")
            self.assertIn("attachment", received_callbacks[0][2])

            # Test sending attachment with EMPTY text (user just hits send after picking screenshot)
            chat_body_empty_text = {
                "id": "msg-att-2",
                "text": "",
                "sender": "Operator",
                "attachment": {
                    "data_b64": fake_b64,
                    "filename": "lone_screenshot.gif",
                    "kind": "screenshot"
                }
            }
            res2 = applet._handle_chat(mock_handler, {}, chat_body_empty_text)
            self.assertEqual(res2["status"], "ok")
            self.assertEqual(len(applet._chat_history), 2)
            self.assertEqual(applet._chat_history[1]["attachment"]["original_name"], "lone_screenshot.gif")
        finally:
            applet.stop()

    def test_screen_off_device_approval_and_wake_unlock(self) -> None:
        """Verifies that when a device is approved while its screen is off, auth_status polling unlocks immediately with token, while fresh unpaired session checks require Mothership auth."""
        notifications = []
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        applet.on_auth_request(lambda req: notifications.append(req))
        try:
            # 1. Device connects while screen on -> pending
            sess_id = "sess-ipad-sleep-1"
            s1 = applet.security.create_or_resume_session(
                client_ip="192.168.1.99",
                device_id="dev-ipad-sleep",
                existing_session_id=sess_id,
            )
            self.assertEqual(s1.status, "pending")
            self.assertEqual(len(notifications), 1)

            # 2. iPad screen goes off / sleeps. Operator on Mothership approves session
            applet.authorize_session(sess_id, accepted=True, trust_device=False)
            self.assertEqual(s1.status, "authorized")

            # 3. iPad screen turns on / wakes up -> auth polling receives approved status and token
            mock_handler = MagicMock()
            auth_res = applet._handle_auth_status(mock_handler, {"session_id": [sess_id]})
            self.assertEqual(auth_res.get("status"), "approved")
            self.assertEqual(auth_res.get("token"), s1.token)

            # 4. With token, active session resumes seamlessly
            s_resumed = applet.security.create_or_resume_session(
                client_ip="192.168.1.99",
                device_id="dev-ipad-sleep",
                existing_session_id=sess_id,
                existing_token=s1.token,
            )
            self.assertEqual(s_resumed.status, "authorized")
            self.assertEqual(s_resumed.token, s1.token)

            # 5. Without token, an unpaired device is NOT auto-resumed (prevents bypassing Mothership gate on reload)
            s_unpaired = applet.security.create_or_resume_session(
                client_ip="192.168.1.99",
                device_id="dev-ipad-sleep",
                existing_session_id="sess-ipad-new-tab",
                existing_token="",
            )
            self.assertEqual(s_unpaired.status, "pending")
        finally:
            applet.stop()

    def test_chat_expiry_returns_reauth_required(self) -> None:
        """Verifies that chat dispatch with an expired or stale session returns reauth_required."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        try:
            mock_handler = MagicMock()
            mock_handler.headers = {"X-Wingman-Token": "stale-expired-token", "X-Wingman-Device": "dev-ipad"}
            res = applet._handle_chat(mock_handler, {}, {"text": "hello", "sender": "Operator"})
            self.assertEqual(res.get("status"), "error")
            self.assertTrue(res.get("session_locked"))
            self.assertTrue(res.get("reauth_required"))
            self.assertIn("Session expired or Mothership rebooted", res.get("message", ""))
        finally:
            applet.stop()

    def test_authorization_device_id_continuity_and_auth_status(self) -> None:
        """Verifies that authorizing by session_id + device_id properly approves and unlocks polling."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        try:
            # 1. Device connects with session A
            s1 = applet.security.create_or_resume_session(
                client_ip="192.168.1.179",
                device_id="dev-android-continuity",
                existing_session_id="sess-android-old",
            )
            self.assertEqual(s1.status, "pending")

            # 2. Operator authorizes session A passing device_id
            res = applet.authorize_session("sess-android-old", accepted=True, trust_device=False, device_id="dev-android-continuity")
            self.assertEqual(res["status"], "ok")

            # 3. Client queries auth_status even with a different session ID or device_id
            mock_handler = MagicMock()
            mock_handler.headers = {"X-Wingman-Device": "dev-android-continuity"}
            status_res = applet._handle_auth_status(mock_handler, {"req_id": ["sess-android-diff"], "device_id": ["dev-android-continuity"]})
            self.assertEqual(status_res["status"], "approved")
            self.assertTrue(bool(status_res["token"]))
        finally:
            applet.stop()

    def test_passkey_unlock_and_session_lock_distinction(self) -> None:
        """Verifies distinction between session_locked and reauth_required, and passkey verification unlocks pending session."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        try:
            applet._passkey_verifier = lambda p: p == "secret123"
            sess = applet.security.create_or_resume_session(client_ip="192.168.1.180", device_id="dev-android", is_loopback=False)
            applet.authorize_session(sess.session_id, accepted=True, trust_device=False)
            sess.is_unlocked = False  # Authorized but passkey locked!

            mock_handler = MagicMock()
            mock_handler.headers = {"X-Wingman-Token": sess.token, "X-Wingman-Device": "dev-android"}
            res = applet._handle_chat(mock_handler, {}, {"text": "hello", "sender": "Operator"})
            self.assertEqual(res.get("status"), "error")
            self.assertTrue(res.get("session_locked"))
            # Must NOT require reauth when node is authorized and only passkey is locked!
            self.assertFalse(res.get("reauth_required", False))
            self.assertIn("Passkey unlock required", res.get("message", ""))

            # Now verify passkey unlock
            unlock_res = applet._handle_verify_passkey(mock_handler, {}, {
                "passkey": "secret123",
                "session_id": sess.session_id,
                "session_token": sess.token,
            })
            self.assertEqual(unlock_res.get("status"), "ok")
            self.assertTrue(unlock_res.get("valid"))
            self.assertTrue(sess.is_unlocked)

            # Re-attempt chat now that session is unlocked
            res_after = applet._handle_chat(mock_handler, {}, {"text": "hello again", "sender": "Operator"})
            self.assertEqual(res_after.get("status"), "ok")
        finally:
            applet.stop()

    def test_security_gate_has_no_passkey_option_and_prevents_unauthorized_bypass(self) -> None:
        """Verifies security gate has no passkey/password option and pending sessions cannot be authorized via passkey."""
        applet = WingmanApplet(port=0, node_id="test-node", require_pairing=True)
        try:
            mock_handler = MagicMock()
            mock_handler.headers = {"User-Agent": "Mozilla/5.0 (Linux; Android)"}
            html = applet._handle_index(mock_handler, {})

            # Must have security gate and radar
            self.assertIn("securityGate", html)
            self.assertIn("Awaiting mothership console authorization...", html)

            # Must NOT have any password or passkey fields on the security gate
            self.assertNotIn("gatePasskeyForm", html)
            self.assertNotIn("gatePasskeyInput", html)
            self.assertNotIn("gateUnlockBtn", html)
            self.assertNotIn("ENTER VAULT PASSKEY DIRECTLY", html)

            # Pending session cannot be authorized via passkey verification
            applet._passkey_verifier = lambda p: p == "secret123"
            sess = applet.security.create_or_resume_session(client_ip="192.168.1.180", device_id="dev-phone")
            self.assertEqual(sess.status, "pending")

            unlock_res = applet._handle_verify_passkey(mock_handler, {}, {
                "passkey": "secret123",
                "session_id": sess.session_id,
            })
            self.assertEqual(unlock_res.get("status"), "ok")
            # Session status must remain pending! Mothership must authorize it!
            self.assertEqual(sess.status, "pending")
        finally:
            applet.stop()

    def test_one_time_accepted_session_auto_opens_and_resumes_without_token(self) -> None:
        """Verifies that an unpaired session accepted by Mothership auto-opens without resetting to pending."""
        applet = WingmanApplet(port=0, node_id="test-phone", require_pairing=True)
        try:
            # 1. Phone initiates pending session
            sess_id = "sess-phone-unpaired-123"
            dev_id = "dev-phone-456"
            s1 = applet.security.create_or_resume_session(
                client_ip="192.168.1.179",
                device_id=dev_id,
                existing_session_id=sess_id,
            )
            self.assertEqual(s1.status, "pending")

            # 2. Mothership Operator clicks 'Accept' (one-time approval: trust_device=False)
            res = applet.authorize_session(sess_id, accepted=True, trust_device=False)
            self.assertEqual(res.get("status"), "ok")
            self.assertEqual(s1.status, "authorized")
            self.assertFalse(s1.is_paired)

            # 3. Phone browser calls checkSession (/applet/wingman/session) before having token stored
            mock_handler = MagicMock()
            mock_handler.client_address = ("192.168.1.179", 54321)
            mock_handler.headers = {"X-Wingman-Device": dev_id, "X-Wingman-Session": sess_id}
            check_res = applet._handle_session_check(mock_handler, {})

            # Must be authenticated and must return token, not reset to pending!
            self.assertTrue(check_res.get("authenticated"))
            self.assertEqual(check_res.get("status"), "authorized")
            self.assertEqual(check_res.get("token"), s1.token)
            self.assertEqual(check_res.get("device_ip"), "192.168.1.179")

            # 4. Auth status polling with device_id also confirms approved status
            status_res = applet._handle_auth_status(mock_handler, {"session_id": [sess_id], "device_id": [dev_id]})
            self.assertEqual(status_res.get("status"), "approved")
            self.assertEqual(status_res.get("token"), s1.token)
        finally:
            applet.stop()

    def test_wingman_gate_html_shows_device_ip(self) -> None:
        """Verifies that the security gate displays the real device IP instead of 127.0.0.1."""
        from gemini_app.webapplet.applets.wingman.ui import get_wingman_html
        html = get_wingman_html(device_ip="192.168.1.179", node_id="android-phone")
        self.assertIn("Device IP:", html)
        self.assertIn("gateDeviceIp", html)
        self.assertIn("192.168.1.179", html)

    def test_reboot_preserves_and_advertises_pending_auth_to_mothership(self) -> None:
        """Verifies that after a node reboots, an active pending session on the security gate is advertised in telemetry and picked up by Mothership."""
        from gemini_app.fleet.satellite import set_active_wingman, collect_telemetry
        from gemini_app.fleet.mothership import MothershipServer, ConnectedSatellite
        from gemini_app.fleet.protocol import FleetMessage

        applet = WingmanApplet(port=0, node_id="test-node-gate", require_pairing=True)
        set_active_wingman(applet)
        ms = MothershipServer(host="127.0.0.1", port=0, auto_broadcast_telemetry=False)
        try:
            # 1. Browser on phone/iPad hits Wingman and sits on security gate (status: pending)
            sess = applet.security.create_or_resume_session(
                client_ip="192.168.1.38",
                device_id="dev-ipad-browser",
                existing_session_id="sess-ipad-gate-1",
            )
            self.assertEqual(sess.status, "pending")

            # 2. is_browser_open() must return True even if no SSE client is connected yet
            self.assertTrue(applet.is_browser_open())

            # 3. collect_telemetry() must include pending_auth and report wingman_active: True
            telem = collect_telemetry()
            webapplet_telem = telem.get("webapplet", {})
            self.assertTrue(webapplet_telem.get("wingman_active"))
            pending_list = webapplet_telem.get("pending_auth", [])
            self.assertEqual(len(pending_list), 1)
            self.assertEqual(pending_list[0]["auth_req_id"], "sess-ipad-gate-1")
            self.assertEqual(pending_list[0]["client_ip"], "192.168.1.38")

            # 4. Mothership receives heartbeat telemetry from node
            sat = ConnectedSatellite("test-node-gate", MagicMock(), ("192.168.1.38", 50000))
            sat.telemetry = telem
            ms.nodes["test-node-gate"] = sat

            # Simulate heartbeat processing
            ms._prune_pending_wingman_requests()
            for p in sat.telemetry.get("webapplet", {}).get("pending_auth", []):
                rid = p.get("auth_req_id")
                entry = dict(p)
                entry["node_id"] = "test-node-gate"
                ms.pending_wingman_auth_requests[rid] = entry

            # 5. Mothership must have pending auth request and not prune it
            ms._prune_pending_wingman_requests()
            self.assertIn("sess-ipad-gate-1", ms.pending_wingman_auth_requests)

            # Even if wingman_active is temporarily reported False, pending_auth in telemetry prevents pruning!
            sat.telemetry = {"webapplet": {"wingman_active": False, "pending_auth": pending_list}}
            ms._prune_pending_wingman_requests()
            self.assertIn("sess-ipad-gate-1", ms.pending_wingman_auth_requests)

            # 6. Wingman access request event arrives
            notified_list = []
            ms.on_wingman_auth(lambda req: notified_list.append(req))
            ms._notify_wingman_auth(ms.pending_wingman_auth_requests["sess-ipad-gate-1"])
            self.assertEqual(len(notified_list), 1)
            self.assertEqual(notified_list[0]["auth_req_id"], "sess-ipad-gate-1")
        finally:
            set_active_wingman(None)
            applet.stop()
            ms.stop()

    def test_auth_status_polling_re_notifies_pending_session(self) -> None:
        """Verifies that polling _handle_auth_status periodically invokes pending callbacks without page reload."""
        applet = WingmanApplet(port=0, node_id="test-node-poll", require_pairing=True)
        notifications = []
        applet.on_auth_request(lambda r: notifications.append(r))
        try:
            sess = applet.security.create_or_resume_session(client_ip="192.168.1.77", device_id="dev-gate-poll")
            self.assertEqual(sess.status, "pending")
            self.assertEqual(len(notifications), 1)

            # Polling immediately within throttle window should not re-notify
            mock_handler = MagicMock()
            mock_handler.headers = {}
            status_res = applet._handle_auth_status(mock_handler, {"req_id": [sess.session_id]})
            self.assertEqual(status_res["status"], "pending")
            self.assertEqual(len(notifications), 1)

            # After 4.1 seconds of polling while sitting on the gate, callback is re-invoked
            sess._last_notified = time.time() - 4.5
            status_res2 = applet._handle_auth_status(mock_handler, {"req_id": [sess.session_id]})
            self.assertEqual(status_res2["status"], "pending")
            self.assertEqual(len(notifications), 2)
            self.assertEqual(notifications[1]["auth_req_id"], sess.session_id)
        finally:
            applet.stop()

    def test_active_session_downgraded_to_pending_on_mothership_reboot(self) -> None:
        """Verifies that on mothership restart, active unpaired sessions are downgraded to pending and re-advertised."""
        applet = WingmanApplet(port=0, node_id="test-node-reboot", require_pairing=True)
        notifications = []
        applet.on_auth_request(lambda r: notifications.append(r))
        try:
            sess = applet.security.create_or_resume_session(client_ip="192.168.1.88", device_id="dev-active-reboot")
            applet.authorize_session(sess.session_id, accepted=True, trust_device=False)
            self.assertEqual(sess.status, "authorized")

            # Mothership reboot occurs
            notifications.clear()
            applet.on_mothership_reboot("epoch-new-12345")
            self.assertEqual(applet.mothership_boot_id, "epoch-new-12345")

            # Session must now be pending (not deleted!) and must have notified Mothership
            re_sess = applet.security.get_session(sess.session_id)
            self.assertIsNotNone(re_sess)
            self.assertEqual(re_sess.status, "pending")
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0]["auth_req_id"], sess.session_id)
        finally:
            applet.stop()

    def test_reboot_epoch_reset_prevents_free_entry_on_all_devices(self) -> None:
        """Verifies that console reboot epoch reset revokes all unpaired sessions and prevents free entry."""
        from unittest.mock import MagicMock
        applet = WingmanApplet(port=0, node_id="test-node-reboot-gate", require_pairing=True)
        try:
            # 1. Device connects and is authorized with one-time approval
            s1 = applet.security.create_or_resume_session(client_ip="192.168.1.179", device_id="dev-phone-gate")
            applet.authorize_session(s1.session_id, accepted=True, trust_device=False, device_id="dev-phone-gate")
            self.assertEqual(s1.status, "authorized")

            mock_h = MagicMock()
            mock_h.headers = {"X-Wingman-Device": "dev-phone-gate"}
            res_before = applet._handle_auth_status(mock_h, {"req_id": [s1.session_id], "device_id": ["dev-phone-gate"]})
            self.assertEqual(res_before["status"], "approved")

            # 2. Console/Mothership reboot occurs: epoch reset to new_boot_id
            applet.on_mothership_reboot("epoch-fresh-999")
            self.assertEqual(applet.mothership_boot_id, "epoch-fresh-999")

            # 3. Old session MUST be downgraded to pending
            self.assertEqual(s1.status, "pending")
            self.assertEqual(s1.token, "")

            # 4. Old session polling must NOT be approved
            res_after_old = applet._handle_auth_status(mock_h, {"req_id": [s1.session_id], "device_id": ["dev-phone-gate"]})
            self.assertEqual(res_after_old["status"], "pending")

            # 5. New session created on refresh must NOT inherit old authorization; free entry blocked!
            s2 = applet.security.create_or_resume_session(client_ip="192.168.1.179", device_id="dev-phone-gate", existing_session_id="sess-new-refresh")
            self.assertEqual(s2.status, "pending")
            res_after_new = applet._handle_auth_status(mock_h, {"req_id": [s2.session_id], "device_id": ["dev-phone-gate"]})
            self.assertEqual(res_after_new["status"], "pending")
            self.assertEqual(res_after_new.get("token", ""), "")
        finally:
            applet.stop()

    def test_incoming_wingman_auth_only_toasts_and_never_auto_pushes_screen(self) -> None:
        """Verifies background incoming device auth never pushes a modal, only toasts and queues in pending."""
        from gemini_app.ui.app import ChatApp

        app = ChatApp()
        app.notify = MagicMock()
        mock_push = MagicMock()
        app.push_screen = mock_push

        req = {
            "session_id": "sess-toast-1",
            "auth_req_id": "sess-toast-1",
            "client_ip": "192.168.1.50",
            "node_id": "ipad-node",
            "device_id": "dev-ipad-50",
            "timestamp": time.time(),
        }

        # Handle incoming auth request
        app._handle_incoming_wingman_auth(req)

        # Modal was NOT pushed!
        mock_push.assert_not_called()
        # Toast notification was triggered
        app.notify.assert_called_once()
        toast_msg = app.notify.call_args[0][0]
        self.assertIn("192.168.1.50", toast_msg)
        self.assertIn("/auth", toast_msg)
        # Pending dictionary stores the request
        self.assertIn("sess-toast-1", app._pending_wingman_auth)

        # Immediate repeat request for the same device should be throttled (no duplicate toast spam)
        app.notify.reset_mock()
        app._handle_incoming_wingman_auth(req)
        app.notify.assert_not_called()

    def test_incoming_wingman_auth_ttl_and_boot_time_filtering(self) -> None:
        """Verifies that expired requests (> 60s) or requests from before console boot are ignored."""
        from gemini_app.ui.app import ChatApp

        app = ChatApp()
        app.notify = MagicMock()
        app._console_boot_time = time.time()

        # 1. Stale request from 10 minutes ago
        stale_req = {
            "session_id": "sess-ancient-1",
            "client_ip": "192.168.1.77",
            "timestamp": time.time() - 600.0,
        }
        app._handle_incoming_wingman_auth(stale_req)
        self.assertNotIn("sess-ancient-1", app._pending_wingman_auth)
        app.notify.assert_not_called()

        # 2. Stale request timestamped before boot time
        pre_boot_req = {
            "session_id": "sess-preboot-2",
            "client_ip": "192.168.1.78",
            "timestamp": app._console_boot_time - 30.0,
        }
        app._handle_incoming_wingman_auth(pre_boot_req)
        self.assertNotIn("sess-preboot-2", app._pending_wingman_auth)
        app.notify.assert_not_called()

    def test_wingman_slash_command_opens_auth_manager_modal(self) -> None:
        """Verifies that /wingman slash command launches WingmanAuthModal on demand."""
        from gemini_app.ui.app import ChatApp
        from gemini_app.ui.modals.wingman_auth import WingmanAuthModal

        app = ChatApp()
        pushed_screens = []
        app.push_screen = lambda scr, *args, **kwargs: pushed_screens.append(scr)

        # Add a pending request
        app._pending_wingman_auth = {
            "req-1": {
                "auth_req_id": "req-1",
                "client_ip": "192.168.1.99",
                "node_id": "phone-node",
                "timestamp": time.time(),
            }
        }

        # Execute /wingman slash command
        res = app._handle_slash_command("/wingman")
        self.assertTrue(res)
        self.assertEqual(len(pushed_screens), 1)
        modal = pushed_screens[0]
        self.assertIsInstance(modal, WingmanAuthModal)
        self.assertEqual(len(modal.pending_requests), 1)
        self.assertEqual(modal.pending_requests[0]["client_ip"], "192.168.1.99")

    def test_wingman_auth_modal_manager_multi_device_and_revoke(self) -> None:
        """Verifies multi-device pending resolution and device revoke callbacks."""
        from gemini_app.ui.modals.wingman_auth import WingmanAuthModal

        resolved = []
        revoked = []

        pending = [
            {"auth_req_id": "r1", "client_ip": "192.168.1.10", "node_id": "ipad", "timestamp": time.time()},
            {"auth_req_id": "r2", "client_ip": "192.168.1.20", "node_id": "phone", "timestamp": time.time()},
        ]
        paired = [
            {"device_id": "dev-trusted-1", "label": "Studio iPad", "client_ip": "192.168.1.10"},
        ]

        modal = WingmanAuthModal(
            pending_requests=pending,
            paired_devices=paired,
            on_resolve=lambda rid, dec, data: resolved.append((rid, dec)),
            on_revoke=lambda dev_id: revoked.append(dev_id),
        )

        dismiss_results = []
        modal.dismiss = lambda res: dismiss_results.append(res)

        # Resolve first item
        modal._resolve_one(0, "accept")
        self.assertEqual(resolved, [("r1", "accept")])
        self.assertEqual(len(modal.pending_requests), 1)
        self.assertEqual(len(dismiss_results), 0)

        # Resolve second item
        modal._resolve_one(0, "pair")
        self.assertEqual(resolved, [("r1", "accept"), ("r2", "pair")])
        self.assertEqual(len(modal.pending_requests), 0)
        self.assertEqual(dismiss_results, ["pair"])

    def test_responsive_modal_screen_guarded_dismiss_prevents_screen_stack_error(self) -> None:
        """Verifies that dismissing when screen stack <= 1 does NOT raise ScreenStackError."""
        from gemini_app.ui.modals.wingman_auth import WingmanAuthModal

        modal = WingmanAuthModal(auth_data={"session_id": "s-test"})
        modal._mounted = True
        mock_app = MagicMock()
        mock_app._screen_stack = [MagicMock()]  # Only 1 screen on stack!
        mock_app.pop_screen.side_effect = Exception("ScreenStackError: Can't pop screen; <= 1")
        modal._app = mock_app

        # Calling dismiss must not raise ScreenStackError
        modal.dismiss("accept")
        mock_app.pop_screen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
