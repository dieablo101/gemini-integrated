"""
cognitive_card.py - Theme-aware Cognitive Recall Interludes.

Defines the structure and badges for Gemini cognitive inputs that appear
in the chat feed relational to the current topic and bi-mental state.
Strictly does NOT display turn numbers—only who is speaking and cognitive intent.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class CognitiveIntent(str, Enum):
    REMEMBER_THIS = "remember_this"           # Critical invariant rules & security specs
    CONSIDER_THIS = "consider_this"           # Trade-offs, alternative approaches, design tips
    JUST_A_THOUGHT = "just_a_thought"         # Creative ideas, lateral connections, epiphanies
    PAST_PRECEDENT = "past_precedent"         # Solutions to errors or patterns solved previously
    ANCHORED_DECISION = "anchored_decision"   # Core architectural roadmaps & agreed baselines


COGNITIVE_BADGES = {
    CognitiveIntent.REMEMBER_THIS: ("🧠 Gemini • Remember this!", "accent_bright"),
    CognitiveIntent.CONSIDER_THIS: ("💡 Gemini • Something to consider", "accent"),
    CognitiveIntent.JUST_A_THOUGHT: ("💭 Gemini • Just a thought...", "accent_dim"),
    CognitiveIntent.PAST_PRECEDENT: ("⚡ Gemini • Past Precedent", "accent"),
    CognitiveIntent.ANCHORED_DECISION: ("⚓ Gemini • Anchored Decision", "accent_bright"),
}


@dataclass
class CognitiveCard:
    card_id: str
    intent: CognitiveIntent
    headline: str
    body: str
    source_context: str            # e.g., "From Blender Handedness discussion" (never turn numbers!)
    domain: str
    salience: float = 1.0
    theme_name: str = "purple"

    def get_badge(self) -> str:
        label, _ = COGNITIVE_BADGES.get(self.intent, ("Gemini", "accent"))
        return label

    def get_theme_shade_key(self) -> str:
        _, shade_key = COGNITIVE_BADGES.get(self.intent, ("Gemini", "accent"))
        return shade_key

    def to_feed_message_dict(self, theme_palette: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Translates this cognitive interlude into a standard message dict that feeds
        directly into the app's existing pagination engine (`_all_messages: list[dict]`).
        No underlying pagination container code needs to change.
        """
        badge = self.get_badge()
        shade_key = self.get_theme_shade_key()
        color_hex = theme_palette.get(shade_key, "#bb55ff") if theme_palette else "#bb55ff"

        # Format markdown body cleanly with context note
        formatted_markdown = (
            f"**{self.headline}**\n\n"
            f"{self.body}\n\n"
            f"> *Context: {self.source_context}*"
        )

        return {
            "turn_id": self.card_id,
            "role": "model",
            "sender": badge,
            "badge": badge,
            "card_type": "cognitive_interlude",
            "intent": self.intent.value,
            "theme_shade": shade_key,
            "accent_hex": color_hex,
            "text": formatted_markdown,
            "is_memory": True,
            "is_transient": True,
            "can_fork": False
        }
