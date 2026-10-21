"""Unit tests for Bilateral Task Runner & Live Status Reporting Service."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gemini_app.task_runner import (
    clear_status,
    cli_main,
    notify_chat,
    send_console_event,
    update_status,
)


class TestTaskRunner(unittest.TestCase):
    def test_send_console_event_fallback_when_socket_missing(self):
        with patch("gemini_app.task_runner.SOCKET_PATH", Path("/tmp/nonexistent_socket_test.sock")):
            result = send_console_event({"action": "status", "text": "testing fallback"})
            self.assertFalse(result)

    def test_send_console_event_success_with_mock_server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_sock = Path(tmpdir) / "test.sock"
            received_messages = []

            async def handle_client(reader, writer):
                data = await reader.read(65536)
                if data:
                    received_messages.append(json.loads(data.decode("utf-8")))
                writer.write(b'{"status": "ok"}')
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            async def run_server_and_client():
                server = await asyncio.start_unix_server(handle_client, path=str(test_sock))

                def _run_sync_calls():
                    with patch("gemini_app.task_runner.SOCKET_PATH", test_sock):
                        res1 = update_status(
                            text="Compiling test project...",
                            toast="Compilation 50%",
                            pulse_nav=True,
                            color="green",
                        )
                        res2 = notify_chat(text="Build successful!", toast="Done")
                        res3 = clear_status()
                    return res1, res2, res3

                res1, res2, res3 = await asyncio.to_thread(_run_sync_calls)
                server.close()
                await server.wait_closed()
                return res1, res2, res3

            res1, res2, res3 = asyncio.run(run_server_and_client())
            self.assertTrue(res1)
            self.assertTrue(res2)
            self.assertTrue(res3)
            self.assertEqual(len(received_messages), 3)

            # Check status message payload
            self.assertEqual(received_messages[0]["action"], "status")
            self.assertEqual(received_messages[0]["text"], "Compiling test project...")
            self.assertEqual(received_messages[0]["toast"], "Compilation 50%")
            self.assertTrue(received_messages[0]["pulse_nav"])
            self.assertEqual(received_messages[0]["palette"], "green")

            # Check chat notification payload
            self.assertEqual(received_messages[1]["action"], "notify_chat")
            self.assertEqual(received_messages[1]["text"], "Build successful!")

            # Check clear payload
            self.assertEqual(received_messages[2]["action"], "status")
            self.assertTrue(received_messages[2]["clear"])

    def test_cli_main_arguments(self):
        with patch("gemini_app.task_runner.send_console_event", return_value=True) as mock_send:
            # Test status update CLI
            rc = cli_main(["Building Godot...", "--toast", "Started", "--pulse", "--color", "magenta"])
            self.assertEqual(rc, 0)
            mock_send.assert_called_with({
                "action": "status",
                "text": "Building Godot...",
                "clear": False,
                "toast": "Started",
                "title": "",
                "severity": "information",
                "duration": 3.5,
                "pulse_nav": True,
                "palette": "magenta",
            })

            # Test clear CLI
            mock_send.reset_mock()
            rc = cli_main(["--clear"])
            self.assertEqual(rc, 0)
            mock_send.assert_called_with({"action": "status", "clear": True})

            # Test chat notification CLI
            mock_send.reset_mock()
            rc = cli_main(["--chat", "Compilation complete!", "--toast", "Done"])
            self.assertEqual(rc, 0)
            mock_send.assert_called_with({
                "action": "notify_chat",
                "text": "Compilation complete!",
                "role": "gemini",
                "pulse_nav": False,
                "toast": "Done",
                "title": "Task Complete",
            })


if __name__ == "__main__":
    unittest.main()
