"""
Continuous Cognitive State Vector.
Represents the hot focus spotlight of the mind, serialized between API calls (<2KB).
"""
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field

@dataclass
class FocusItem:
    concept_id: str
    energy: float
    primed_hops: int
    last_activated: float

@dataclass
class CognitiveStateVector:
    version: int = 1
    session_id: str = "shadow_session"
    timestamp: float = field(default_factory=time.time)
    latent_intent: str = "idle"
    focus_spotlight: List[FocusItem] = field(default_factory=list)
    causal_invariants: List[str] = field(default_factory=list)
    turn_counter: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveStateVector":
        if not isinstance(data, dict):
            return cls(session_id="recovered_cold_session")

        focus_items = []
        raw_spotlight = data.get("focus_spotlight", [])
        if isinstance(raw_spotlight, list):
            for item in raw_spotlight:
                if isinstance(item, dict):
                    try:
                        cid = str(item.get("concept_id", "unknown"))
                        energy = float(item.get("energy", 0.5))
                        primed_hops = int(item.get("primed_hops", 0))
                        last_act = float(item.get("last_activated", time.time()))
                        focus_items.append(FocusItem(cid, energy, primed_hops, last_act))
                    except Exception:
                        pass
                elif isinstance(item, FocusItem):
                    focus_items.append(item)

        raw_invariants = data.get("causal_invariants", [])
        invariants = [str(x) for x in raw_invariants] if isinstance(raw_invariants, list) else []

        raw_meta = data.get("metadata", {})
        meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}

        return cls(
            version=int(data.get("version", 1)),
            session_id=str(data.get("session_id", "shadow_session")),
            timestamp=float(data.get("timestamp", time.time())),
            latent_intent=str(data.get("latent_intent", "idle")),
            focus_spotlight=focus_items,
            causal_invariants=invariants,
            turn_counter=int(data.get("turn_counter", 0)),
            metadata=meta,
        )

    def get_summary_frame(self) -> str:
        """Returns a dense working memory prompt injection frame (<200 tokens)."""
        if not self.focus_spotlight:
            return "[COGNITIVE STATE: COLD / IDLE]"
        
        top_focus = sorted(self.focus_spotlight, key=lambda x: x.energy, reverse=True)[:5]
        items_str = ", ".join([f"{item.concept_id} (e={item.energy:.2f})" for item in top_focus])
        invariants_str = "; ".join(self.causal_invariants[:3]) if self.causal_invariants else "None"
        
        return (
            f"[WARM WORKING MEMORY (Turn {self.turn_counter})]\n"
            f"• Residual Spotlight: {items_str}\n"
            f"• Latent Intent: {self.latent_intent}\n"
            f"• Causal Invariants: {invariants_str}"
        )
