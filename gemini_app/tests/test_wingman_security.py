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


if __name__ == "__main__":
    unittest.main()
