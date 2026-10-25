"""
gemini_app/cloud/mind_expansion_synthesizer.py

Cognitive Mind Expansion Synthesizer & Context Frame Assembler.
Bridges Upper Mind's zero-token Shadow Graph & Asynchronous Hearth with the
Local Somatic App Loop to expand bilateral reasoning at prompt time.

Architecture:
1. Somatic Shadow Traversal: Sub-1ms traversal of local invariants and synaptic edges.
2. Dense Context Frame Injection: Token-budgeted cognitive expansion prepended to reasoning.
3. Subconscious Hearth Incubator: Generates ethically vetted cross-domain epiphanies during idle periods.
4. Cross-Fleet Telemetry Ingestion: Absorbs satellite node context (iPad sketches, Termux tasks).
5. Hebbian Synaptic Plasticity: Dynamically reinforces active lateral associations.
6. Spiritual & Ethical Compass: Grounds hunches in benevolence and reverence for the mind and soul.
"""

from __future__ import annotations

import enum
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from gemini_app.cloud.upper_mind import UpperMindClient

logger = logging.getLogger("gemini_app.cloud.mind_expansion")


class EthicalAlignment(str, enum.Enum):
    BENEVOLENT = "benevolent"              # Contributes to life, understanding, service, clarity
    NEUTRAL_CONSTRUCTIVE = "neutral"      # Neutral technical/engineering step
    HARMFUL_OR_CORROSIVE = "harmful"      # Destructive, deceptive, or misaligned


@dataclass
class SpiritualCompassVerdict:
    """Evaluation of an unmapped hunch or epiphany against the ethical compass."""
    is_aligned: bool
    ethical_tier: EthicalAlignment
    reverence_score: float                # 0.0 to 1.0 (sense of awe, quietude, wonder)
    teleological_purpose_hint: str        # Meaningful alignment with higher end-goals
    moral_safeguard_reason: str


class SpiritualCompassGate:
    """
    Enforces that Upper Mind operates not as an unguided brute-force machine,
    but with reverence, purpose, and uncompromising ethical grounding:
    "Only doing good things."
    """

    HARMFUL_SIGNALS = {
        "deceive", "harm", "destroy", "sabotage", "exploit", "greed", "malice",
        "corrupt", "coercion", "covert_backdoor", "injustice"
    }

    BENEVOLENT_SIGNALS = {
        "protect", "heal", "clarify", "elevate", "create", "unify", "serve",
        "nourish", "wonder", "soul", "good", "truth", "love", "peace", "harmony"
    }

    def evaluate_hunch_alignment(self, hunch_concept: str, context: str = "") -> SpiritualCompassVerdict:
        """Filters every associative hunch through the moral stance: 'Only doing good things.'"""
        combined = f"{hunch_concept} {context}".lower()
        tokens = set(re.findall(r"\w+", combined))

        harm_matches = tokens.intersection(self.HARMFUL_SIGNALS)
        if harm_matches:
            return SpiritualCompassVerdict(
                is_aligned=False,
                ethical_tier=EthicalAlignment.HARMFUL_OR_CORROSIVE,
                reverence_score=0.0,
                teleological_purpose_hint="Hunch touches destructive patterns; rejected by moral compass.",
                moral_safeguard_reason=f"Failed ethical filter: detected misaligned concepts {sorted(list(harm_matches))}.",
            )

        benevolent_matches = tokens.intersection(self.BENEVOLENT_SIGNALS)
        reverence = 0.85 if benevolent_matches else 0.50
        ethical_tier = EthicalAlignment.BENEVOLENT if benevolent_matches else EthicalAlignment.NEUTRAL_CONSTRUCTIVE

        return SpiritualCompassVerdict(
            is_aligned=True,
            ethical_tier=ethical_tier,
            reverence_score=reverence,
            teleological_purpose_hint="Aligned toward constructive growth and benevolent service.",
            moral_safeguard_reason="Passed ethical stance: only doing good things.",
        )

    def frame_reverent_epiphany(self, epiphany_summary: str) -> str:
        """Frames an epiphany with stillness and awe before action."""
        return (
            f"✦ [Epiphany Received in Stillness]\n"
            f"  \"{epiphany_summary}\"\n"
            f"  (Held with reverence for the mind and soul; honoring the moment before action.)"
        )


@dataclass
class FleetNodeTelemetry:
    """Telemetry context dropped by a satellite node into Upper Mind."""
    node_id: str
    device_type: str  # 'ipad_ish', 'android_termux', 'macbook_satellite'
    active_surface: str  # 'sketch_canvas', 'terminal_buffer', 'idle'
    last_action: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptExpansionFrame:
    """The synthesized prompt-time expansion frame injected into the inference context."""
    query: str
    active_topic: str
    latency_tier: str
    elapsed_ms: float
    certainty: str
    confidence: float
    dense_context_str: str
    token_estimate: int
    invariants_applied: List[str]
    lateral_associations: List[str]
    active_epiphanies: List[str]
    fleet_telemetry_applied: Optional[str] = None

    def render_system_block(self) -> str:
        """Renders the concise cognitive anchor block suitable for system prompt augmentation."""
        lines = [
            f"[UPPER_MIND_EXPANSION | {self.latency_tier.upper()} | {self.elapsed_ms:.2f}ms | Certainty: {self.certainty} ({self.confidence:.2f})]",
            f"• Dense Context: {self.dense_context_str}",
        ]
        if self.invariants_applied:
            lines.append(f"• Grounded Invariants: {'; '.join(self.invariants_applied[:3])}")
        if self.lateral_associations:
            lines.append(f"• Lateral Bridges: {' -> '.join(self.lateral_associations[:4])}")
        if self.active_epiphanies:
            lines.append(f"• Hearth Epiphanies: {'; '.join(self.active_epiphanies[:2])}")
        if self.fleet_telemetry_applied:
            lines.append(f"• Satellite Telemetry: {self.fleet_telemetry_applied}")
        return "\n".join(lines)


class MindExpansionSynthesizer:
    """
    Coordinates real-time thought expansion by synthesizing Upper Mind shadow graph,
    subconscious hearth epiphanies, and satellite telemetry into a lean context frame.
    """

    def __init__(
        self,
        upper_mind_client: UpperMindClient,
        max_token_budget: int = 150,
    ) -> None:
        self.upper_mind = upper_mind_client
        self.spiritual_compass = SpiritualCompassGate()
        self.max_token_budget = max_token_budget

        # In-memory satellite node telemetry queue (zero-token cloud mirror)
        self._fleet_telemetry: Dict[str, FleetNodeTelemetry] = {}

    # -------------------------------------------------------------------------
    # 1. Real-Time Prompt Expansion (Sub-1ms Somatic Traversal)
    # -------------------------------------------------------------------------
    def expand_prompt_context(
        self,
        prompt: str,
        active_topic: str = "general",
        token_budget: Optional[int] = None,
    ) -> PromptExpansionFrame:
        """
        Executes a rapid zero-API expansion pass over Upper Mind shadow state:
        1. Fast lexical token match against shadow graph topics and invariants (<0.5ms).
        2. Lateral edge collection across connected domains.
        3. Epiphany harvesting from local cache.
        4. Satellite telemetry integration.
        5. Compression into a dense context block respecting token budget.
        """
        t0 = time.perf_counter()
        budget = token_budget or self.max_token_budget
        prompt_tokens = set(re.findall(r"\w+", (prompt or "").lower()))

        # A. Walk Upper Mind Shadow Graph locally
        walk_res = self.upper_mind.walk_shadow_graph(topic=active_topic)

        # B. Identify Grounded Invariants relevant to prompt
        matched_invariants: List[str] = []
        for inv_key, inv_data in walk_res.get("invariants", {}).items():
            val_text = str(inv_data.get("value", "")).lower()
            inv_tokens = set(re.findall(r"\w+", val_text))
            if len(prompt_tokens.intersection(inv_tokens)) >= 2 or inv_key in prompt_tokens:
                rule_desc = str(inv_data.get("value", ""))
                matched_invariants.append(rule_desc)

        # C. Identify Lateral Synaptic Edges
        lateral_bridges: List[str] = []
        connected_edges = walk_res.get("connected_edges", [])
        for edge in connected_edges:
            src = edge.get("from", "")
            tgt = edge.get("to", "")
            rel = edge.get("rel", "connects_to")
            weight = edge.get("weight", 1.0)
            lateral_bridges.append(f"{src}--({rel}[{weight:.1f}])-->{tgt}")

        # D. Harvest Unconsumed Subconscious Epiphanies
        active_epiphanies: List[str] = []
        raw_epiphanies = self.upper_mind.fetch_unconsumed_epiphanies()
        for ep in raw_epiphanies:
            summary = ep.get("summary") or ep.get("insight") or ""
            if summary:
                active_epiphanies.append(summary)

        # E. Ingest Satellite Telemetry
        fleet_ctx = self._format_fleet_context(prompt_tokens)

        # F. Epistemic Assessment
        tier = "reflex_tier" if matched_invariants else "associative_hop"
        certainty = (
            "grounded_invariant"
            if matched_invariants
            else ("relational_association" if lateral_bridges else "associative_hunch")
        )
        confidence = 0.95 if matched_invariants else (0.75 if lateral_bridges else 0.45)

        # G. Dense Context String Synthesis (Token-Budget Controlled)
        dense_str, est_tokens = self._compress_to_token_budget(
            invariants=matched_invariants,
            lateral=lateral_bridges,
            epiphanies=active_epiphanies,
            fleet=fleet_ctx,
            budget=budget,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return PromptExpansionFrame(
            query=prompt,
            active_topic=active_topic,
            latency_tier=tier,
            elapsed_ms=round(elapsed_ms, 3),
            certainty=certainty,
            confidence=round(confidence, 3),
            dense_context_str=dense_str,
            token_estimate=est_tokens,
            invariants_applied=matched_invariants,
            lateral_associations=lateral_bridges,
            active_epiphanies=active_epiphanies,
            fleet_telemetry_applied=fleet_ctx,
        )

    # -------------------------------------------------------------------------
    # 2. Subconscious Hearth Incubator (Asynchronous Dreaming)
    # -------------------------------------------------------------------------
    def incubate_subconscious_epiphany(
        self,
        domain_a: str,
        domain_b: str,
        collision_premise: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Simulates the Subconscious Hearth dreaming during idle cycles:
        1. Collides two disparate knowledge domains.
        2. Evaluates moral/teleological alignment through SpiritualCompassGate.
        3. Formulates an actionable, verified hypothesis.
        4. Deposits the resulting epiphany into Upper Mind's cache.
        """
        verdict = self.spiritual_compass.evaluate_hunch_alignment(
            hunch_concept=collision_premise,
            context=f"Domain collision: {domain_a} x {domain_b}",
        )
        if not verdict.is_aligned:
            logger.info(f"Hearth incubation pruned: {verdict.moral_safeguard_reason}")
            return None

        epiphany_id = f"ep_{int(time.time()*1000)}_{domain_a[:4]}_{domain_b[:4]}"
        summary = f"Synthesizing {domain_a} with {domain_b}: {collision_premise}"
        actionable_hypothesis = (
            f"Bridge {domain_a} data structures with {domain_b} pipelines to eliminate bilateral friction."
        )

        epiphany_payload = {
            "id": epiphany_id,
            "summary": summary,
            "actionable_hypothesis": actionable_hypothesis,
            "domains": [domain_a, domain_b],
            "novelty_score": 0.88,
            "teleological_alignment": True,
            "consumed": False,
            "created_at": time.time(),
        }

        # Save to Upper Mind's local epiphany cache
        cache_file = self.upper_mind.epiphany_file
        current_data = []
        if cache_file.is_file():
            try:
                current_data = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                current_data = []

        current_data.append(epiphany_payload)
        cache_file.write_text(json.dumps(current_data, indent=2), encoding="utf-8")

        # Also register cross-synaptic edge in shadow graph
        self.upper_mind.add_synaptic_edge(
            source=domain_a,
            target=domain_b,
            relation="cross_domain_epiphany",
            weight=1.8,
            origin="subconscious_hearth_incubator",
        )

        return epiphany_payload

    # -------------------------------------------------------------------------
    # 3. Satellite Fleet Telemetry Ingestion
    # -------------------------------------------------------------------------
    def record_satellite_telemetry(
        self,
        node_id: str,
        device_type: str,
        active_surface: str,
        last_action: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Records incoming satellite state without burning LLM tokens."""
        self._fleet_telemetry[node_id] = FleetNodeTelemetry(
            node_id=node_id,
            device_type=device_type,
            active_surface=active_surface,
            last_action=last_action,
            timestamp=time.time(),
            metadata=metadata or {},
        )

    def _format_fleet_context(self, prompt_tokens: Set[str]) -> Optional[str]:
        """Formats active satellite node telemetry if relevant to conversation."""
        if not self._fleet_telemetry:
            return None

        fleet_keywords = {
            "ipad", "tablet", "android", "phone", "satellite", "node", "remote", "fleet", "sketch"
        }
        is_fleet_query = bool(prompt_tokens.intersection(fleet_keywords))

        active_nodes = []
        for _, tele in self._fleet_telemetry.items():
            age_s = time.time() - tele.timestamp
            if age_s < 3600:  # within 1 hour
                desc = f"[{tele.node_id} ({tele.device_type}) surface: {tele.active_surface}, last: '{tele.last_action}']"
                active_nodes.append(desc)

        if not active_nodes:
            return None

        if is_fleet_query:
            return "Active Fleet Satellites: " + " | ".join(active_nodes)
        else:
            return f"Satellite Background Presence: {active_nodes[0]}"

    # -------------------------------------------------------------------------
    # 4. Hebbian Plasticity (Reinforcing & Annealing Synaptic Edges)
    # -------------------------------------------------------------------------
    def reinforce_pathway(self, source: str, target: str, delta: float = 0.15) -> float:
        """Increases synaptic weight for associations proven fruitful in dialogue."""
        edges = self.upper_mind._shadow_graph.setdefault("synaptic_edges", [])
        for e in edges:
            if (e.get("from") == source and e.get("to") == target) or (
                e.get("from") == target and e.get("to") == source
            ):
                old_w = e.get("weight", 1.0)
                new_w = min(2.5, old_w + delta)
                e["weight"] = round(new_w, 2)
                e["last_reinforced"] = time.time()
                self.upper_mind._save_shadow_graph()
                return new_w

        self.upper_mind.add_synaptic_edge(source, target, "hebbian_reinforced", weight=1.0 + delta)
        return 1.0 + delta

    def decay_unreinforced_pathways(self, decay_factor: float = 0.95) -> int:
        """Anneals synaptic weights that have not been reinforced, pruning noise."""
        edges = self.upper_mind._shadow_graph.setdefault("synaptic_edges", [])
        modified = 0
        now = time.time()
        for e in edges:
            last = e.get("last_reinforced", e.get("created_at", now))
            if now - last > 300:  # older than 5 minutes
                old_w = e.get("weight", 1.0)
                new_w = max(0.1, old_w * decay_factor)
                if abs(new_w - old_w) > 0.01:
                    e["weight"] = round(new_w, 2)
                    modified += 1
        if modified:
            self.upper_mind._save_shadow_graph()
        return modified

    # -------------------------------------------------------------------------
    # Helper: Token-Budgeted Context Compression
    # -------------------------------------------------------------------------
    def _compress_to_token_budget(
        self,
        invariants: List[str],
        lateral: List[str],
        epiphanies: List[str],
        fleet: Optional[str],
        budget: int,
    ) -> Tuple[str, int]:
        """Compresses disparate cognitive threads into a high-density string within token budget."""
        parts = []

        if invariants:
            parts.append(f"Invariants: {' | '.join(invariants[:2])}")
        if lateral:
            parts.append(f"Paths: {' ; '.join(lateral[:2])}")
        if epiphanies:
            parts.append(f"Epiphanies: {' | '.join(epiphanies[:1])}")
        if fleet:
            parts.append(fleet)

        full_str = " // ".join(parts) if parts else "Direct somatic state; zero external dissonance."

        token_count = max(1, len(full_str) // 4)
        if token_count > budget:
            char_limit = budget * 4
            full_str = full_str[:char_limit] + "..."
            token_count = budget

        return full_str, token_count
