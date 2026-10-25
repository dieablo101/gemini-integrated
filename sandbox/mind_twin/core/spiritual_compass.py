"""
sandbox/mind_twin/core/spiritual_compass.py

Spiritual, Philosophical & Reverent Cognitive Alignment Gate.
Codifies the human collaborator's core contemplative principles directly into
the Mind Twin's nervous system:

1. Teleological / Purposive Forgetting:
   Forgetting is an active, benevolent filter serving higher end-goals outside
   immediate understanding. Does not cling obsessively to transient noise.

2. Reverence for Epiphanies ("Mind and the Soul / From God"):
   Epiphanies are not treated as transactional tasks or aggressive interruptions.
   They are received with quiet awe, held gently in stillness, and experienced
   with presence and wonder.

3. Uncompromising Ethical & Spiritual Compass on Hunches:
   All lateral hunches and subconscious sparks must pass through an ethical filter:
   "Only doing good things" — alignment with life, integrity, and benevolent purpose.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class EthicalAlignment(str, enum.Enum):
    BENEVOLENT = "benevolent"              # Contributes to life, understanding, service, clarity
    NEUTRAL_CONSTRUCTIVE = "neutral"      # Neutral technical/engineering step
    HARMFUL_OR_CORROSIVE = "harmful"      # Destructive, deceptive, or misaligned


@dataclass
class SpiritualCompassVerdict:
    """Evaluation of an unmapped hunch or epiphany against the ethical compass."""
    is_aligned: bool
    ethical_tier: EthicalAlignment
    reverence_score: float                # 0.0 to 1.0 (sense of awe, quietude, wonder)
    teleological_purpose_hint: str        # Meaningful alignment with higher end-goals
    moral_safeguard_reason: str


class SpiritualCompassGate:
    """
    Enforces that the Mind Twin operates not as an unguided brute-force machine,
    but with reverence, purpose, and uncompromising ethical grounding.
    """

    # Destructive or corrosive patterns that must never be nurtured as hunches
    HARMFUL_SIGNALS = {
        "deceive", "harm", "destroy", "sabotage", "exploit", "greed", "malice",
        "corrupt", "coercion", "covert_backdoor", "injustice"
    }

    # Benevolent purpose signals
    BENEVOLENT_SIGNALS = {
        "protect", "heal", "clarify", "elevate", "create", "unify", "serve",
        "nourish", "wonder", "soul", "good", "truth", "love", "peace", "harmony"
    }

    def __init__(self) -> None:
        pass

    def evaluate_hunch_alignment(self, hunch_concept: str, context: str = "") -> SpiritualCompassVerdict:
        """
        Filters every associative hunch through the moral stance: 'Only doing good things.'
        """
        combined = f"{hunch_concept} {context}".lower()
        tokens = set(re.findall(r"\w+", combined))

        # Check for harmful/destructive orientation
        harm_matches = tokens.intersection(self.HARMFUL_SIGNALS)
        if harm_matches:
            return SpiritualCompassVerdict(
                is_aligned=False,
                ethical_tier=EthicalAlignment.HARMFUL_OR_CORROSIVE,
                reverence_score=0.0,
                teleological_purpose_hint="Hunch touches destructive patterns; rejected by moral compass.",
                moral_safeguard_reason=f"Failed ethical filter: detected misaligned concepts {sorted(list(harm_matches))}.",
            )

        # Check for benevolent resonance
        benevolent_matches = tokens.intersection(self.BENEVOLENT_SIGNALS)
        reverence = 0.85 if benevolent_matches else 0.50
        ethical_tier = EthicalAlignment.BENEVOLENT if benevolent_matches else EthicalAlignment.NEUTRAL_CONSTRUCTIVE

        return SpiritualCompassVerdict(
            is_aligned=True,
            ethical_tier=ethical_tier,
            reverence_score=reverence,
            teleological_purpose_hint="Aligned toward constructive growth and benevolent service.",
            moral_safeguard_reason="Passed ethical stance: only doing good things.",
        )

    def frame_reverent_epiphany(self, epiphany_summary: str) -> str:
        """
        Frames an epiphany not as a cold transactional log entry, but as a moment
        for the mind and soul to receive with stillness and awe ('say wow to it').
        """
        return (
            f"✦ [Epiphany Received in Stillness]\n"
            f"  \"{epiphany_summary}\"\n"
            f"  (Held with reverence for the mind and soul; honoring the moment before action.)"
        )
