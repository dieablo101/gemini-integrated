"""Unix Domain Socket IPC Server."""

import asyncio
from collections.abc import Callable
import json
from pathlib import Path


class SocketServer:

    def __init__(self, socket_path: Path, message_handler: Callable[[dict], None]) -> None:
        self.socket_path = socket_path
        self.message_handler = message_handler
        self._server: asyncio.AbstractServer | None = None

    async def start(self, on_error: Callable[[str], None] | None = None) -> None:
        if self.socket_path.exists():
            self.socket_path.unlink()

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=str(self.socket_path),
            )
        except Exception as e:
            if on_error:
                on_error(str(e))

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        data = await reader.read()
        if data:
            try:
                payload = json.loads(data.decode("utf-8"))
                if payload.get("action") == "insert":
                    self.message_handler(payload)
            except Exception:
                pass
        writer.close()
        await writer.wait_closed()

    def stop(self) -> None:
        if self._server:
            self._server.close()
        if self.socket_path.exists():
            self.socket_path.unlink(missing_ok=True)
