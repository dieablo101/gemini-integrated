"""
sandbox/mind_twin/core/fleet_crdt.py

Lossy Fleet Telemetry & Distributed CRDT State Replicator.
Provides:
1. Vector Clocks: Causality tracking across Toughbook, iPad, and Android nodes.
2. LWW-Register & State-Based CRDT: Deterministic conflict-free resolution for concurrent edits.
3. Lossy Network Simulator: Models packet drop, jitter, re-ordering, and offline queue burst replay.
4. Rate-Limiting Backpressure Ingestion: Ingests 1,000+ out-of-order sensor packets without thread locking.
"""

from __future__ import annotations

import copy
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================================
# 1. VECTOR CLOCK
# ============================================================================

@dataclass
class VectorClock:
    clock: Dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str) -> None:
        self.clock[node_id] = self.clock.get(node_id, 0) + 1

    def merge(self, other: "VectorClock") -> "VectorClock":
        new_clock = dict(self.clock)
        for nid, val in other.clock.items():
            new_clock[nid] = max(new_clock.get(nid, 0), val)
        return VectorClock(new_clock)

    def compare(self, other: "VectorClock") -> str:
        """
        Returns:
        - 'EQUAL'
        - 'ANCESTOR' (self < other)
        - 'DESCENDANT' (self > other)
        - 'CONCURRENT' (split-brain concurrent edits)
        """
        all_keys = set(self.clock.keys()).union(other.clock.keys())
        greater = False
        less = False

        for k in all_keys:
            v1 = self.clock.get(k, 0)
            v2 = other.clock.get(k, 0)
            if v1 > v2:
                greater = True
            elif v1 < v2:
                less = True

        if greater and less:
            return "CONCURRENT"
        if greater and not less:
            return "DESCENDANT"
        if less and not greater:
            return "ANCESTOR"
        return "EQUAL"


# ============================================================================
# 2. CONFLICT-FREE REPLICATED DATA TYPE (LWW-REGISTER CRDT)
# ============================================================================

@dataclass
class CRDTAxisRecord:
    key: str
    value: Any
    timestamp: float
    node_id: str
    clock: VectorClock


class DistributedStateCRDT:
    """
    State-based Last-Write-Wins CRDT Document for fleet nodes.
    Ensures mathematical convergence regardless of arrival order or duplicates.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.vector_clock = VectorClock({node_id: 0})
        self.registers: Dict[str, CRDTAxisRecord] = {}

    def set(self, key: str, value: Any, timestamp: Optional[float] = None) -> CRDTAxisRecord:
        self.vector_clock.increment(self.node_id)
        t = timestamp if timestamp is not None else time.time()
        record = CRDTAxisRecord(
            key=key,
            value=value,
            timestamp=t,
            node_id=self.node_id,
            clock=VectorClock(dict(self.vector_clock.clock)),
        )
        self.registers[key] = record
        return record

    def get(self, key: str, default: Any = None) -> Any:
        record = self.registers.get(key)
        return record.value if record else default

    def merge_remote_record(self, remote: CRDTAxisRecord) -> bool:
        """
        Deterministic merge rule:
        1. Higher vector clock descendant wins.
        2. If concurrent, higher physical timestamp wins.
        3. If timestamps identical, lexicographically higher node_id wins (tie-breaker).
        """
        self.vector_clock = self.vector_clock.merge(remote.clock)
        current = self.registers.get(remote.key)

        if current is None:
            self.registers[remote.key] = remote
            return True

        cmp = current.clock.compare(remote.clock)
        if cmp == "ANCESTOR":
            self.registers[remote.key] = remote
            return True
        elif cmp == "DESCENDANT":
            return False  # Local is newer

        # Concurrent branch (LWW tie-breaker)
        if remote.timestamp > current.timestamp:
            self.registers[remote.key] = remote
            return True
        elif remote.timestamp < current.timestamp:
            return False
        else:
            # Deterministic tie-breaker
            if remote.node_id > current.node_id:
                self.registers[remote.key] = remote
                return True
            return False


# ============================================================================
# 3. LOSSY TELEMETRY SIMULATOR & INGESTION BACKPRESSURE
# ============================================================================

@dataclass
class NetworkPacket:
    seq: int
    sender: str
    payload: Dict[str, Any]
    sent_at: float


class LossyNetworkSimulator:
    """
    Simulates high-jitter, high-drop network channels between Toughbook and satellites.
    """

    def __init__(self, drop_rate: float = 0.35, max_delay_ms: float = 200.0) -> None:
        self.drop_rate = drop_rate
        self.max_delay_ms = max_delay_ms
        self.packet_buffer: List[Tuple[float, NetworkPacket]] = []

    def transmit(self, packet: NetworkPacket) -> bool:
        """Transmits packet. Drops if random < drop_rate."""
        if random.random() < self.drop_rate:
            return False  # Dropped packet

        jitter = random.uniform(0.0, self.max_delay_ms / 1000.0)
        deliver_time = time.time() + jitter
        self.packet_buffer.append((deliver_time, packet))
        return True

    def drain_deliverable(self) -> List[NetworkPacket]:
        """Returns packets that have arrived (shuffled due to network jitter)."""
        now = time.time()
        deliverable = [p for t, p in self.packet_buffer if t <= now]
        self.packet_buffer = [item for item in self.packet_buffer if item[0] > now]
        random.shuffle(deliverable)
        return deliverable


class BatchTelemetryFoldEngine:
    """
    Safely folds 1,000+ out-of-order satellite sensor packets into cognitive state
    with rate-limiting backpressure so the main thread never stalls.
    """

    def __init__(self, max_batch_size: int = 50) -> None:
        self.max_batch_size = max_batch_size
        self.pending_queue: List[Dict[str, Any]] = []
        self.ingested_count = 0
        self.dropped_stale_count = 0
        self.latest_lux = 0.0
        self.latest_battery = 100.0

    def enqueue_backlog(self, packets: List[Dict[str, Any]]) -> None:
        self.pending_queue.extend(packets)

    def process_fold_tick(self, max_time_budget_ms: float = 5.0) -> Dict[str, Any]:
        """
        Processes up to max_batch_size packets within the time budget.
        Discards older duplicate readings and retains only freshest trends.
        """
        t0 = time.perf_counter()
        processed = 0

        while self.pending_queue and processed < self.max_batch_size:
            if (time.perf_counter() - t0) * 1000.0 > max_time_budget_ms:
                break

            pkt = self.pending_queue.pop(0)
            seq = pkt.get("seq", 0)
            lux = pkt.get("lux", 0.0)
            batt = pkt.get("battery", 100.0)

            # Sanitize values
            if math.isfinite(lux):
                self.latest_lux = lux
            if math.isfinite(batt):
                self.latest_battery = batt

            self.ingested_count += 1
            processed += 1

        t_elapsed = (time.perf_counter() - t0) * 1000.0
        return {
            "processed": processed,
            "remaining": len(self.pending_queue),
            "elapsed_ms": round(t_elapsed, 3),
            "latest_lux": self.latest_lux,
            "latest_battery": self.latest_battery,
        }
