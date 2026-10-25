"""
Prism Router & Somatic-to-UpperMind Collapser
=============================================
Fuses the 7 active somatic sensory slots (Miller working memory: cursor CoG, voice,
terminal stdout, typing state, topic anchor, temporal anchor, git diff) into a single
focal CognitiveIntentFrame in < 2ms, and routes deterministically between:
  1. ROUTE_SOMATIC_LOCAL: Instant reflex (< 2ms, zero network, zero tokens)
  2. ROUTE_FIREBASE_UPPERMIND: State/Presence sync (zero tokens, async cloud transport)
  3. ROUTE_API_UPPERMIND: Generative synthesis & deep reasoning (LLM token call)

Strictly sandbox-only implementation.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
import time
from typing import Any, Dict, List, Optional


class RoutingTier(Enum):
    SOMATIC_LOCAL = "somatic_local"
    FIREBASE_UPPERMIND = "firebase_uppermind"
    API_UPPERMIND = "api_uppermind"


class SomaticInterrupt(Enum):
    NONE = "none"
    HALT = "halt"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass
class CursorCoG:
    """Slot 1: The 'Index Finger' / Center of Gravity in code/editor."""
    file_path: str = ""
    line_number: int = 0
    symbol_under_cursor: str = ""
    selected_text: str = ""
    enclosing_function: str = ""


@dataclass
class VoiceStreamSlot:
    """Slot 2: Continuous audio / spoken stream fragment."""
    utterance: str = ""
    is_speaking: bool = False
    pause_duration_ms: float = 0.0
    confidence: float = 1.0
    detected_interrupt: SomaticInterrupt = SomaticInterrupt.NONE


@dataclass
class TerminalExecSlot:
    """Slot 3: Last terminal command output or compiler/test state."""
    command: str = ""
    exit_code: int = 0
    stdout_tail: str = ""
    stderr_tail: str = ""
    test_failures_count: int = 0


@dataclass
class TypingStateSlot:
    """Slot 4: Editor/Prompt typing status & cadence."""
    buffer_length: int = 0
    is_typing: bool = False
    idle_ms: float = 0.0
    submitted: bool = False  # Enter was pressed


@dataclass
class TopicAnchorSlot:
    """Slot 5: Active knowledge / notes topic anchor."""
    topic_name: str = ""
    notes_count: int = 0
    revisit_queue_count: int = 0
    is_dirty: bool = False  # Local note added/modified awaiting sync


@dataclass
class TemporalAnchorSlot:
    """Slot 6: Turn lineage momentum & temporal anchoring."""
    turn_id: str = ""
    turn_number: int = 0
    momentum_score: float = 1.0


@dataclass
class WorkspaceDeltaSlot:
    """Slot 7: File tree diff and git staged/unstaged changes."""
    modified_files: List[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    is_dirty: bool = False


@dataclass
class SomaticSensoryTracks:
    """The 7 working sensory tracks feeding into the Prism Collapser."""
    cursor: CursorCoG = field(default_factory=CursorCoG)
    voice: VoiceStreamSlot = field(default_factory=VoiceStreamSlot)
    terminal: TerminalExecSlot = field(default_factory=TerminalExecSlot)
    typing: TypingStateSlot = field(default_factory=TypingStateSlot)
    topic: TopicAnchorSlot = field(default_factory=TopicAnchorSlot)
    temporal: TemporalAnchorSlot = field(default_factory=TemporalAnchorSlot)
    workspace: WorkspaceDeltaSlot = field(default_factory=WorkspaceDeltaSlot)


@dataclass
class DeicticAnchor:
    """De-referenced anchor for spoken pronouns ('this', 'that', 'here')."""
    raw_reference: str
    target_kind: str  # 'code_symbol', 'file_line', 'terminal_error', 'none'
    resolved_value: str


@dataclass
class CognitiveIntentFrame:
    """The '7 into 1' synthesized focal frame."""
    focal_summary: str
    dominant_modality: str  # 'voice', 'typing', 'spatial', 'execution'
    deictic_anchors: List[DeicticAnchor] = field(default_factory=list)
    actionable_intent: bool = False
    intent_category: str = "ambient"  # 'ambient', 'interrupt', 'state_sync', 'query', 'triage', 'code_gen'
    routing_tier: RoutingTier = RoutingTier.SOMATIC_LOCAL
    somatic_latency_ms: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)


class BilateralPrismRouter:
    """
    7-into-1 Somatic Collapser and Bilateral Routing Gate.
    Maintains sub-2ms budget and enforces clean separation between
    Local Somatics, Firebase State Sync, and API Upper Mind reasoning.
    """

    # Multi-word patterns first so greedy regex captures 'this function'/'this error' before bare 'this'
    DEICTIC_PATTERN = re.compile(
        r"\b(?:this\s+(?:function|method|class|variable|line|error|failure|exception|traceback)|that\s+(?:function|method|error|failure)|this|that|here)\b",
        re.IGNORECASE
    )
    INTERRUPT_WORDS = {
        "stop": SomaticInterrupt.HALT,
        "halt": SomaticInterrupt.HALT,
        "cancel": SomaticInterrupt.HALT,
        "kill": SomaticInterrupt.HALT,
        "wait": SomaticInterrupt.PAUSE,
        "hold on": SomaticInterrupt.PAUSE,
        "pause": SomaticInterrupt.PAUSE,
        "resume": SomaticInterrupt.RESUME,
        "continue": SomaticInterrupt.RESUME,
    }

    def __init__(self, speech_pause_threshold_ms: float = 500.0):
        self.speech_pause_threshold_ms = speech_pause_threshold_ms
        self.history_frames: List[CognitiveIntentFrame] = []

    def collapse_and_route(self, tracks: SomaticSensoryTracks) -> CognitiveIntentFrame:
        """
        Collapses the 7 sensory tracks into 1 focal frame and resolves routing tier.
        Guaranteed to execute in < 2ms without external network I/O.
        """
        start_t = time.perf_counter()

        # Step 1: Detect immediate voice reflexes / interrupts
        voice_interrupt = self._evaluate_voice_interrupt(tracks.voice)
        if voice_interrupt != SomaticInterrupt.NONE:
            tracks.voice.detected_interrupt = voice_interrupt

        # Step 2: Resolve Deictic 'Index Finger' Grounding
        deictic_anchors = self._resolve_deictic_anchors(tracks)

        # Step 3: Determine Dominant Modality & Actionable Intent
        dominant_modality, category, actionable = self._classify_intent(tracks)

        # Step 4: Routing Decision Gate (The 3-Tier Policy)
        routing_tier = self._decide_routing(tracks, category, actionable)

        # Step 5: Synthesize 7-into-1 Focal Summary
        focal_summary = self._synthesize_focal_summary(tracks, category, deictic_anchors)

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0

        frame = CognitiveIntentFrame(
            focal_summary=focal_summary,
            dominant_modality=dominant_modality,
            deictic_anchors=deictic_anchors,
            actionable_intent=actionable,
            intent_category=category,
            routing_tier=routing_tier,
            somatic_latency_ms=elapsed_ms,
            payload={
                "cursor_file": tracks.cursor.file_path,
                "cursor_line": tracks.cursor.line_number,
                "terminal_exit": tracks.terminal.exit_code,
                "voice_transcript": tracks.voice.utterance,
                "active_topic": tracks.topic.topic_name,
                "interrupt": tracks.voice.detected_interrupt.value,
            }
        )

        self.history_frames.append(frame)
        if len(self.history_frames) > 50:
            self.history_frames.pop(0)

        return frame

    def _evaluate_voice_interrupt(self, voice: VoiceStreamSlot) -> SomaticInterrupt:
        if not voice.utterance:
            return SomaticInterrupt.NONE
        # Clean punctuation for robust matching
        clean = re.sub(r"[^\w\s]", "", voice.utterance.strip().lower())
        words = clean.split()
        for token, action in self.INTERRUPT_WORDS.items():
            if token in clean:
                # Direct word or phrase match
                if token == clean or token in words or (" " in token and token in clean):
                    return action
        return SomaticInterrupt.NONE

    def _resolve_deictic_anchors(self, tracks: SomaticSensoryTracks) -> List[DeicticAnchor]:
        anchors: List[DeicticAnchor] = []
        text = tracks.voice.utterance or ""
        matches = self.DEICTIC_PATTERN.findall(text)

        for match in matches:
            m_lower = match.lower()
            if any(k in m_lower for k in ("error", "failure", "exception", "traceback")) and (tracks.terminal.exit_code != 0 or tracks.terminal.stderr_tail):
                err = tracks.terminal.stderr_tail or tracks.terminal.stdout_tail
                anchors.append(DeicticAnchor(raw_reference=match, target_kind="terminal_error", resolved_value=err.strip()[:200]))
            elif any(k in m_lower for k in ("function", "method", "class", "variable")) or tracks.cursor.symbol_under_cursor:
                symbol = tracks.cursor.symbol_under_cursor or "active_cursor_context"
                anchors.append(DeicticAnchor(
                    raw_reference=match,
                    target_kind="code_symbol",
                    resolved_value=f"{tracks.cursor.file_path}:{tracks.cursor.line_number} -> {symbol}"
                ))
            elif tracks.cursor.file_path:
                anchors.append(DeicticAnchor(
                    raw_reference=match,
                    target_kind="file_line",
                    resolved_value=f"{tracks.cursor.file_path}:{tracks.cursor.line_number}"
                ))
            else:
                anchors.append(DeicticAnchor(raw_reference=match, target_kind="none", resolved_value="unresolved"))
        return anchors

    def _classify_intent(self, tracks: SomaticSensoryTracks) -> tuple[str, str, bool]:
        # Fast local interrupt
        if tracks.voice.detected_interrupt != SomaticInterrupt.NONE:
            return "voice", "interrupt", True

        # Typing in input buffer without Enter yet
        if tracks.typing.is_typing and not tracks.typing.submitted:
            return "typing", "ambient", False

        # Prompt submitted via Enter
        if tracks.typing.submitted and tracks.typing.buffer_length > 0:
            return "typing", "query", True

        # Voice utterance after cadence pause
        if tracks.voice.utterance and not tracks.voice.is_speaking and tracks.voice.pause_duration_ms >= self.speech_pause_threshold_ms:
            # Check if voice is asking about an error or asking to build/fix
            utt = tracks.voice.utterance.lower()
            if tracks.terminal.exit_code != 0 and any(w in utt for w in ["why", "error", "fail", "broken", "fix"]):
                return "voice", "triage", True
            if any(w in utt for w in ["refactor", "create", "build", "scaffold", "implement", "how", "explain", "what"]):
                return "voice", "query", True
            return "voice", "ambient", False

        # Topic dirty flag (notes modified locally)
        if tracks.topic.is_dirty:
            return "spatial", "state_sync", True

        # Workspace diff dirty flag
        if tracks.workspace.is_dirty and not tracks.voice.is_speaking and not tracks.typing.is_typing:
            return "spatial", "state_sync", True

        # Default ambient state
        return "spatial", "ambient", False

    def _decide_routing(self, tracks: SomaticSensoryTracks, category: str, actionable: bool) -> RoutingTier:
        # Rule 1: Interrupts and ambient navigation are strictly LOCAL SOMATIC
        if category in ("interrupt", "ambient") or not actionable:
            return RoutingTier.SOMATIC_LOCAL

        # Rule 2: State / Presence sync (topic notes, workspace diff, device ping) -> FIREBASE UPPERMIND
        if category == "state_sync" or tracks.topic.is_dirty:
            return RoutingTier.FIREBASE_UPPERMIND

        # Rule 3: Direct queries, failure triage, architectural synthesis -> API UPPERMIND
        if category in ("query", "triage", "code_gen"):
            return RoutingTier.API_UPPERMIND

        return RoutingTier.SOMATIC_LOCAL

    def _synthesize_focal_summary(
        self,
        tracks: SomaticSensoryTracks,
        category: str,
        deictic_anchors: List[DeicticAnchor]
    ) -> str:
        parts: List[str] = []

        if category == "interrupt":
            return f"[INTERRUPT] Somatic halt/pause triggered by voice: '{tracks.voice.utterance}'"

        if category == "state_sync":
            return f"[STATE SYNC] Syncing dirty topic '{tracks.topic.topic_name}' ({tracks.topic.notes_count} notes) to Firebase Upper Mind."

        # Add cursor grounding
        if tracks.cursor.file_path:
            cursor_str = f"Looking at {tracks.cursor.file_path}:{tracks.cursor.line_number}"
            if tracks.cursor.symbol_under_cursor:
                cursor_str += f" ({tracks.cursor.symbol_under_cursor})"
            parts.append(cursor_str)

        # Add terminal status
        if tracks.terminal.exit_code != 0:
            parts.append(f"Command failed (exit {tracks.terminal.exit_code})")
        elif tracks.terminal.command:
            parts.append(f"Last command: {tracks.terminal.command}")

        # Add voice / deictic context
        if tracks.voice.utterance:
            parts.append(f"Spoken: '{tracks.voice.utterance}'")
            if deictic_anchors:
                anchor_strs = [f"'{a.raw_reference}' -> {a.resolved_value}" for a in deictic_anchors]
                parts.append(f"Deictic resolution: [{', '.join(anchor_strs)}]")

        # Add topic context
        if tracks.topic.topic_name:
            parts.append(f"Topic: {tracks.topic.topic_name}")

        return " | ".join(parts) if parts else "[AMBIENT] System idle and aligned."
