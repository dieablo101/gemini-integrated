"""
Cognitive Lapse Detection & State Re-Sync Engine.
Handles blackout intervals when the background daemon halts or crashes,
applying lapse temporal decay and reconciling buffered events upon recovery.
"""
import time
import os
import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from sandbox.mind_twin.core.state import CognitiveStateVector, FocusItem
from sandbox.mind_twin.core.hypergraph import Hypergraph

@dataclass
class LapseEvent:
    lapse_id: str
    last_heartbeat: float
    resumed_at: float
    duration_seconds: float
    pre_lapse_turn: int
    missed_events_count: int = 0
    decayed_spotlight_count: int = 0
    restored: bool = False

@dataclass
class BufferedEvent:
    event_id: str
    timestamp: float
    event_type: str  # e.g., 'query', 'file_change', 'sensory_packet'
    payload: Dict[str, Any]

class LapseManager:
    def __init__(self, checkpoint_path: str, decay_alpha: float = 0.05, decay_beta: float = 0.5):
        self.checkpoint_path = checkpoint_path
        self.decay_alpha = decay_alpha
        self.decay_beta = decay_beta
        self.event_buffer: List[BufferedEvent] = []

    def save_checkpoint(self, state: CognitiveStateVector, now: Optional[float] = None) -> str:
        """Atomically saves state checkpoint with heartbeat timestamp."""
        now = now or time.time()
        data = state.to_dict()
        data["last_heartbeat"] = now
        
        tmp_path = f"{self.checkpoint_path}.tmp.{os.getpid()}"
        os.makedirs(os.path.dirname(os.path.abspath(self.checkpoint_path)), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self.checkpoint_path)
        return self.checkpoint_path

    def load_checkpoint(self) -> Optional[Tuple[CognitiveStateVector, float]]:
        """Loads last checkpoint and returns (state, last_heartbeat)."""
        if not os.path.exists(self.checkpoint_path):
            return None
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            last_hb = data.get("last_heartbeat", data.get("timestamp", time.time()))
            state = CognitiveStateVector.from_dict(data)
            return state, last_hb
        except Exception:
            return None

    def buffer_event(self, event_type: str, payload: Dict[str, Any], timestamp: Optional[float] = None) -> BufferedEvent:
        """Buffers events occurring while daemon is dead or rebooting."""
        ev = BufferedEvent(
            event_id=f"buf_{len(self.event_buffer)+1}_{int(time.time()*1000)}",
            timestamp=timestamp or time.time(),
            event_type=event_type,
            payload=payload
        )
        self.event_buffer.append(ev)
        return ev

    def clear_buffer(self) -> List[BufferedEvent]:
        buffered = list(self.event_buffer)
        self.event_buffer.clear()
        return buffered

    def compute_lapse_decay(self, state: CognitiveStateVector, lapse_duration: float) -> CognitiveStateVector:
        """
        Calculates memory decay over the blackout period.
        R(lapse) = (1 + alpha * lapse_duration)^(-beta)
        """
        retention = (1.0 + self.decay_alpha * max(0.0, lapse_duration)) ** (-self.decay_beta)
        new_spotlight = []
        for item in state.focus_spotlight:
            new_energy = item.energy * retention
            # keep items that survive lapse retention threshold (e.g. 0.1)
            if new_energy >= 0.1:
                new_spotlight.append(FocusItem(
                    concept_id=item.concept_id,
                    energy=new_energy,
                    primed_hops=item.primed_hops,
                    last_activated=item.last_activated
                ))
        state.focus_spotlight = new_spotlight
        return state

    def reconcile_post_lapse(
        self,
        now: Optional[float] = None,
        hypergraph: Optional[Hypergraph] = None
    ) -> Tuple[CognitiveStateVector, LapseEvent]:
        """
        Reconciles cognitive state after a daemon lapse:
        1. Reads checkpoint.
        2. Detects lapse duration.
        3. Applies lapse decay.
        4. Reconciles buffered events that queued up during daemon downtime.
        """
        now = now or time.time()
        checkpoint = self.load_checkpoint()
        
        if checkpoint is None:
            state = CognitiveStateVector(
                session_id="recovered_cold_session",
                timestamp=now,
                latent_intent="recovered_from_cold_lapse"
            )
            lapse = LapseEvent(
                lapse_id="cold_boot",
                last_heartbeat=now,
                resumed_at=now,
                duration_seconds=0.0,
                pre_lapse_turn=0,
                restored=True
            )
            return state, lapse

        saved_state, last_hb = checkpoint
        lapse_duration = max(0.0, now - last_hb)
        
        pre_count = len(saved_state.focus_spotlight)
        decayed_state = self.compute_lapse_decay(saved_state, lapse_duration)
        decayed_count = pre_count - len(decayed_state.focus_spotlight)

        # Reconcile buffered events
        missed = self.clear_buffer()
        if missed:
            for ev in missed:
                if ev.event_type == "query":
                    query_text = ev.payload.get("query", "")
                    decayed_state.latent_intent = f"post_lapse_reconcile: {query_text[:30]}"
                    decayed_state.turn_counter += 1

        decayed_state.timestamp = now
        decayed_state.metadata["last_lapse_duration"] = lapse_duration
        decayed_state.metadata["missed_events_replayed"] = len(missed)

        lapse_event = LapseEvent(
            lapse_id=f"lapse_{int(last_hb)}_{int(now)}",
            last_heartbeat=last_hb,
            resumed_at=now,
            duration_seconds=lapse_duration,
            pre_lapse_turn=saved_state.turn_counter,
            missed_events_count=len(missed),
            decayed_spotlight_count=decayed_count,
            restored=True
        )

        return decayed_state, lapse_event
