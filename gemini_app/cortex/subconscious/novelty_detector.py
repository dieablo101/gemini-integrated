"""
sandbox/mind_twin/core/subconscious/novelty_detector.py

Novelty & Out-of-the-Norm Detector.
Enforces the constraint: Subconscious incubation ONLY fires when working on
something out of the norm or new (unsolved architectural paradoxes, new domain collisions).
Routine maintenance, diagnostics, and familiar tasks keep the subconscious dormant.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class NoveltyEvaluation:
    """The result of the novelty gating filter."""
    novelty_score: float
    is_out_of_the_norm: bool
    should_fire_incubation: bool
    reason: str
    unfamiliar_anchors: List[str] = field(default_factory=list)
    familiarity_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novelty_score": round(self.novelty_score, 3),
            "is_out_of_the_norm": self.is_out_of_the_norm,
            "should_fire_incubation": self.should_fire_incubation,
            "reason": self.reason,
            "unfamiliar_anchors": self.unfamiliar_anchors,
            "familiarity_confidence": round(self.familiarity_confidence, 3),
        }


class NoveltyDetector:
    """
    Evaluates whether an incoming task or conversational topic is 'out of the norm' / 'new'.
    Maintains a lexicon of established familiar operational patterns.
    """

    DEFAULT_ROUTINE_PATTERNS: Set[str] = {
        # Dev & Ops routines
        "git", "commit", "push", "status", "test", "unittest", "pytest",
        "lint", "format", "reboot", "restart", "inspect", "compile",
        "check", "build", "run", "log", "cleanup", "diagnose", "diff",
        "patch", "file", "read", "write", "search", "grep", "shell",
        # Standard administrative dialogue
        "hello", "hi", "thanks", "ok", "yes", "no", "sure", "clear",
    }

    def __init__(
        self,
        novelty_threshold: float = 0.65,
        familiar_lexicon: Optional[Set[str]] = None,
    ) -> None:
        self.novelty_threshold = novelty_threshold
        self.familiar_lexicon = set(familiar_lexicon) if familiar_lexicon else set(self.DEFAULT_ROUTINE_PATTERNS)
        self.domain_history: Dict[str, int] = {}

    def register_familiar_terms(self, terms: List[str]) -> None:
        """Expands the baseline of known familiar concepts."""
        for t in terms:
            words = re.findall(r"\w{3,}", t.lower())
            self.familiar_lexicon.update(words)

    def register_domain_experience(self, domain: str) -> None:
        """Records experience in a domain to lower future surprise/novelty."""
        dom = domain.strip().lower()
        self.domain_history[dom] = self.domain_history.get(dom, 0) + 1

    def evaluate(
        self,
        task_prompt: str,
        active_topic: str = "",
        context_keywords: Optional[List[str]] = None,
    ) -> NoveltyEvaluation:
        """
        Calculates novelty score in [0.0, 1.0].
        If novelty >= novelty_threshold, triggers subconscious background crunching.
        """
        combined_text = f"{task_prompt} {active_topic}".lower()
        if context_keywords:
            combined_text += " " + " ".join(context_keywords).lower()

        tokens = re.findall(r"[a-z]{3,}", combined_text)
        if not tokens:
            return NoveltyEvaluation(
                novelty_score=0.0,
                is_out_of_the_norm=False,
                should_fire_incubation=False,
                reason="Empty or non-alphabetic task prompt (dormant).",
            )

        unique_tokens = set(tokens)
        familiar_count = 0
        novel_tokens: List[str] = []

        for token in unique_tokens:
            if token in self.familiar_lexicon:
                familiar_count += 1
            else:
                novel_tokens.append(token)

        total_unique = len(unique_tokens)
        familiarity_ratio = familiar_count / total_unique
        raw_novelty = 1.0 - familiarity_ratio

        # Cross-domain collision bonus:
        # If words bridge two historically distinct domains (e.g. 'blender' + 'gyro' / 'pns' + 'godot')
        domain_entropy = 0.0
        creative_bridge_markers = {
            "somatic", "subconscious", "apophenia", "epiphany", "neural",
            "blender", "godot", "shader", "armature", "rigging", "fluid",
            "telemetry", "accelerometer", "photodiode", "satellite", "p2p",
            "simulation", "procedural", "synthetic", "dopamine", "hebbian",
        }
        creative_matches = unique_tokens.intersection(creative_bridge_markers)
        if len(creative_matches) >= 2:
            domain_entropy = min(0.35, 0.12 * len(creative_matches))

        final_novelty = min(1.0, raw_novelty * 0.7 + domain_entropy)

        # Experience dampening: if we have worked in this exact domain repeatedly, dampen novelty
        topic_key = active_topic.strip().lower()
        exp = self.domain_history.get(topic_key, 0)
        if exp > 5:
            dampening = min(0.25, 0.05 * math.log(exp))
            final_novelty = max(0.0, final_novelty - dampening)

        is_novel = final_novelty >= self.novelty_threshold

        if is_novel:
            reason = (
                f"Out of the norm detected (novelty={final_novelty:.2f} >= {self.novelty_threshold:.2f}). "
                f"Contains {len(novel_tokens)} unfamiliar terms & cross-domain bridge markers: {novel_tokens[:4]}."
            )
        else:
            reason = (
                f"Routine familiar task (novelty={final_novelty:.2f} < {self.novelty_threshold:.2f}). "
                f"Lexicon familiarity={familiarity_ratio:.2f}. Subconscious engine stays dormant."
            )

        return NoveltyEvaluation(
            novelty_score=final_novelty,
            is_out_of_the_norm=is_novel,
            should_fire_incubation=is_novel,
            reason=reason,
            unfamiliar_anchors=novel_tokens[:6],
            familiarity_confidence=familiarity_ratio,
        )
