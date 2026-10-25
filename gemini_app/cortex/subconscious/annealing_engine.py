"""
sandbox/mind_twin/core/subconscious/annealing_engine.py

Annealing & Perturbation Engine.
Governs miss-handling, vector perturbation, cooling schedules, and dormancy transitions:
  - Type 1 (Sterile Miss): Kill immediately; discard unfertile knot.
  - Type 2 (Muddled Miss): Micro-shift; rotate one companion vector and retry.
  - Type 3 (Premature Miss): Macro-pivot or cool down; put into incubation backoff.
  - Max 3 Attempts: Transitions seed to LatentSoilVault, saving CPU and awaiting external catalyst.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from gemini_app.cortex.subconscious.accretion_hearth import AccretionHearth, LatentSoilVault
from gemini_app.cortex.subconscious.resonance_gate import ResonanceResult
from gemini_app.cortex.subconscious.seed_packet import ObservationVector, SeedPacket


@dataclass
class AnnealingDecision:
    """The next step prescribed by the annealing engine after an attempt."""
    action: str  # "ignite", "discard", "perturb_micro", "pivot_macro", "dormant_soil"
    seed_id: str
    attempt_number: int
    reason: str
    perturbed_vector: Optional[ObservationVector] = None
    cooldown_seconds: float = 0.0


class AnnealingEngine:
    """
    Thermodynamic annealing and retry governor for subconscious incubation.
    """

    def __init__(
        self,
        hearth: AccretionHearth,
        max_attempts: int = 3,
        base_backoff_seconds: float = 300.0,  # 5 minutes in prod (testable via overrides)
    ) -> None:
        self.hearth = hearth
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds

    def handle_attempt_result(
        self,
        seed: SeedPacket,
        resonance: ResonanceResult,
        t_now: Optional[float] = None,
    ) -> AnnealingDecision:
        """
        Evaluates the attempt resonance and dictates the thermodynamic next step.
        """
        now = t_now or time.time()
        seed.attempts += 1
        seed.last_attempt_at = now

        # Case 0: Breakthrough passed!
        if resonance.passed:
            seed.status = "ignited"
            seed.ignited_at = now
            return AnnealingDecision(
                action="ignite",
                seed_id=seed.seed_id,
                attempt_number=seed.attempts,
                reason="Candidate passed all 3 resonance gates.",
            )

        # Record failure reason
        seed.failure_reasons.append(f"Attempt {seed.attempts}: {resonance.feedback}")

        # Case 1: Sterile Miss -> Discard immediately (zero mystery)
        if resonance.miss_type == "sterile":
            seed.status = "discarded"
            # Remove from hearth
            with self.hearth._lock:
                self.hearth._hearth.pop(seed.seed_id, None)
            return AnnealingDecision(
                action="discard",
                seed_id=seed.seed_id,
                attempt_number=seed.attempts,
                reason="Sterile miss: trivial or non-fertile knot. Discarded immediately.",
            )

        # Check maximum retry exhaustion
        if seed.attempts >= self.max_attempts:
            # Transfer to Latent Soil Vault
            self.hearth.move_to_soil(seed.seed_id)
            return AnnealingDecision(
                action="dormant_soil",
                seed_id=seed.seed_id,
                attempt_number=seed.attempts,
                reason=f"Exhausted {self.max_attempts} attempts without resonance. Moved to latent soil.",
            )

        # Case 2: Muddled Miss -> Micro-shift (perturb one vector)
        if resonance.miss_type == "muddled":
            new_vec = self._perturb_one_vector(seed, now)
            backoff = self.base_backoff_seconds * (seed.attempts)
            return AnnealingDecision(
                action="perturb_micro",
                seed_id=seed.seed_id,
                attempt_number=seed.attempts,
                reason="Muddled miss: rotated one companion vector to reduce cognitive noise.",
                perturbed_vector=new_vec,
                cooldown_seconds=backoff,
            )

        # Case 3: Premature Miss -> Macro-pivot or cooldown
        backoff = self.base_backoff_seconds * (seed.attempts * 1.5)
        return AnnealingDecision(
            action="pivot_macro",
            seed_id=seed.seed_id,
            attempt_number=seed.attempts,
            reason="Premature miss: idea needs more real-world mass. Incubation cooled down.",
            cooldown_seconds=backoff,
        )

    def _perturb_one_vector(self, seed: SeedPacket, now: float) -> ObservationVector:
        """
        Micro-shift perturbation: rotates the lens by swapping out the weakest vector
        for an alternative perspective (e.g. cadence or relational stance).
        """
        if seed.vectors:
            # Drop lowest weight or oldest vector
            weakest_idx = min(range(len(seed.vectors)), key=lambda i: seed.vectors[i].weight)
            dropped = seed.vectors.pop(weakest_idx)

        # Introduce an orthogonal companion vector
        alt_planes = ["relational", "behavioral", "artifact", "sensory"]
        used_planes = seed.get_planes()
        candidate_planes = [p for p in alt_planes if p not in used_planes]
        chosen_plane = candidate_planes[0] if candidate_planes else "relational"

        new_vec = ObservationVector(
            vector_id=f"vec_perturb_{uuid.uuid4().hex[:6]}",
            plane=chosen_plane,
            label=f"Perturbed Lens {chosen_plane.capitalize()} Anchor",
            data={"perturbed": True, "parent_seed": seed.seed_id},
            weight=1.0,
            timestamp=now,
        )
        seed.attach_vector(new_vec)
        return new_vec
