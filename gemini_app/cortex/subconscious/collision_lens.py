"""
sandbox/mind_twin/core/subconscious/collision_lens.py

Invariant Collision Lens.
Constructs multi-plane projection matrices across Behavioral, Artifact, and Relational domains.
Enforces anti-spoiler constraints: extracts the single unstated invariant that explains
why distinct planes co-exist, forbidding clichés and sterile summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from gemini_app.cortex.subconscious.seed_packet import ObservationVector, SeedPacket


@dataclass
class CollisionMatrix:
    """The projected multi-plane collision space for a seed."""
    seed_id: str
    behavioral_plane: List[ObservationVector]
    artifact_plane: List[ObservationVector]
    relational_plane: List[ObservationVector]
    sensory_plane: List[ObservationVector]
    anti_spoiler_prompt: str
    planes_collided: List[str]


class CollisionLens:
    """
    Collision Lens engine:
    - Sorts observation vectors into planes.
    - Ensures multi-plane orthogonality.
    - Formulates the anti-spoiler invariant prompt for the subconscious synthesizer.
    """

    def __init__(self, temperature: float = 0.7) -> None:
        self.temperature = temperature

    def project(self, seed: SeedPacket) -> CollisionMatrix:
        """
        Projects seed vectors across planes and generates an anti-spoiler collision matrix.
        """
        behavioral: List[ObservationVector] = []
        artifact: List[ObservationVector] = []
        relational: List[ObservationVector] = []
        sensory: List[ObservationVector] = []

        for v in seed.vectors:
            p = v.plane.lower()
            if p == "behavioral":
                behavioral.append(v)
            elif p in ("artifact", "code", "architecture"):
                artifact.append(v)
            elif p in ("relational", "values", "intent"):
                relational.append(v)
            elif p in ("sensory", "telemetry"):
                sensory.append(v)
            else:
                relational.append(v)

        planes_collided = []
        if behavioral:
            planes_collided.append("behavioral")
        if artifact:
            planes_collided.append("artifact")
        if relational:
            planes_collided.append("relational")
        if sensory:
            planes_collided.append("sensory")

        prompt = self._build_anti_spoiler_prompt(
            raw_thought=seed.raw_thought,
            behavioral=behavioral,
            artifact=artifact,
            relational=relational,
            sensory=sensory,
            domain_hints=seed.domain_hints,
        )

        return CollisionMatrix(
            seed_id=seed.seed_id,
            behavioral_plane=behavioral,
            artifact_plane=artifact,
            relational_plane=relational,
            sensory_plane=sensory,
            anti_spoiler_prompt=prompt,
            planes_collided=planes_collided,
        )

    def _build_anti_spoiler_prompt(
        self,
        raw_thought: str,
        behavioral: List[ObservationVector],
        artifact: List[ObservationVector],
        relational: List[ObservationVector],
        sensory: List[ObservationVector],
        domain_hints: List[str],
    ) -> str:
        """
        Strictly forbids summaries, obvious restatements, or pre-chewed explanations.
        Forces the synthesis to produce the unstated unifying invariant.
        """
        lines = [
            "### SUBCONSCIOUS INVARIANT COLLISION LENS ###",
            f"Tension Knot: {raw_thought}",
        ]

        if domain_hints:
            lines.append(f"Domain Hints: {', '.join(domain_hints)}")

        if behavioral:
            items = "; ".join(f"{b.label} ({b.data})" for b in behavioral)
            lines.append(f"Plane 1 [Somatic/Behavioral]: {items}")

        if artifact:
            items = "; ".join(f"{a.label} ({a.data})" for a in artifact)
            lines.append(f"Plane 2 [Technical Artifact]: {items}")

        if relational:
            items = "; ".join(f"{r.label} ({r.data})" for r in relational)
            lines.append(f"Plane 3 [Relational/Intent]: {items}")

        if sensory:
            items = "; ".join(f"{s.label} ({s.data})" for s in sensory)
            lines.append(f"Plane 4 [Sensory Environment]: {items}")

        lines.extend([
            "",
            "STRICT COGNITIVE CONSTRAINTS:",
            "1. Do NOT summarize the inputs. Do NOT state the obvious.",
            "2. Identify the single unstated invariant that explains WHY these disparate planes exist in this exact configuration.",
            "3. Compress the resolution into a single high-density invariant sentence followed by 1 actionable mechanism.",
        ])

        return "\n".join(lines)
