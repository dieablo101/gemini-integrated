"""
feed_lens.py - Bi-Mental Continuous Pagination Feed Lens.

Provides a dynamic cognitive projection over historical and live chat shards,
allowing bidirectional continuous pagination where relevance is governed by
both user focus and Gemini working memory slots rather than flat chronology alone.
"""

from __future__ import annotations
import math
import time
from enum import Enum
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from sandbox.mind_twin.core.relational_cortex import RelationalCortex
from sandbox.mind_twin.core.chat_dissector import ShardDomain, ShardCategory


class LensMode(str, Enum):
    RAW = "RAW"                           # Pure chronological linear stream
    COGNITIVE = "COGNITIVE"               # Bi-mental relevance projection with dynamic folding
    DECISION_CARDS = "DECISION_CARDS"     # High-density invariant rules & technical specs only


@dataclass
class VisibleShard:
    shard_id: str
    turn_index: int
    role: str
    domain: str
    category: str
    salience: float
    score: float
    summary: str
    content: str
    keywords: List[str]
    is_fold: bool = False


@dataclass
class FoldedSegment:
    start_turn: int
    end_turn: int
    count: int
    dominant_category: str
    summary_label: str
    is_fold: bool = True
    score: float = 0.0


ProjectionItem = Union[VisibleShard, FoldedSegment]


class FeedLens:
    """
    Virtual viewport projection engine for bilateral terminal continuous pagination.
    """
    def __init__(
        self,
        cortex: RelationalCortex,
        viewport_height: int = 15,
        mode: LensMode = LensMode.COGNITIVE
    ):
        self.cortex = cortex
        self.viewport_height = viewport_height
        self.mode = mode
        self.scroll_offset = 0  # 0 = at bottom (present), >0 = scrolled up into past

        # Bi-mental alignment states
        self.user_domain: Optional[str] = None
        self.user_keywords: List[str] = []
        self.gemini_slots: List[str] = []

        # Weights
        self.w_recency = 0.4
        self.w_topic = 0.35
        self.w_gemini = 0.25

    def set_mode(self, mode: LensMode) -> None:
        self.mode = mode

    def update_bi_mental_focus(
        self,
        user_domain: Optional[str] = None,
        user_keywords: Optional[List[str]] = None,
        gemini_slots: Optional[List[str]] = None
    ) -> None:
        if user_domain is not None:
            self.user_domain = user_domain
        if user_keywords is not None:
            self.user_keywords = [k.lower() for k in user_keywords]
        if gemini_slots is not None:
            self.gemini_slots = [s.lower() for s in gemini_slots]

    def scroll_up(self, delta: int = 5) -> int:
        self.scroll_offset = max(0, self.scroll_offset + delta)
        return self.scroll_offset

    def scroll_down(self, delta: int = 5) -> int:
        self.scroll_offset = max(0, self.scroll_offset - delta)
        return self.scroll_offset

    def jump_to_present(self) -> None:
        self.scroll_offset = 0

    def calculate_shard_score(self, shard: Dict[str, Any], max_turn_index: int) -> float:
        # 1. Recency component: (0.0 -> 1.0)
        turn_idx = shard["turn_index"]
        recency_norm = turn_idx / max(max_turn_index, 1)

        # Invert distance relative to current scroll offset
        # When scroll_offset is small, recent turns get top recency boost
        effective_recency = recency_norm

        # 2. Topic alignment with user focus (0.0 -> 1.0)
        topic_match = 0.0
        if self.user_domain and shard["domain"] == self.user_domain:
            topic_match += 0.6
        shard_kws = shard.get("keywords", [])
        if self.user_keywords and shard_kws:
            common = set(self.user_keywords).intersection(set([k.lower() for k in shard_kws]))
            if common:
                topic_match += min(0.4, len(common) * 0.15)

        # 3. Gemini working memory slots alignment (0.0 -> 1.0)
        gemini_match = 0.0
        if self.gemini_slots:
            content_lower = shard["content"].lower()
            for slot_kw in self.gemini_slots:
                if slot_kw in content_lower or slot_kw in shard["summary"].lower():
                    gemini_match += 0.3
            gemini_match = min(1.0, gemini_match)

        # Salience modifier
        salience_mult = min(1.5, shard["salience"])

        score = (
            (self.w_recency * effective_recency) +
            (self.w_topic * topic_match) +
            (self.w_gemini * gemini_match)
        ) * salience_mult

        # Invariant rules receive a persistent visibility floor
        if shard["category"] == ShardCategory.INVARIANT_RULE.value:
            score = max(score, 0.75)

        return round(score, 4)

    def render_projection(self) -> List[ProjectionItem]:
        """
        Projects a continuous pagination window based on current scroll offset and lens mode.
        Returns a list of VisibleShard and FoldedSegment items fitting the viewport.
        """
        if self.mode == LensMode.RAW:
            return self._render_raw()
        elif self.mode == LensMode.DECISION_CARDS:
            return self._render_decisions()
        else:
            return self._render_cognitive()

    def _render_raw(self) -> List[ProjectionItem]:
        # Fetch sequential shards ordered by turn_index
        all_shards = self.cortex.query_shards(limit=500, order_by_salience=False)
        if not all_shards:
            return []
        
        # Paginate from bottom
        # scroll_offset 0 means the last `viewport_height` items
        total = len(all_shards)
        end_idx = max(0, total - self.scroll_offset)
        start_idx = max(0, end_idx - self.viewport_height)
        slice_items = all_shards[start_idx:end_idx]

        visible: List[ProjectionItem] = []
        for s in slice_items:
            visible.append(VisibleShard(
                shard_id=s["shard_id"],
                turn_index=s["turn_index"],
                role=s["role"],
                domain=s["domain"],
                category=s["category"],
                salience=s["salience"],
                score=1.0,
                summary=s["summary"],
                content=s["content"],
                keywords=s["keywords"]
            ))
        return visible

    def _render_decisions(self) -> List[ProjectionItem]:
        # Only invariant rules, specs, and anchors
        all_shards = self.cortex.query_shards(limit=500, order_by_salience=True)
        decision_shards = [
            s for s in all_shards
            if s["category"] in (ShardCategory.INVARIANT_RULE.value, ShardCategory.TECHNICAL_SPEC.value, ShardCategory.PROJECT_ANCHOR.value)
        ]
        decision_shards.sort(key=lambda x: x["turn_index"])
        
        total = len(decision_shards)
        end_idx = max(0, total - self.scroll_offset)
        start_idx = max(0, end_idx - self.viewport_height)
        slice_items = decision_shards[start_idx:end_idx]

        return [
            VisibleShard(
                shard_id=s["shard_id"],
                turn_index=s["turn_index"],
                role=s["role"],
                domain=s["domain"],
                category=s["category"],
                salience=s["salience"],
                score=s["salience"],
                summary=s["summary"],
                content=s["content"],
                keywords=s["keywords"]
            )
            for s in slice_items
        ]

    def _render_cognitive(self) -> List[ProjectionItem]:
        all_shards = self.cortex.query_shards(limit=500, order_by_salience=False)
        if not all_shards:
            return []

        max_turn = max(s["turn_index"] for s in all_shards)
        
        # Score each shard
        scored = []
        for s in all_shards:
            sc = self.calculate_shard_score(s, max_turn)
            scored.append((s, sc))

        # Bottom 4 turns (immediate present) are always kept visible if scroll_offset == 0
        threshold = 0.35
        
        projected_stream: List[ProjectionItem] = []
        fold_buffer: List[Dict[str, Any]] = []

        def flush_fold():
            if not fold_buffer:
                return
            dominant = fold_buffer[0]["category"]
            projected_stream.append(FoldedSegment(
                start_turn=fold_buffer[0]["turn_index"],
                end_turn=fold_buffer[-1]["turn_index"],
                count=len(fold_buffer),
                dominant_category=dominant,
                summary_label=f"Folded {len(fold_buffer)} background messages ({dominant} / transient background)"
            ))
            fold_buffer.clear()

        for s, sc in scored:
            # Immediate present turns stay visible
            is_present_anchor = (max_turn - s["turn_index"] < 3) and (self.scroll_offset == 0)
            
            if sc >= threshold or is_present_anchor:
                flush_fold()
                projected_stream.append(VisibleShard(
                    shard_id=s["shard_id"],
                    turn_index=s["turn_index"],
                    role=s["role"],
                    domain=s["domain"],
                    category=s["category"],
                    salience=s["salience"],
                    score=sc,
                    summary=s["summary"],
                    content=s["content"],
                    keywords=s["keywords"]
                ))
            else:
                fold_buffer.append(s)

        flush_fold()

        # Now paginate the projected stream according to scroll_offset
        total = len(projected_stream)
        end_idx = max(0, total - self.scroll_offset)
        start_idx = max(0, end_idx - self.viewport_height)
        
        return projected_stream[start_idx:end_idx]
