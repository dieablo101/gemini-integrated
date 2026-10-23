"""
sandbox/mind_twin/core/subconscious/epiphany_channel.py

Lockless / Thread-safe Epiphany Trajection Channel.
Provides a non-blocking IPC channel between the background subconscious cruncher
and the conscious 7-slot working memory gate.
"""

from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EpiphanyPacket:
    """A verified breakthrough packet ready for conscious trajection."""
    packet_id: str
    spark_name: str
    domain_bridge: List[str]
    feasibility_score: float
    summary: str
    mechanism: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "spark_name": self.spark_name,
            "domain_bridge": self.domain_bridge,
            "feasibility_score": round(self.feasibility_score, 3),
            "summary": self.summary,
            "mechanism": self.mechanism,
            "created_at": self.created_at,
        }


class EpiphanyChannel:
    """
    Non-blocking FIFO ring channel for passing epiphanies into conscious working memory.
    """

    def __init__(self, capacity: int = 16) -> None:
        self.capacity = capacity
        self._buffer: collections.deque[EpiphanyPacket] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self.total_packets_sent: int = 0
        self.total_packets_delivered: int = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def __bool__(self) -> bool:
        """Channel instance truthiness is always True regardless of buffer occupancy."""
        return True

    def push(self, packet: EpiphanyPacket) -> bool:
        """Pushes a verified epiphany into the channel. Drops oldest if full."""
        with self._lock:
            self._buffer.append(packet)
            self.total_packets_sent += 1
            return True

    def pop(self) -> Optional[EpiphanyPacket]:
        """Pops the next available epiphany without blocking. Returns None if empty."""
        with self._lock:
            if not self._buffer:
                return None
            packet = self._buffer.popleft()
            self.total_packets_delivered += 1
            return packet

    def peek(self) -> Optional[EpiphanyPacket]:
        """Peeks at the top epiphany without consuming it."""
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[0]

    def drain(self) -> List[EpiphanyPacket]:
        """Alias for drain_all()."""
        return self.drain_all()

    def drain_all(self) -> List[EpiphanyPacket]:
        """Drains and returns all queued epiphanies."""
        with self._lock:
            items = list(self._buffer)
            self.total_packets_delivered += len(items)
            self._buffer.clear()
            return items

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._buffer) == 0

    def size(self) -> int:
        with self._lock:
            return len(self._buffer)
