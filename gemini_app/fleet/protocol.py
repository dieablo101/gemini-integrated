"""Communication protocol for Mothership and Satellite nodes."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

DEFAULT_PORT = 7331
PROTOCOL_VERSION = "1.0.0"


class FleetMessage:
    """Standard message envelope for fleet communications over TCP."""

    TYPE_REGISTER = "register"
    TYPE_HEARTBEAT = "heartbeat"
    TYPE_COMMAND = "command"
    TYPE_RESPONSE = "response"
    TYPE_DISCONNECT = "disconnect"
    TYPE_ERROR = "error"
    TYPE_TELEMETRY = "telemetry"
    TYPE_EVENT = "event"
    TYPE_CHALLENGE = "challenge"
    TYPE_AUTH = "auth"
    TYPE_AUTH_OK = "auth_ok"
    TYPE_AUTH_FAIL = "auth_fail"

    def __init__(
        self,
        msg_type: str,
        node_id: str,
        payload: Optional[Dict[str, Any]] = None,
        msg_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        self.type = msg_type
        self.node_id = node_id
        self.payload = payload or {}
        self.msg_id = msg_id or f"{node_id}-{int(time.time() * 1000)}"
        self.timestamp = timestamp or time.time()
        self.version = PROTOCOL_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "node_id": self.node_id,
            "msg_id": self.msg_id,
            "timestamp": self.timestamp,
            "version": self.version,
            "payload": self.payload,
        }

    def serialize(self) -> bytes:
        """Serializes message to a newline-terminated JSON UTF-8 byte stream."""
        return (json.dumps(self.to_dict()) + "\n").encode("utf-8")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FleetMessage:
        return cls(
            msg_type=data.get("type", "unknown"),
            node_id=data.get("node_id", "unknown"),
            payload=data.get("payload", {}),
            msg_id=data.get("msg_id"),
            timestamp=data.get("timestamp"),
        )

    @classmethod
    def deserialize(cls, raw: str) -> FleetMessage:
        """Parses a single JSON line into a FleetMessage."""
        data = json.loads(raw.strip())
        return cls.from_dict(data)
