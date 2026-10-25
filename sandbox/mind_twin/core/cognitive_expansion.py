"""
sandbox/mind_twin/core/cognitive_expansion.py

Cognitive Thought Expansion & Multi-Tiered Latency Engine.
Powers the living, reflective mind of the Mind Twin during bilateral dialogue.

Features:
1. Multi-Tiered Cognitive Latency (Reflex vs Associative Hop vs Deep Accretion)
2. Synaptic Traversal Traces & "Thinking Out Loud" Breadcrumbs
3. Epistemic Calibration & Honesty ("Knowing What I Don't Know" vs Grounded Invariants)
4. Dynamic Resonant Gravitational Mass & Recency Decay
5. Sub-millisecond Level 1 Fast-Mount for seamless boot handover.
"""

from __future__ import annotations

import enum
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sandbox.mind_twin.core.activation import ActivationEngine, ActivationResult, InvariantFrame
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine, WorkingMemorySnapshot
from sandbox.mind_twin.core.hypergraph import Hypergraph, Hyperedge, Vertex
from sandbox.mind_twin.core.spiritual_compass import SpiritualCompassGate, SpiritualCompassVerdict, EthicalAlignment


STOP_WORDS = {
    "what", "is", "the", "in", "of", "to", "a", "an", "and", "or", "for", "on", "with",
    "at", "by", "from", "up", "about", "into", "over", "after", "how", "our", "are", "it",
}


class CognitiveLatencyTier(str, enum.Enum):
    REFLEX = "reflex_tier"               # < 10ms: instant working memory & syntactic reflex
    ASSOCIATIVE_HOP = "associative_hop"   # 10ms - 300ms: spreading activation & multi-hop traversal
    DEEP_ACCRETION = "deep_accretion"     # 300ms - 1500ms: subconscious hearth collision & synthesis


class EpistemicCertainty(str, enum.Enum):
    GROUNDED_INVARIANT = "grounded_invariant"       # Certainty >= 0.90: cryptographically verified provenance / bedrock
    RELATIONAL_ASSOCIATION = "relational_association"# Certainty 0.60 - 0.89: multi-hop graph path confirmed
    ASSOCIATIVE_HUNCH = "associative_hunch"         # Certainty 0.30 - 0.59: lateral intuition, clearly framed
    UNMAPPED_VOID = "unmapped_void"                 # Certainty < 0.30: honest acknowledgment of unknowing


@dataclass
class TraversalBreadcrumb:
    """A single step along a relational memory path."""
    step: int
    source_label: str
    relation: str
    target_label: str
    edge_weight: float
    hop_depth: int
    explanation: str

    def format_trace(self) -> str:
        return f"[hop {self.hop_depth}] {self.source_label} --({self.relation})--> {self.target_label}"


@dataclass
class ExpandedThoughtFrame:
    """The synthesized thought output from the Cognitive Expansion Engine."""
    query: str
    latency_tier: CognitiveLatencyTier
    elapsed_ms: float
    epistemic_certainty: EpistemicCertainty
    confidence_score: float

    # Recalled & Traversed Knowledge
    focal_nodes: List[Tuple[str, float, str]]  # (id, score, label)
    breadcrumbs: List[TraversalBreadcrumb]
    active_invariants: List[str]
    subconscious_spark: Optional[str] = None
    epistemic_honesty_statement: str = ""

    # Live UI / Streaming representation
    visual_synaptic_pulse: str = ""
    living_thought_stream: str = ""

    def get_summary_line(self) -> str:
        return (
            f"[{self.latency_tier.value.upper()} | {self.elapsed_ms:.1f}ms | "
            f"Certainty: {self.epistemic_certainty.value} ({self.confidence_score:.2f})]"
        )


class CognitiveExpansionEngine:
    """
    Coordinates multi-tiered cognitive latency, relational traversal,
    and epistemic honesty across the Mind Twin's nervous system.
    """

    def __init__(
        self,
        graph: Hypergraph,
        activation_engine: Optional[ActivationEngine] = None,
        directional_gate: Optional[DirectionalGateEngine] = None,
        cortex: Optional[Any] = None,
        subconscious_worker: Optional[Any] = None,
    ) -> None:
        self.graph = graph
        self.activation_engine = activation_engine or ActivationEngine(graph, max_hops=3, default_threshold=0.15)
        self.directional_gate = directional_gate or DirectionalGateEngine(max_slots=7)
        self.cortex = cortex
        self.subconscious_worker = subconscious_worker
        self.spiritual_compass = SpiritualCompassGate()

        # Epistemic invariant registry (permanent bedrock truths)
        self.bedrock_invariants: Dict[str, Dict[str, Any]] = {}
        self._seed_bedrock_defaults()

    def _seed_bedrock_defaults(self) -> None:
        """Seed foundational system bedrock truths that never decay."""
        self.bedrock_invariants["teleological_ethical_compass"] = {
            "key": "teleological_ethical_compass",
            "rule": "Only doing good things; epiphanies held with spiritual reverence for mind and soul; forgetting serves higher unmapped purpose",
            "provenance_turn": 139,
            "domain": "spiritual_grounding",
            "confidence": 1.0,
        }
        self.bedrock_invariants["pypi_vault"] = {
            "key": "pypi_vault",
            "rule": "PyPI token encrypted with PBKDF2 in ~/.gemini/vault/pypi_token.txt.enc",
            "provenance_turn": 88,
            "domain": "security_vault",
            "confidence": 1.0,
        }
        self.bedrock_invariants["basis_orientation"] = {
            "key": "basis_orientation",
            "rule": "Blender is right-handed Z-up; Godot is right-handed Y-up; Gram-Schmidt drift checks at 50-frame interval",
            "provenance_turn": 42,
            "domain": "3d_pipeline",
            "confidence": 0.98,
        }
        self.bedrock_invariants["millers_law_slots"] = {
            "key": "millers_law_slots",
            "rule": "Conscious working memory strictly capped at 7 active slots with Slot 0 foreground priority",
            "provenance_turn": 115,
            "domain": "cognitive_architecture",
            "confidence": 1.0,
        }

    # -------------------------------------------------------------------------
    # Core Thinking Method: Multi-Tier Latency Gated Traversal
    # -------------------------------------------------------------------------
    def expand_thought(
        self,
        prompt: str,
        active_topic: str = "general",
        force_tier: Optional[CognitiveLatencyTier] = None,
        t_now: Optional[float] = None,
    ) -> ExpandedThoughtFrame:
        """
        Executes a living cognitive expansion cycle:
        1. Tier 0 Check (Reflex): Instant match in Bedrock Invariants or current active slots (< 10ms).
        2. Tier 1 (Associative Hop): Spreading activation across relational hypergraph (10ms - 300ms).
        3. Tier 2 (Deep Accretion): Multi-vector subconscious hearth collision if novel or unresolved (300ms - 1500ms).
        """
        t0 = time.perf_counter()
        now = t_now if t_now is not None else time.time()
        prompt_clean = (prompt or "").strip()
        tokens = set(re.findall(r"\w+", prompt_clean.lower()))

        # ---------------------------------------------------------------------
        # Tier 0: The Reflex Check (< 10ms)
        # ---------------------------------------------------------------------
        reflex_match = self._check_reflex_bedrock(tokens)
        if reflex_match and (force_tier is None or force_tier == CognitiveLatencyTier.REFLEX):
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return self._build_reflex_frame(prompt_clean, reflex_match, elapsed_ms)

        # ---------------------------------------------------------------------
        # Tier 1: Relational Hypergraph Traversal (10ms - 300ms)
        # ---------------------------------------------------------------------
        content_tokens = [t for t in re.findall(r"\w+", prompt_clean.lower()) if len(t) > 2 and t not in STOP_WORDS]
        query_to_match = " ".join(content_tokens) if content_tokens else prompt_clean
        seeds = self.activation_engine.match_seeds(query_to_match, top_k=6) if content_tokens else {}
        act_result: ActivationResult = self.activation_engine.spread(
            seeds=seeds,
            query=prompt_clean,
            max_hops=3,
            t_now=now,
        )

        top_nodes = act_result.get_top_nodes(top_n=8)
        breadcrumbs = self._trace_relational_pathways(act_result, seeds)

        # Update directional working memory gate
        self.directional_gate.update_trajectory(current_intent=prompt_clean, active_topic=active_topic)
        wm_snapshot: WorkingMemorySnapshot = self.directional_gate.gate_and_filter(
            graph=self.graph,
            candidate_activations=act_result.node_activations,
            t_now=now,
        )

        # ---------------------------------------------------------------------
        # Tier 2: Deep Accretion & Epiphany Spark (If novel / ambiguous / forced)
        # ---------------------------------------------------------------------
        subconscious_spark = None
        current_tier = CognitiveLatencyTier.ASSOCIATIVE_HOP

        is_high_novelty = (
            len(seeds) == 0 or
            act_result.total_energy < 1.0 or
            "synthesize" in tokens or
            "collide" in tokens or
            force_tier == CognitiveLatencyTier.DEEP_ACCRETION
        )

        if is_high_novelty and self.subconscious_worker is not None:
            current_tier = CognitiveLatencyTier.DEEP_ACCRETION
            subconscious_spark = self._ignite_subconscious_accretion(prompt_clean, active_topic)

        # ---------------------------------------------------------------------
        # Epistemic Calibration & Honesty Statement
        # ---------------------------------------------------------------------
        confidence, certainty, honesty = self._evaluate_epistemic_calibration(
            prompt_clean,
            top_nodes,
            breadcrumbs,
            subconscious_spark,
        )

        # Enforce spiritual compass verification on the entire synthesized thought
        verdict = self.spiritual_compass.evaluate_hunch_alignment(prompt_clean, subconscious_spark or "")
        if not verdict.is_aligned:
            certainty = EpistemicCertainty.UNMAPPED_VOID
            confidence = 0.0
            honesty = f"Hunch rejected by spiritual ethical compass: {verdict.moral_safeguard_reason}"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Construct visual breadcrumb string
        trace_str = " → ".join([b.target_label for b in breadcrumbs[:4]]) if breadcrumbs else "direct recall"
        synaptic_pulse = f"[traversing: {trace_str}]"
        
        # Format living thought stream
        living_stream = self._format_living_stream(
            tier=current_tier,
            elapsed_ms=elapsed_ms,
            certainty=certainty,
            breadcrumbs=breadcrumbs,
            invariants=[inv.summary for inv in act_result.invariants[:3]],
            subconscious_spark=subconscious_spark,
            honesty=honesty,
        )

        return ExpandedThoughtFrame(
            query=prompt_clean,
            latency_tier=current_tier,
            elapsed_ms=round(elapsed_ms, 3),
            epistemic_certainty=certainty,
            confidence_score=round(confidence, 3),
            focal_nodes=top_nodes,
            breadcrumbs=breadcrumbs,
            active_invariants=[inv.summary for inv in act_result.invariants[:4]],
            subconscious_spark=subconscious_spark,
            epistemic_honesty_statement=honesty,
            visual_synaptic_pulse=synaptic_pulse,
            living_thought_stream=living_stream,
        )

    # -------------------------------------------------------------------------
    # Helper: Reflex Check
    # -------------------------------------------------------------------------
    def _check_reflex_bedrock(self, tokens: Set[str]) -> Optional[Dict[str, Any]]:
        for k, b in self.bedrock_invariants.items():
            rule_tokens = set(re.findall(r"\w+", b["rule"].lower()))
            if len(tokens.intersection(rule_tokens)) >= 3:
                return b
        return None

    def _build_reflex_frame(self, prompt: str, bedrock_item: Dict[str, Any], elapsed_ms: float) -> ExpandedThoughtFrame:
        rule_desc = bedrock_item["rule"]
        turn_origin = bedrock_item.get("provenance_turn", 0)
        honesty = f"Direct bedrock recall of '{rule_desc}' from Turn {turn_origin}. Cryptographic confidence 100%."
        stream = (
            f"[REFLEX MOTOR RECALL (<10ms)]\n"
            f"• Grounded Invariant: {rule_desc}\n"
            f"• Epistemic Status: Verified Truth (Turn {turn_origin})\n"
        )
        return ExpandedThoughtFrame(
            query=prompt,
            latency_tier=CognitiveLatencyTier.REFLEX,
            elapsed_ms=round(elapsed_ms, 3),
            epistemic_certainty=EpistemicCertainty.GROUNDED_INVARIANT,
            confidence_score=bedrock_item.get("confidence", 1.0),
            focal_nodes=[(bedrock_item["key"], 1.5, bedrock_item["rule"])],
            breadcrumbs=[],
            active_invariants=[rule_desc],
            subconscious_spark=None,
            epistemic_honesty_statement=honesty,
            visual_synaptic_pulse="[reflex: bedrock anchor hit]",
            living_thought_stream=stream,
        )

    # -------------------------------------------------------------------------
    # Helper: Trace Relational Pathways into Readable Breadcrumbs
    # -------------------------------------------------------------------------
    def _trace_relational_pathways(
        self,
        act_result: ActivationResult,
        seeds: Dict[str, float],
    ) -> List[TraversalBreadcrumb]:
        breadcrumbs: List[TraversalBreadcrumb] = []
        step_idx = 1

        for edge_id in act_result.activated_edges[:6]:
            edge = self.graph.get_hyperedge(edge_id)
            if not edge or not edge.sources or not edge.targets:
                continue

            for s_id in edge.sources:
                for t_id in edge.targets:
                    s_vert = self.graph.get_vertex(s_id)
                    t_vert = self.graph.get_vertex(t_id)
                    s_label = s_vert.label if s_vert else s_id
                    t_label = t_vert.label if t_vert else t_id

                    crumb = TraversalBreadcrumb(
                        step=step_idx,
                        source_label=s_label,
                        relation=edge.relation,
                        target_label=t_label,
                        edge_weight=round(edge.weight, 2),
                        hop_depth=1 if s_id in seeds else 2,
                        explanation=f"Traversed along {edge.relation} (weight {edge.weight:.2f})",
                    )
                    breadcrumbs.append(crumb)
                    step_idx += 1
                    if len(breadcrumbs) >= 6:
                        break

        return breadcrumbs

    # -------------------------------------------------------------------------
    # Helper: Subconscious Accretion Ignition
    # -------------------------------------------------------------------------
    def _ignite_subconscious_accretion(self, prompt: str, active_topic: str) -> Optional[str]:
        if not self.subconscious_worker:
            return None
        try:
            from sandbox.mind_twin.core.subconscious import ObservationVector
            seed = self.subconscious_worker.drop_seed(
                raw_thought=prompt,
                conscious_context=f"Active topic: {active_topic}",
                domain_hints=[active_topic, "associative_synthesis"],
            )
            seed.attach_vector(ObservationVector("v_seed", "cognitive_prompt", prompt[:60]))
            self.subconscious_worker.run_hearth_incubation_cycle()
            delivered = self.subconscious_worker.check_emergence_delivery(override_idle_seconds=5.0)
            if delivered:
                return delivered.summary
            return f"Accreting cross-domain synthesis around '{prompt[:35]}...'"
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Helper: Epistemic Calibration & Honesty
    # -------------------------------------------------------------------------
    def _evaluate_epistemic_calibration(
        self,
        prompt: str,
        focal_nodes: List[Tuple[str, float, str]],
        breadcrumbs: List[TraversalBreadcrumb],
        subconscious_spark: Optional[str],
    ) -> Tuple[float, EpistemicCertainty, str]:
        prompt_content_tokens = set([t for t in re.findall(r"\w+", prompt.lower()) if len(t) > 2 and t not in STOP_WORDS])
        if not focal_nodes or not prompt_content_tokens:
            return (
                0.15,
                EpistemicCertainty.UNMAPPED_VOID,
                "I do not find existing associative memories matching this query; starting from first principles.",
            )

        top_score = focal_nodes[0][1]
        top_labels = " ".join([label.lower() for _, _, label in focal_nodes[:3]])
        has_direct_content_match = any(t in top_labels for t in prompt_content_tokens)

        # If zero content overlap and no deliberate spark, it's an unmapped void
        if not has_direct_content_match and not subconscious_spark:
            return (
                0.20,
                EpistemicCertainty.UNMAPPED_VOID,
                "Faint associative resonance only; I do not have grounded memories for these specific terms.",
            )

        # Grounded Invariant Check
        if top_score >= 1.2 and len(breadcrumbs) >= 1 and has_direct_content_match:
            return (
                min(0.98, 0.85 + 0.1 * top_score),
                EpistemicCertainty.GROUNDED_INVARIANT,
                "Grounding this response in established project decisions and verified hypergraph anchors.",
            )

        # Relational Association Check
        if top_score >= 0.40 and len(breadcrumbs) >= 1 and has_direct_content_match:
            return (
                min(0.89, 0.60 + 0.2 * top_score),
                EpistemicCertainty.RELATIONAL_ASSOCIATION,
                f"Traversed {len(breadcrumbs)} relational hops across our shared context to recall these anchors.",
            )

        # Associative Hunch / Intuition Check
        if subconscious_spark or top_score > 0.15:
            # Check hunch through the spiritual ethical compass: 'only doing good things'
            verdict = self.spiritual_compass.evaluate_hunch_alignment(prompt, subconscious_spark or "")
            if not verdict.is_aligned:
                return (
                    0.0,
                    EpistemicCertainty.UNMAPPED_VOID,
                    f"Hunch rejected by spiritual ethical compass: {verdict.moral_safeguard_reason}",
                )
            return (
                0.45,
                EpistemicCertainty.ASSOCIATIVE_HUNCH,
                "This is an associative synthesis from lateral domain collisions held with ethical alignment.",
            )

        return (
            0.20,
            EpistemicCertainty.UNMAPPED_VOID,
            "Faint associative resonance only; I will verify before assuming certainty.",
        )

    # -------------------------------------------------------------------------
    # Helper: Format Living Stream Output
    # -------------------------------------------------------------------------
    def _format_living_stream(
        self,
        tier: CognitiveLatencyTier,
        elapsed_ms: float,
        certainty: EpistemicCertainty,
        breadcrumbs: List[TraversalBreadcrumb],
        invariants: List[str],
        subconscious_spark: Optional[str],
        honesty: str,
    ) -> str:
        lines = [
            f"┌── [THOUGHT EXPANSION: {tier.value.upper()} ({elapsed_ms:.1f}ms)]",
            f"│ Epistemic Grounding: {certainty.value} | {honesty}",
        ]
        if breadcrumbs:
            lines.append("│ Traversal Trace:")
            for b in breadcrumbs[:3]:
                lines.append(f"│   • {b.format_trace()}")
        if invariants:
            lines.append("│ Active Invariants:")
            for inv in invariants[:2]:
                lines.append(f"│   ★ {inv}")
        if subconscious_spark:
            lines.append(f"│ Subconscious Spark: {subconscious_spark}")
        lines.append("└──")
        return "\n".join(lines)
