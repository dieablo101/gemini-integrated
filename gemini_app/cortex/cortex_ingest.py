"""
cortex_ingest.py - Ingestion Pipeline from Live Chats to Relational Cortex.

Scans the console's live chat repository (~/.gemini/chats/), extracts all turns
up to the latest conversation message, dissects them using the ChatDissector
and UserBurstConsolidator, and populates the SQLite Relational Cortex (cortex.db).

Provides clean pre-computation of:
1. Invariant rules and architectural anchors.
2. Relational hyperedges between intersecting domains.
3. Topic horizons for double-tap Home positioning.
"""

from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from gemini_app.storage.chat_store import ChatStore
from gemini_app.config import CHATS_DIR, GEMINI_HOME
from gemini_app.cortex.chat_dissector import (
    ChatDissector, ConcurrentStagingBuffer, ChatShard, ShardDomain, ShardCategory
)
from gemini_app.cortex.relational_cortex import RelationalCortex


@dataclass
class IngestionReport:
    chats_scanned: int = 0
    total_turns_processed: int = 0
    shards_created: int = 0
    edges_created: int = 0
    invariant_rules_count: int = 0
    technical_specs_count: int = 0
    domain_breakdown: Dict[str, int] = field(default_factory=dict)
    active_topic_horizon_index: int = 0
    duration_ms: float = 0.0


class CortexIngestPipeline:
    """
    Ingests live chat transcripts and managed state into the Relational Cortex.
    """
    def __init__(
        self,
        cortex: Optional[RelationalCortex] = None,
        db_path: Optional[str] = None,
        chats_dir: Optional[Path | str] = None
    ):
        target_db = db_path or str(GEMINI_HOME / "cortex.db")
        self.cortex = cortex or RelationalCortex(db_path=target_db)
        self.chat_store = ChatStore(chats_dir=chats_dir or CHATS_DIR)
        self.dissector = ChatDissector()

    def ingest_chat_by_id(self, chat_id: str) -> IngestionReport:
        """
        Ingests a specific chat transcript into the cortex.
        """
        start_time = time.time()
        chat_data = self.chat_store.load_chat(chat_id)
        history = chat_data.get("history", [])
        
        report = IngestionReport(chats_scanned=1, total_turns_processed=len(history))
        if not history:
            report.duration_ms = round((time.time() - start_time) * 1000, 2)
            return report

        # Push messages through the concurrent staging buffer
        staging = ConcurrentStagingBuffer(capacity=len(history) + 50)
        for idx, turn in enumerate(history):
            tid = turn.get("turn_id") or f"turn_{idx}"
            role = turn.get("role") or ("user" if turn.get("sender") == "User" else "model")
            text = turn.get("text", "")
            ts = turn.get("timestamp") or time.time()
            staging.push(turn_id=tid, turn_index=idx, role=role, text=text, timestamp=ts)

        # Dissect and consolidate user bursts
        staged_items = staging.drain_for_valuation()
        shards = self.dissector.dissect_staged_stream(staged_items)

        # Insert shards in batch into cortex
        self.cortex.batch_insert_shards(shards)
        report.shards_created = len(shards)

        # Auto-link relational edges based on shared semantic concepts
        links = self.cortex.auto_link_shards(shards, min_shared_keywords=2)
        report.edges_created = links

        # Track domain and category breakdowns
        for s in shards:
            d_name = s.domain.value if isinstance(s.domain, ShardDomain) else str(s.domain)
            report.domain_breakdown[d_name] = report.domain_breakdown.get(d_name, 0) + 1
            if s.category == ShardCategory.INVARIANT_RULE:
                report.invariant_rules_count += 1
            elif s.category == ShardCategory.TECHNICAL_SPEC:
                report.technical_specs_count += 1

        # Detect active topic horizon (where recent topic shift occurred)
        report.active_topic_horizon_index = self._calculate_topic_horizon(history)
        report.duration_ms = round((time.time() - start_time) * 1000, 2)

        return report

    def ingest_all_chats(self) -> IngestionReport:
        """
        Ingests all chats from the chat store into the cortex.
        """
        start_time = time.time()
        chats = self.chat_store.list_chats()
        combined_report = IngestionReport(chats_scanned=len(chats))

        for chat_meta in chats:
            cid = chat_meta["id"]
            rep = self.ingest_chat_by_id(cid)
            combined_report.total_turns_processed += rep.total_turns_processed
            combined_report.shards_created += rep.shards_created
            combined_report.edges_created += rep.edges_created
            combined_report.invariant_rules_count += rep.invariant_rules_count
            combined_report.technical_specs_count += rep.technical_specs_count
            for d, c in rep.domain_breakdown.items():
                combined_report.domain_breakdown[d] = combined_report.domain_breakdown.get(d, 0) + c
            if rep.active_topic_horizon_index > combined_report.active_topic_horizon_index:
                combined_report.active_topic_horizon_index = rep.active_topic_horizon_index

        combined_report.duration_ms = round((time.time() - start_time) * 1000, 2)
        return combined_report

    def _calculate_topic_horizon(self, history: List[Dict[str, Any]]) -> int:
        """
        Calculates the index where the most recent sprint topic began.
        Returns 0 if no clear boundary is found.
        """
        if len(history) < 5:
            return 0

        # Scan backwards from the end to detect domain shift
        recent_domain: Optional[ShardDomain] = None
        for i in range(len(history) - 1, -1, -1):
            text = history[i].get("text", "")
            d = self.dissector.classify_domain(text)
            if recent_domain is None and d != ShardDomain.GENERAL:
                recent_domain = d
            elif recent_domain is not None and d != recent_domain and d != ShardDomain.GENERAL:
                # Boundary detected
                return max(0, i + 1)

        return 0


if __name__ == "__main__":
    pipeline = CortexIngestPipeline()
    report = pipeline.ingest_all_chats()
    print("=== Relational Cortex Ingestion Complete ===")
    print(f"Chats scanned: {report.chats_scanned}")
    print(f"Total turns processed: {report.total_turns_processed}")
    print(f"Shards created: {report.shards_created}")
    print(f"Relational edges: {report.edges_created}")
    print(f"Invariant rules: {report.invariant_rules_count}")
    print(f"Technical specs: {report.technical_specs_count}")
    print(f"Duration: {report.duration_ms}ms")
    print(f"Domain breakdown: {report.domain_breakdown}")
