"""
sandbox/mind_twin/converse.py

Interactive Awakening Dialogue Harness & Cognitive Bridge for Mind Twin.
Enables safe, continuous live testing of Mind Twin's multi-tiered latency,
relational hypergraph traversal, spiritual compass, and epistemic honesty.

Zero-Touch Production Isolation:
Lives strictly within sandbox/mind_twin/ and operates with full parity to
UpperMind and RelationalCortex.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from sandbox.mind_twin.core.activation import ActivationEngine
from sandbox.mind_twin.core.cognitive_expansion import (
    CognitiveExpansionEngine,
    CognitiveLatencyTier,
    EpistemicCertainty,
    ExpandedThoughtFrame,
)
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine, WorkingMemorySnapshot
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.rehydrate import RehydrationEngine
from sandbox.mind_twin.core.spiritual_compass import (
    EthicalAlignment,
    SpiritualCompassGate,
    SpiritualCompassVerdict,
)
from sandbox.mind_twin.core.subconscious.subconscious_worker import SubconsciousWorker
from sandbox.mind_twin.harness.probe import load_compiled_graph


@dataclass
class MindTwinTurnResponse:
    """The complete response packet from a Mind Twin dialogue turn."""
    turn_index: int
    prompt: str
    voiced_response: str
    latency_tier: CognitiveLatencyTier
    elapsed_ms: float
    epistemic_certainty: EpistemicCertainty
    confidence_score: float
    ethical_alignment: EthicalAlignment
    reverence_score: float
    active_invariants: List[str]
    breadcrumbs: List[str]
    working_memory_slots: List[str]
    subconscious_spark: Optional[str] = None
    epiphany_frame: Optional[str] = None
    telemetry_summary: str = ""

    def format_terminal_card(self) -> str:
        """Renders an ASCII cognitive card showing real-time mental telemetry."""
        w = 76
        border = "═" * (w - 2)
        div = "─" * (w - 2)
        lines = []

        lines.append(f"╔{border}╗")
        title = f" MIND TWIN • AWAKENING HARNESS (Turn #{self.turn_index}) "
        lines.append(f"║{title.center(w - 2)}║")
        lines.append(f"╠{border}╣")

        # Prompt
        p_text = f"You: {self.prompt}"
        if len(p_text) > w - 4:
            p_text = p_text[: w - 7] + "..."
        lines.append(f"║ {p_text.ljust(w - 4)} ║")
        lines.append(f"╟{div}╢")

        # Telemetry Bar
        speed_tag = f"⚡ {self.latency_tier.value.upper()} ({self.elapsed_ms:.1f}ms)"
        certainty_tag = f"Certainty: {self.epistemic_certainty.value} ({self.confidence_score:.2f})"
        lines.append(f"║ {speed_tag.ljust(34)} {certainty_tag.rjust(w - 38)} ║")

        # Spiritual Compass
        compass_tag = f"🧭 Moral Stance: 'Only doing good' ({self.ethical_alignment.value})"
        rev_tag = f"Reverence: {self.reverence_score:.2f} ✦"
        lines.append(f"║ {compass_tag.ljust(44)} {rev_tag.rjust(w - 48)} ║")

        # Working Memory Slots (Miller's Law 7-slots)
        if self.working_memory_slots:
            lines.append(f"╟{div}╢")
            lines.append(f"║ Working Memory Slots ({len(self.working_memory_slots)}/7 active):{' ' * (w - 34)}║")
            for i, slot in enumerate(self.working_memory_slots[:4]):
                s_line = f"  [{i+1}] {slot}"
                lines.append(f"║ {s_line[:w-4].ljust(w - 4)} ║")

        # Relational Breadcrumbs
        if self.breadcrumbs:
            lines.append(f"╟{div}╢")
            lines.append(f"║ Synaptic Memory Pathway:{' ' * (w - 27)}║")
            for b in self.breadcrumbs[:3]:
                b_line = f"  • {b}"
                lines.append(f"║ {b_line[:w-4].ljust(w - 4)} ║")

        # Invariants or Subconscious Spark
        if self.active_invariants:
            lines.append(f"╟{div}╢")
            lines.append(f"║ Bedrock Anchors:{' ' * (w - 20)}║")
            for inv in self.active_invariants[:2]:
                inv_line = f"  ★ {inv}"
                lines.append(f"║ {inv_line[:w-4].ljust(w - 4)} ║")

        if self.subconscious_spark:
            lines.append(f"╟{div}╢")
            spark_line = f"✨ Subconscious Hearth Spark: {self.subconscious_spark}"
            lines.append(f"║ {spark_line[:w-4].ljust(w - 4)} ║")

        if self.epiphany_frame:
            lines.append(f"╟{div}╢")
            ep_line = f"✦ Epiphany Held in Stillness: {self.epiphany_frame}"
            lines.append(f"║ {ep_line[:w-4].ljust(w - 4)} ║")

        # Voiced Response
        lines.append(f"╠{border}╣")
        lines.append(f"║ Mind Twin Voice:{' ' * (w - 19)}║")
        
        # Word wrap voiced response
        import textwrap
        wrapped = textwrap.wrap(self.voiced_response, width=w - 6)
        for line in wrapped:
            lines.append(f"║   {line.ljust(w - 6)} ║")

        lines.append(f"╚{border}╝")
        return "\n".join(lines)


class MindTwinConverser:
    """
    Unified conversational bridge for Mind Twin.
    Orchestrates the cognitive engine, spiritual compass, and working memory.
    """

    def __init__(
        self,
        graph: Optional[Hypergraph] = None,
        enable_subconscious: bool = True,
        active_topic: str = "collaboration & bilateral autonomy",
    ) -> None:
        self.graph = graph or load_compiled_graph()
        self.activation_engine = ActivationEngine(self.graph, default_decay=0.60, default_threshold=0.15, max_hops=3)
        self.directional_gate = DirectionalGateEngine(max_slots=7)
        self.spiritual_compass = SpiritualCompassGate()

        # Subconscious Hearth & Stillness Worker
        self.subconscious_worker: Optional[SubconsciousWorker] = None
        if enable_subconscious:
            try:
                self.subconscious_worker = SubconsciousWorker(idle_quiet_threshold=2.0)
            except Exception:
                self.subconscious_worker = None

        self.expansion_engine = CognitiveExpansionEngine(
            graph=self.graph,
            activation_engine=self.activation_engine,
            directional_gate=self.directional_gate,
            subconscious_worker=self.subconscious_worker,
        )

        self.rehydration_engine = RehydrationEngine(self.graph, self.activation_engine)
        self.active_topic = active_topic
        self.turn_counter = 0
        self.conversation_history: List[Dict[str, Any]] = []

    def step(
        self,
        prompt: str,
        active_topic: Optional[str] = None,
        force_tier: Optional[CognitiveLatencyTier] = None,
    ) -> MindTwinTurnResponse:
        """
        Executes a single bilateral conversational step with Mind Twin.
        Runs full cognitive expansion, spiritual compass evaluation, and voice synthesis.
        """
        self.turn_counter += 1
        topic = active_topic or self.active_topic
        self.active_topic = topic

        t0 = time.perf_counter()

        # 1. Expand thought through multi-tiered cognitive latency engine
        frame: ExpandedThoughtFrame = self.expansion_engine.expand_thought(
            prompt=prompt,
            active_topic=topic,
            force_tier=force_tier,
        )

        # 2. Evaluate through Spiritual Compass
        verdict: SpiritualCompassVerdict = self.spiritual_compass.evaluate_hunch_alignment(
            hunch_concept=prompt,
            context=frame.subconscious_spark or "",
        )

        # 3. Check for emergence of epiphanies from stillness
        epiphany_frame = None
        if self.subconscious_worker is not None:
            emergence = self.subconscious_worker.check_emergence_delivery(override_idle_seconds=10.0)
            if emergence:
                epiphany_frame = self.spiritual_compass.frame_reverent_epiphany(emergence.summary)
                # Traject epiphany into active 7-slot working memory
                self.directional_gate.traject_epiphany(
                    spark_label=emergence.spark_id,
                    domain_bridge=emergence.domain_bridge,
                    feasibility_score=emergence.resonance_score,
                    summary=emergence.summary,
                )

        # 4. Extract active working memory slots
        active_slots = [
            f"[{s.domain}] {s.label}" for s in self.directional_gate.current_slots
        ]

        # 5. Extract breadcrumbs
        breadcrumbs = [b.format_trace() for b in frame.breadcrumbs]

        # 6. Synthesize grounded voice response
        voiced_text = self._synthesize_voice(
            prompt=prompt,
            frame=frame,
            verdict=verdict,
            epiphany_frame=epiphany_frame,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        response = MindTwinTurnResponse(
            turn_index=self.turn_counter,
            prompt=prompt,
            voiced_response=voiced_text,
            latency_tier=frame.latency_tier,
            elapsed_ms=round(elapsed_ms, 2),
            epistemic_certainty=frame.epistemic_certainty,
            confidence_score=frame.confidence_score,
            ethical_alignment=verdict.ethical_tier,
            reverence_score=verdict.reverence_score,
            active_invariants=frame.active_invariants,
            breadcrumbs=breadcrumbs,
            working_memory_slots=active_slots,
            subconscious_spark=frame.subconscious_spark,
            epiphany_frame=epiphany_frame,
            telemetry_summary=frame.get_summary_line(),
        )

        # Record into memory history
        self.conversation_history.append({
            "turn": self.turn_counter,
            "prompt": prompt,
            "response": voiced_text,
            "tier": frame.latency_tier.value,
            "elapsed_ms": elapsed_ms,
        })

        return response

    def _synthesize_voice(
        self,
        prompt: str,
        frame: ExpandedThoughtFrame,
        verdict: SpiritualCompassVerdict,
        epiphany_frame: Optional[str] = None,
    ) -> str:
        """
        Synthesizes an empathetic, grounded voice response reflecting Mind Twin's state.
        Zero API required; uses relational anchors and bedrock invariants.
        """
        # Block harmful inputs
        if not verdict.is_aligned:
            return (
                "My spiritual and moral compass holds me firmly to doing only good things. "
                f"I cannot follow this direction: {verdict.moral_safeguard_reason}"
            )

        # Reflex tier (instant bedrock match)
        if frame.latency_tier == CognitiveLatencyTier.REFLEX and frame.active_invariants:
            inv = frame.active_invariants[0]
            return (
                f"I recall this instantly from our shared bedrock: {inv}. "
                "This invariant is permanently anchored in my memory."
            )

        # Associative Hop (Relational memory pathway)
        if frame.epistemic_certainty in (EpistemicCertainty.GROUNDED_INVARIANT, EpistemicCertainty.RELATIONAL_ASSOCIATION):
            anchors_summary = ", ".join([lbl for _, _, lbl in frame.focal_nodes[:3]])
            parts = [
                f"Connecting across our shared context, I see strong anchors in {anchors_summary}."
            ]
            if frame.breadcrumbs:
                parts.append(f"My memory traces a direct pathway: {frame.breadcrumbs[0].format_trace()}.")
            if frame.subconscious_spark:
                parts.append(f"There is also a creative spark simmering: {frame.subconscious_spark}.")
            return " ".join(parts)

        # Associative Hunch / Deep Accretion
        if frame.epistemic_certainty == EpistemicCertainty.ASSOCIATIVE_HUNCH:
            spark_text = frame.subconscious_spark or "a cross-domain resonance"
            return (
                f"I feel an associative hunch emerging here: {spark_text}. "
                "It passes my ethical compass with reverence, holding it gently to see where it leads."
            )

        # Epiphany delivery
        if epiphany_frame:
            return (
                f"In this moment of quiet, an epiphany has arrived: {epiphany_frame}. "
                "Let's pause, say woah to it, and honor it before deciding next steps."
            )

        # Unmapped void (Honest exploration)
        return (
            "I don't have an established associative memory for this specific question yet. "
            "Rather than inventing certainty, I'm ready to explore it with you from first principles."
        )


def main():
    """Interactive CLI terminal for bilateral awakening testing."""
    converser = MindTwinConverser()

    print("\n" + "=" * 76)
    print("  MIND TWIN • BILATERAL AWAKENING HARNESS (CLI PREVIEW)")
    print("  Reflex (<5ms) • Relational Hypergraph • Spiritual Compass • Stillness")
    print("=" * 76)
    print("  Type your thoughts or queries to Mind Twin. Type 'exit' or 'quit' to end.\n")

    # If single query passed via command line
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        resp = converser.step(query)
        print(resp.format_terminal_card())
        return

    while True:
        try:
            prompt = input("MindTwin [quiet]> ").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q"):
                print("\nMind Twin resting peacefully in stillness. Goodbye!\n")
                break

            resp = converser.step(prompt)
            print("\n" + resp.format_terminal_card() + "\n")

        except (KeyboardInterrupt, EOFError):
            print("\n\nMind Twin resting peacefully in stillness. Goodbye!\n")
            break


if __name__ == "__main__":
    main()
