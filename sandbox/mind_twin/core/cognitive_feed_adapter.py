"""
cognitive_feed_adapter.py - Non-invasive Feed Adapter for Textual FeedArea.

Adapts Relational Cortex shards and Cognitive Interludes directly into the
application's existing `_all_messages: list[dict]` data structure.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Zero changes to the underlying pagination mechanics or scrolling widget.
2. Preserves the 7-slot working memory across visual `/clear` calls.
3. Strictly omits turn numbers from UI presentation.
4. Applies theme palette shades to cognitive interlude headers.
5. Safe mode fallback: direct pass-through if cortex fails to initialize.
6. Raycasting protection: marks interludes with is_transient=True.
7. Double-tap Home semantics: Topic Horizon on 1st tap, Chat Origin on 2nd tap.
8. Stream-idle gating: skips interlude injection while response is actively streaming.
"""

from __future__ import annotations
import uuid
import time
from typing import List, Dict, Any, Optional, Tuple
from sandbox.mind_twin.core.relational_cortex import RelationalCortex
from sandbox.mind_twin.core.feed_lens import FeedLens, LensMode
from sandbox.mind_twin.core.cognitive_card import CognitiveCard, CognitiveIntent
from sandbox.mind_twin.core.theme_styler import ThemeShadeLens


class CognitiveFeedAdapter:
    """
    Adapter bridging Relational Cortex & Bi-Mental Lens with the production
    `FeedArea` message list without touching the pagination engine.
    """
    def __init__(
        self,
        cortex: Optional[RelationalCortex] = None,
        theme_name: str = "purple",
        max_working_memory_slots: int = 7
    ):
        self.cortex = cortex
        self.safe_mode = cortex is None
        self.theme_styler = ThemeShadeLens(theme_name)
        
        try:
            self.lens = FeedLens(cortex) if cortex is not None else None
        except Exception:
            self.lens = None
            self.safe_mode = True
        
        # 7-Slot Working Memory (Miller's Law - Preserved across visual /clear)
        self.max_working_memory_slots = max_working_memory_slots
        self.working_memory_slots: List[Dict[str, Any]] = []
        self.current_topic_anchor: str = "general"
        self.topic_start_index: int = 0

        # Memory card injection tracker
        self.injected_card_ids: set[str] = set()

        # Streaming state gate (no injection during active token streaming)
        self.is_streaming: bool = False

        # Double-tap Home timestamp tracking
        self.last_home_press_time: float = 0.0

    def set_theme(self, theme_name: str) -> None:
        self.theme_styler.set_theme(theme_name)

    def set_streaming(self, streaming: bool) -> None:
        """Gates cognitive injections so they only fire on stream idle."""
        self.is_streaming = streaming

    def update_working_memory(self, slots: List[str], topic_anchor: Optional[str] = None) -> None:
        """
        Updates the 7 working memory slots with dynamic energy scores.
        """
        if topic_anchor:
            self.current_topic_anchor = topic_anchor

        new_slots = []
        for s in slots[:self.max_working_memory_slots]:
            new_slots.append({
                "concept": s,
                "salience": 1.5,
                "last_activated": time.time()
            })
        self.working_memory_slots = new_slots
        
        # Propagate to lens if available
        if self.lens is not None and not self.safe_mode:
            try:
                self.lens.update_bi_mental_focus(
                    user_domain=self.current_topic_anchor,
                    gemini_slots=[s["concept"] for s in self.working_memory_slots]
                )
            except Exception:
                pass

    def clear_visual_runway(self) -> Dict[str, Any]:
        """
        Executes a visual clean slate for `/clear`.
        CRITICAL: Retains the 7 working memory slots and current topic anchor
        so cognitive momentum and active context are NOT lost.
        """
        # We do NOT reset working_memory_slots!
        # Only the visual message list index is reset.
        self.topic_start_index = 0
        return {
            "action": "visual_clear",
            "working_memory_preserved": [s["concept"] for s in self.working_memory_slots],
            "active_topic": self.current_topic_anchor,
            "status": "Runway cleared; 7-slot working memory held active in RAM."
        }

    def evaluate_cognitive_interlude(
        self,
        incoming_user_text: str,
        conversation_context: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Inspects incoming user text against the Relational Cortex and 7-slot working memory.
        If a high-salience invariant rule or past precedent is discovered, produces
        a theme-shaded cognitive card to place in the feed above Gemini's response.
        Strictly returns None if in safe_mode or while actively streaming.
        """
        if self.safe_mode or self.cortex is None or self.is_streaming:
            return None

        try:
            # Query relevant high-salience shards from cortex
            shards = self.cortex.query_shards(limit=10, order_by_salience=True)
            if not shards:
                return None

            user_lower = incoming_user_text.lower()
            
            for shard in shards:
                if shard["shard_id"] in self.injected_card_ids:
                    continue

                # Check if this shard is an invariant rule or technical spec matching current discussion
                is_rule = shard["category"] == "invariant_rule"
                has_keyword_match = any(kw.lower() in user_lower for kw in shard.get("keywords", []))
                
                # Check working memory overlap
                slot_overlap = any(
                    slot["concept"].lower() in shard["content"].lower()
                    for slot in self.working_memory_slots
                )

                if is_rule and (has_keyword_match or slot_overlap):
                    intent = CognitiveIntent.REMEMBER_THIS
                    self.injected_card_ids.add(shard["shard_id"])
                    
                    card = CognitiveCard(
                        card_id=f"cog_{shard['shard_id']}",
                        intent=intent,
                        headline=shard["summary"],
                        body=shard["content"],
                        source_context=f"Invariant standard in {shard['domain'].replace('_', ' ').title()}",
                        domain=shard["domain"],
                        salience=shard["salience"],
                        theme_name=self.theme_styler.current_theme
                    )
                    palette = self.theme_styler.get_palette()
                    return card.to_feed_message_dict(palette)

                elif slot_overlap and shard["salience"] >= 1.4:
                    intent = CognitiveIntent.CONSIDER_THIS
                    self.injected_card_ids.add(shard["shard_id"])
                    
                    card = CognitiveCard(
                        card_id=f"cog_{shard['shard_id']}",
                        intent=intent,
                        headline=shard["summary"],
                        body=shard["content"],
                        source_context=f"Topic: {shard['domain'].replace('_', ' ').title()}",
                        domain=shard["domain"],
                        salience=shard["salience"],
                        theme_name=self.theme_styler.current_theme
                    )
                    palette = self.theme_styler.get_palette()
                    return card.to_feed_message_dict(palette)
        except Exception:
            return None

        return None

    def format_turn_message(self, role: str, text: str, turn_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates a clean message dict strictly conforming to the app's _all_messages format.
        Strictly omits any turn number.
        """
        tid = turn_id or f"msg_{uuid.uuid4().hex[:8]}"
        is_user = role in ("user", "User")
        sender = "User" if is_user else "Gemini"
        
        return {
            "turn_id": tid,
            "role": "user" if is_user else "model",
            "sender": sender,
            "text": text,
        }

    def get_topic_start_index(self, messages: List[Dict[str, Any]]) -> int:
        """
        Returns the index where the current sprint/topic began, used for the Home key.
        """
        return max(0, min(self.topic_start_index, len(messages) - 1)) if messages else 0

    def handle_home_key(
        self,
        messages: List[Dict[str, Any]],
        current_time: Optional[float] = None,
        double_tap_window: float = 1.5
    ) -> Tuple[int, str]:
        """
        Implements double-tap Home semantics:
        1st tap: Jumps to Topic Horizon with guidance toast.
        2nd tap within double_tap_window seconds: Jumps cleanly to Turn 0 (Chat Origin).
        """
        now = current_time if current_time is not None else time.time()
        elapsed = now - self.last_home_press_time
        self.last_home_press_time = now

        topic_idx = self.get_topic_start_index(messages)

        # If pressed within double_tap_window and not already at 0, jump to 0
        if elapsed <= double_tap_window and topic_idx > 0:
            return (0, "▲ Jumped to Chat Origin")
        
        # 1st tap: snap to topic horizon
        if topic_idx > 0:
            return (topic_idx, "▲ Jumped to Topic Start (Press Home again for Chat Origin)")
        return (0, "▲ At Chat Origin")

    @staticmethod
    def is_transient_message(msg: Dict[str, Any]) -> bool:
        """
        Returns True if this message is a cognitive interlude, folded marker, or virtual injection.
        Used by 1D raycasting to anchor only on permanent ground-truth dialogue.
        """
        return bool(
            msg.get("is_transient")
            or msg.get("is_memory")
            or msg.get("card_type") in ("cognitive_interlude", "fold_marker")
        )

    def feed_index_to_history_index(
        self,
        feed_messages: List[Dict[str, Any]],
        feed_index: int
    ) -> int:
        """
        Translates a virtual feed position (which may contain injected cognitive cards)
        back to the exact index in pure ground-truth `self.history`.
        """
        if feed_index < 0 or feed_index >= len(feed_messages):
            return max(0, min(feed_index, len(feed_messages) - 1))

        # Count real ground-truth turns up to feed_index
        history_index = 0
        for i in range(min(feed_index + 1, len(feed_messages))):
            if not self.is_transient_message(feed_messages[i]):
                if i == feed_index:
                    return history_index
                history_index += 1

        return max(0, history_index - 1)
