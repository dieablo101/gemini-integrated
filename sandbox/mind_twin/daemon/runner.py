"""
Continuous Mind Daemon Runner.
Simulates a zero-overhead local autonomic timekeeper that runs in the background.
"""
import time
import json
from pathlib import Path
from typing import Optional
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.state import CognitiveStateVector

class MindDaemon:
    def __init__(self, state_file_path: str, hypergraph: Hypergraph, tick_interval: float = 1.0):
        self.state_file_path = Path(state_file_path)
        self.hypergraph = hypergraph
        self.tick_interval = tick_interval
        self._running = False

    def load_state(self) -> Optional[CognitiveStateVector]:
        if not self.state_file_path.exists():
            return None
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return CognitiveStateVector.from_dict(data)
        except Exception:
            return None

    def save_state(self, state: CognitiveStateVector):
        self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file_path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)

    def tick_once(self, now: Optional[float] = None) -> Optional[CognitiveStateVector]:
        """Runs a single autonomic maintenance pulse."""
        state = self.load_state()
        if not state:
            return None

        now = now or time.time()
        delta_t = now - state.timestamp
        if delta_t <= 0:
            return state

        # Continuous Ebbinghaus decay on active spotlight
        alpha = self.hypergraph.decay_alpha
        beta = self.hypergraph.decay_beta
        retention = (1.0 + alpha * delta_t) ** (-beta)

        decayed = []
        for item in state.focus_spotlight:
            new_energy = item.energy * retention
            if new_energy >= 0.1:  # Floor cutoff for active consciousness
                item.energy = new_energy
                decayed.append(item)

        state.focus_spotlight = decayed
        state.timestamp = now
        self.save_state(state)
        return state
