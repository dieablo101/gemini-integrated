"""
sandbox/mind_twin/core/subconscious/seed_packet.py

Data structures for Conscious Drop seeds and multi-plane observation vectors.
Enables asynchronous, zero-latency conscious exit hatches for unresolved tensions.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ObservationVector:
    """
    An environmental, behavioral, or relational observation fiber attached to a seed.
    Planes:
      - behavioral: typing cadence, idle duration, rhythm, flow state
      - artifact: code structure, socket protocol, game engine architecture
      - relational: user intent, values, aesthetic humor, autonomy stance
      - sensory: mobile node sensors (lux, gyro, location context)
    """
    vector_id: str
    plane: str
    label: str
    data: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vector_id": self.vector_id,
            "plane": self.plane,
            "label": self.label,
            "data": self.data,
            "weight": round(self.weight, 3),
            "timestamp": self.timestamp,
        }


@dataclass
class SeedPacket:
    """
    An unresolved thought or tension knot dropped from the conscious mind.
    Undergoes multi-vector accretion in the hearth, passes through collision lenses
    and resonance gates, and rests in latent soil if unannealed.
    """
    seed_id: str
    raw_thought: str
    conscious_context: str = ""
    domain_hints: List[str] = field(default_factory=list)
    status: str = "dropped"  # "dropped", "incubating", "ignited", "dormant", "discarded"
    created_at: float = field(default_factory=time.time)
    vectors: List[ObservationVector] = field(default_factory=list)
    attempts: int = 0
    last_attempt_at: Optional[float] = None
    dormant_at: Optional[float] = None
    ignited_at: Optional[float] = None
    failure_reasons: List[str] = field(default_factory=list)
    saliency_score: float = 0.5
    last_hypothesis: str = ""

    @classmethod
    def create(
        cls,
        raw_thought: str,
        conscious_context: str = "",
        domain_hints: Optional[List[str]] = None,
        seed_id: Optional[str] = None,
    ) -> SeedPacket:
        sid = seed_id or f"seed_{uuid.uuid4().hex[:8]}"
        return cls(
            seed_id=sid,
            raw_thought=raw_thought,
            conscious_context=conscious_context,
            domain_hints=domain_hints or [],
            status="dropped",
            created_at=time.time(),
        )

    def attach_vector(self, vector: ObservationVector) -> None:
        """Attaches an observation vector fiber to this seed."""
        self.vectors.append(vector)

    def get_planes(self) -> List[str]:
        """Returns the distinct planes covered by attached vectors."""
        return list({v.plane for v in self.vectors})

    def get_vectors_for_plane(self, plane: str) -> List[ObservationVector]:
        """Returns all observation vectors belonging to the specified plane."""
        return [v for v in self.vectors if v.plane == plane]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed_id": self.seed_id,
            "raw_thought": self.raw_thought,
            "conscious_context": self.conscious_context,
            "domain_hints": self.domain_hints,
            "status": self.status,
            "created_at": self.created_at,
            "vectors": [v.to_dict() for v in self.vectors],
            "attempts": self.attempts,
            "last_attempt_at": self.last_attempt_at,
            "dormant_at": self.dormant_at,
            "ignited_at": self.ignited_at,
            "failure_reasons": self.failure_reasons,
            "saliency_score": round(self.saliency_score, 3),
            "last_hypothesis": self.last_hypothesis,
        }
