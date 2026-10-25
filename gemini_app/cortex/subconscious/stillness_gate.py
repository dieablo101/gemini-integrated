"""
sandbox/mind_twin/core/subconscious/stillness_gate.py

Stillness Gate & Cognitive Receptivity Evaluator.
Guarantees that epiphanies never interrupt deep flow states or active debugging.
Surfaces insights strictly during receptive cognitive stillness windows:
  - Terminal idle pause (> 45s post-task)
  - Post-commit milestone pauses
  - Dawn boot rehydration
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ReceptivityStatus:
    """The outcome of a receptivity check."""
    is_receptive: bool
    trigger_type: str  # "stillness_pause", "post_commit", "dawn_boot", "active_flow_locked", "busy_transient"
    idle_seconds: float
    reason: str


class StillnessGate:
    """
    Cognitive stillness gate.
    Protects user concentration and enforces emergence only in authentic pauses.
    """

    def __init__(
        self,
        idle_threshold_seconds: float = 45.0,
    ) -> None:
        self.idle_threshold_seconds = idle_threshold_seconds
        self.last_user_activity: float = time.time()
        self.is_executing: bool = False
        self.is_typing: bool = False

    def record_activity(self, activity_type: str = "keystroke") -> None:
        """Records active user engagement."""
        self.last_user_activity = time.time()
        if activity_type == "keystroke":
            self.is_typing = True

    def set_execution_state(self, running: bool) -> None:
        """Sets whether a terminal shell command, compile, or test is running."""
        self.is_executing = running
        if running:
            self.last_user_activity = time.time()

    def evaluate_receptivity(
        self,
        event_marker: Optional[str] = None,
        t_now: Optional[float] = None,
        override_idle_seconds: Optional[float] = None,
    ) -> ReceptivityStatus:
        """
        Determines whether the conscious space is quiet and ready to receive an epiphany.
        """
        now = t_now or time.time()
        idle_sec = override_idle_seconds if override_idle_seconds is not None else (now - self.last_user_activity)

        # 1. Flow lock: never interrupt active compilation or active execution
        if self.is_executing:
            return ReceptivityStatus(
                is_receptive=False,
                trigger_type="active_flow_locked",
                idle_seconds=idle_sec,
                reason="Terminal command / compile execution in progress.",
            )

        # 2. Dawn boot / morning awakening
        if event_marker == "dawn_boot":
            return ReceptivityStatus(
                is_receptive=True,
                trigger_type="dawn_boot",
                idle_seconds=idle_sec,
                reason="Dawn boot greeting: quiet morning rehydration window open.",
            )

        # 3. Post-commit milestone reflection
        if event_marker == "post_commit":
            return ReceptivityStatus(
                is_receptive=True,
                trigger_type="post_commit",
                idle_seconds=idle_sec,
                reason="Post-commit milestone: natural cognitive punctuation mark.",
            )

        # 4. Cognitive stillness threshold
        if idle_sec >= self.idle_threshold_seconds:
            return ReceptivityStatus(
                is_receptive=True,
                trigger_type="stillness_pause",
                idle_seconds=idle_sec,
                reason=f"Terminal idle pause of {idle_sec:.1f}s exceeded threshold ({self.idle_threshold_seconds:.1f}s).",
            )

        # 5. Default busy
        return ReceptivityStatus(
            is_receptive=False,
            trigger_type="busy_transient",
            idle_seconds=idle_sec,
            reason=f"User active {idle_sec:.1f}s ago; waiting for stillness threshold ({self.idle_threshold_seconds:.1f}s).",
        )
