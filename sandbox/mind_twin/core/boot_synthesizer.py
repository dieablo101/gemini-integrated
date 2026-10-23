"""
Unified Boot Synthesizer & Mental State Assembler.
Unites Notes, Episodic History, PNS Sensory Telemetry, and Fleet Node Capabilities
into a single, unitized cognitive state vector upon boot.
Equipped with a 7-Slot Directional Working Memory Gate (Miller's Law)
and Subconscious Incubation Worker. Hardened with comprehensive input sanitization
and runtime failsafes.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sandbox.mind_twin.core.activation import ActivationEngine, ActivationResult, InvariantFrame
from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine, WorkingMemorySnapshot
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.node_capability import (
    FleetTopologySynthesizer,
    NodeCapabilityProfile,
    WholeSystemCapability,
)
from sandbox.mind_twin.core.pns_sensor import (
    PhoneSensorySynthesizer,
    PhoneSensoryTelemetry,
)
from sandbox.mind_twin.core.state import CognitiveStateVector, FocusItem
from sandbox.mind_twin.core.subconscious import (
    ConclusiveRealityProbe,
    EpiphanyChannel,
    NoveltyDetector,
    SubconsciousWorker,
)


def _safe_float(val: Any, default: float = 0.0, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        if min_val is not None:
            f = max(min_val, f)
        if max_val is not None:
            f = min(max_val, f)
        return f
    except (ValueError, TypeError):
        return default


@dataclass
class UnifiedCognitiveBootState:
    """The unitized mental state generated upon boot."""
    boot_timestamp: float = field(default_factory=time.time)
    turn_counter: int = 1
    session_id: str = "boot_session"
    active_topic: str = "general"
    working_notes_summary: str = ""

    # Cognitive Focus & 7-Slot Working Memory
    focus_spotlight: List[FocusItem] = field(default_factory=list)
    working_memory_frame: str = ""
    active_slots_count: int = 0
    suppressed_concepts_count: int = 0
    causal_invariants: List[str] = field(default_factory=list)
    revisit_queue: List[str] = field(default_factory=list)

    # Physical & Fleet Context
    somatic_context: str = "PNS: offline"
    fleet_capability: Optional[WholeSystemCapability] = None
    subconscious_status: str = "dormant"

    # Graph Topology Metrics
    graph_vertices_count: int = 0
    graph_edges_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boot_timestamp": self.boot_timestamp,
            "turn_counter": self.turn_counter,
            "session_id": self.session_id,
            "active_topic": self.active_topic,
            "working_notes_summary": self.working_notes_summary,
            "focus_spotlight": [
                {
                    "concept_id": f.concept_id,
                    "energy": round(f.energy, 3),
                    "primed_hops": f.primed_hops,
                    "last_activated": f.last_activated,
                }
                for f in self.focus_spotlight
            ],
            "active_slots_count": self.active_slots_count,
            "suppressed_concepts_count": self.suppressed_concepts_count,
            "subconscious_status": self.subconscious_status,
            "causal_invariants": self.causal_invariants,
            "revisit_queue": self.revisit_queue,
            "somatic_context": self.somatic_context,
            "fleet_capability": self.fleet_capability.to_dict() if self.fleet_capability else None,
            "graph_vertices_count": self.graph_vertices_count,
            "graph_edges_count": self.graph_edges_count,
        }

    def get_unified_boot_frame(self) -> str:
        """
        Synthesizes the complete unitized prompt injection frame (<250 tokens).
        Gives the LLM instant, complete awareness of mental state, cluster hardware,
        somatic conditions, working memory slots, and pending tasks.
        """
        top_focus = sorted(self.focus_spotlight, key=lambda x: x.energy, reverse=True)[:5]
        focus_str = ", ".join([f"{item.concept_id} (e={item.energy:.2f})" for item in top_focus]) if top_focus else "Cold"

        fleet_frame = self.fleet_capability.get_summary_frame() if self.fleet_capability else "Fleet: Standalone"
        revisits = "; ".join(self.revisit_queue[:3]) if self.revisit_queue else "None"
        invariants = "; ".join(self.causal_invariants[:3]) if self.causal_invariants else "Continuous bilateral autonomy"

        lines = [
            f"[UNITIZED MENTAL STATE BOOT (Turn {self.turn_counter})]",
            f"• Active Topic: {self.active_topic}",
            f"• Hot Spotlight: {focus_str}",
            f"• Working Memory (7-Target Gate): {self.active_slots_count}/7 slots active ({self.suppressed_concepts_count} latent suppressed)",
            f"• Somatic State: {self.somatic_context}",
            f"• Subconscious Status: {self.subconscious_status}",
            f"• {fleet_frame}",
            f"• Revisit Queue: {revisits}",
            f"• Invariants: {invariants}",
        ]
        if self.working_memory_frame:
            lines.append(f"• Dynamic Working Hierarchy:\n{self.working_memory_frame}")
        return "\n".join(lines)


class BootSynthesizer:
    """
    Master Ingestion and Boot Engine.
    Coordinates the 4 Ingestion Pillars, 7-Slot Working Memory Gate, and Subconscious Incubation.
    """

    def __init__(
        self,
        decay_alpha: float = 0.005,
        decay_beta: float = 0.3,
        activation_damping: float = 0.75,
        activation_threshold: float = 0.10,
        max_working_memory_slots: int = 7,
    ) -> None:
        self.hypergraph = Hypergraph(decay_alpha=decay_alpha, decay_beta=decay_beta)
        self.activation_engine = ActivationEngine(
            graph=self.hypergraph,
            default_decay=activation_damping,
            default_threshold=activation_threshold,
            max_hops=4,
        )
        self.pns_synthesizer = PhoneSensorySynthesizer(self.hypergraph)
        self.directional_gate = DirectionalGateEngine(max_slots=max_working_memory_slots)

        self.novelty_detector = NoveltyDetector()
        self.reality_probe = ConclusiveRealityProbe()
        self.epiphany_channel = EpiphanyChannel()
        self.subconscious_worker = SubconsciousWorker(
            graph=self.hypergraph,
            novelty_detector=self.novelty_detector,
            reality_probe=self.reality_probe,
            epiphany_channel=self.epiphany_channel,
        )

    # -------------------------------------------------------------------------
    # Pillar 1: Topical Notes Ingestion
    # -------------------------------------------------------------------------
    def ingest_notes(self, notes_data: Any) -> Tuple[str, str, List[str]]:
        """
        Ingests NotesManager instance or dict/list representation.
        Returns: (active_topic, clean_working_notes, revisit_list)
        """
        active_topic = "general"
        working_notes = ""
        revisits: List[str] = []

        if notes_data is None:
            return active_topic, working_notes, revisits

        raw_notes: List[Dict[str, Any]] = []

        # Check if NotesManager instance
        if hasattr(notes_data, "notes") and hasattr(notes_data, "current_topic"):
            active_topic = str(getattr(notes_data, "current_topic", "general") or "general")
            working_notes = str(getattr(notes_data, "working_notes", "") or "")
            raw_notes = [n.to_dict() if hasattr(n, "to_dict") else n for n in getattr(notes_data, "notes", [])]
        elif isinstance(notes_data, dict):
            active_topic = str(notes_data.get("current_topic") or notes_data.get("topic") or "general")
            working_notes = str(notes_data.get("working_notes") or "")
            managed = notes_data.get("managed_notes", {})
            if isinstance(managed, dict) and "notes" in managed and isinstance(managed["notes"], list):
                raw_notes = managed["notes"]
            elif "notes" in notes_data and isinstance(notes_data["notes"], list):
                raw_notes = notes_data["notes"]

        # Insert active topic vertex
        topic_vid = f"topic:{active_topic.strip().lower()}"
        self.hypergraph.add_vertex(
            v_id=topic_vid,
            label=f"Topic: {active_topic}",
            vtype="topic_anchor",
            base_energy=1.2,
            attributes={"topic": active_topic, "persistence": 0.95},
        )

        # Ingest working notes
        if working_notes.strip():
            wn_vid = "note:working_scratchpad"
            self.hypergraph.add_vertex(
                v_id=wn_vid,
                label="Working Scratchpad",
                vtype="working_note",
                base_energy=1.3,
                attributes={"content": working_notes[:200]},
            )
            self.hypergraph.add_hyperedge(
                sources=[topic_vid],
                targets=[wn_vid],
                relation="active_scratchpad",
                weight=1.5,
            )

        # Ingest individual note items
        for n in raw_notes:
            if not isinstance(n, dict):
                continue
            nid = str(n.get("id") or f"note_{len(self.hypergraph.vertices)}")
            content = str(n.get("content") or "").strip()
            topic = str(n.get("topic") or active_topic).strip().lower()
            status = str(n.get("status") or "working").strip().lower()
            if not content:
                continue

            # Topic vertex
            t_vid = f"topic:{topic}"
            if not self.hypergraph.has_vertex(t_vid):
                self.hypergraph.add_vertex(
                    v_id=t_vid,
                    label=f"Topic: {topic}",
                    vtype="topic_anchor",
                    base_energy=0.9,
                    attributes={"topic": topic},
                )

            # Energy weighting by status
            energy_map = {
                "working": 1.1,
                "get_back_to": 1.0,
                "think_about": 0.8,
                "reference": 0.5,
                "completed": 0.3,
            }
            n_energy = energy_map.get(status, 0.7)

            note_vid = f"note:{nid}"
            clean_label = (content[:45] + "...") if len(content) > 45 else content
            self.hypergraph.add_vertex(
                v_id=note_vid,
                label=clean_label,
                vtype="topical_note",
                base_energy=n_energy,
                attributes={"full_content": content, "topic": topic, "status": status},
            )

            # Hyperedge from Topic to Note
            self.hypergraph.add_hyperedge(
                sources=[t_vid],
                targets=[note_vid],
                relation="contains_note",
                weight=1.0,
            )

            if status == "get_back_to":
                revisits.append(content)

        return active_topic, working_notes, revisits

    # -------------------------------------------------------------------------
    # Pillar 2: Episodic Chat History Ingestion
    # -------------------------------------------------------------------------
    def ingest_history(self, history: Optional[List[Dict[str, Any]]], now: Optional[float] = None) -> int:
        """
        Ingests conversation history turns with temporal decay.
        Returns the total number of turns ingested.
        """
        if not history or not isinstance(history, list):
            return 0

        t_now = _safe_float(now, time.time())
        valid_turns = [turn for turn in history if isinstance(turn, dict)]
        total_turns = len(valid_turns)
        if total_turns == 0:
            return 0

        # Ingest the last 15 turns with recency retention
        recent_window = valid_turns[-15:]
        prev_turn_vid: Optional[str] = None

        for idx, turn in enumerate(recent_window):
            turn_num = (total_turns - len(recent_window)) + idx + 1
            tid = str(turn.get("turn_id") or f"turn_{turn_num}")
            role = str(turn.get("role") or "user")
            text = str(turn.get("text") or "")
            default_time = t_now - (len(recent_window) - idx) * 120.0
            turn_time = _safe_float(turn.get("timestamp"), default_time)

            delta_t = max(0.0, t_now - turn_time)
            decay = (1.0 + self.hypergraph.decay_alpha * delta_t) ** (-self.hypergraph.decay_beta)
            base_energy = _safe_float(0.9 * decay, 0.5, 0.01, 10.0)

            turn_vid = f"turn:{tid}"
            label = f"T{turn_num} ({role}): {text[:35]}..." if len(text) > 35 else f"T{turn_num} ({role})"
            self.hypergraph.add_vertex(
                v_id=turn_vid,
                label=label,
                vtype=f"history_{role}",
                base_energy=base_energy,
                attributes={"turn_num": turn_num, "role": role, "text": text[:200]},
            )

            # Link sequential turns
            if prev_turn_vid:
                self.hypergraph.add_hyperedge(
                    sources=[prev_turn_vid],
                    targets=[turn_vid],
                    relation="conversational_sequence",
                    weight=_safe_float(0.85 * decay, 0.5, 0.01, 5.0),
                )
            prev_turn_vid = turn_vid

        return total_turns

    # -------------------------------------------------------------------------
    # Pillar 3: Somatic PNS Sensory Ingestion
    # -------------------------------------------------------------------------
    def ingest_sensory(self, telemetry: Optional[PhoneSensoryTelemetry] = None) -> Tuple[List[str], str]:
        """
        Ingests phone peripheral telemetry into somatic anchors.
        Returns: (activated_somatic_labels, formatted_somatic_frame)
        """
        if telemetry is None:
            telemetry = PhoneSensoryTelemetry(
                timestamp=time.time(),
                lux=120.0,
                battery_pct=85.0,
                battery_charging=True,
                motion_magnitude=0.02,
                audio_amplitude_db=-45.0,
            )

        activated_nodes = self.pns_synthesizer.ingest(telemetry)
        frame = self.pns_synthesizer.build_somatic_frame()
        return activated_nodes, frame

    # -------------------------------------------------------------------------
    # Pillar 4: Fleet & Whole System Capability Ingestion
    # -------------------------------------------------------------------------
    def ingest_fleet(self, raw_fleet_snapshot: Optional[Dict[str, Any]] = None) -> WholeSystemCapability:
        """
        Ingests hardware capability, compute power, use cases, tooling, efficiency,
        and power profiles across all active nodes into the hypergraph.
        """
        system_cap = FleetTopologySynthesizer.synthesize_fleet(raw_fleet_snapshot)

        # 1. System Capability Vertex
        sys_vid = "cluster:system_capability"
        self.hypergraph.add_vertex(
            v_id=sys_vid,
            label=f"Whole System ({system_cap.online_nodes}/{system_cap.total_nodes} Nodes)",
            vtype="cluster_aggregate",
            base_energy=1.2,
            attributes={
                "total_cores": system_cap.total_cpu_cores,
                "total_ram_mb": system_cap.total_ram_mb,
                "efficiency_index": system_cap.system_efficiency_index,
            },
        )

        # 2. Ingest individual Node Capability Profiles
        for node in system_cap.node_profiles:
            n_vid = f"node:{node.node_id}"
            n_energy = 1.0 if node.status == "online" else 0.3

            self.hypergraph.add_vertex(
                v_id=n_vid,
                label=f"Node: {node.name}",
                vtype="fleet_node",
                base_energy=n_energy,
                attributes=node.to_dict(),
            )

            # Link node to cluster aggregate
            self.hypergraph.add_hyperedge(
                sources=[sys_vid],
                targets=[n_vid],
                relation="cluster_member",
                weight=1.0 if node.status == "online" else 0.2,
            )

            # Ingest Node Usecases
            for uc in node.usecases:
                uc_vid = f"usecase:{uc}"
                if not self.hypergraph.has_vertex(uc_vid):
                    self.hypergraph.add_vertex(
                        v_id=uc_vid,
                        label=f"Usecase: {uc.replace('_', ' ').title()}",
                        vtype="capability_usecase",
                        base_energy=0.8,
                    )
                self.hypergraph.add_hyperedge(
                    sources=[n_vid],
                    targets=[uc_vid],
                    relation="provides_usecase",
                    weight=0.9,
                )

            # Ingest Tooling
            for tool in node.tooling:
                tool_vid = f"tool:{tool}"
                if not self.hypergraph.has_vertex(tool_vid):
                    self.hypergraph.add_vertex(
                        v_id=tool_vid,
                        label=f"Tool: {tool}",
                        vtype="environment_tool",
                        base_energy=0.7,
                    )
                self.hypergraph.add_hyperedge(
                    sources=[n_vid],
                    targets=[tool_vid],
                    relation="has_tool",
                    weight=0.8,
                )

        return system_cap

    # -------------------------------------------------------------------------
    # Cross-Domain Interconnects (Synaptic Bridges)
    # -------------------------------------------------------------------------
    def bridge_cross_domain_hyperedges(self, active_topic: str) -> None:
        """
        Creates semantic hyperedges linking notes, nodes, and somatics.
        """
        t_vid = f"topic:{active_topic.strip().lower()}"
        host_vid = "node:toughbook-hub"
        phone_vid = "node:android-termux-localhost"
        ipad_vid = "node:ipad-ish-localhost"

        # Fleet topic -> satellite nodes
        if "fleet" in active_topic or "node" in active_topic:
            for n_vid in (phone_vid, ipad_vid):
                if self.hypergraph.has_vertex(n_vid) and self.hypergraph.has_vertex(t_vid):
                    self.hypergraph.add_hyperedge(
                        sources=[t_vid],
                        targets=[n_vid],
                        relation="topic_node_coupling",
                        weight=1.2,
                    )

        # Game Dev topic -> Host & iPad
        if "blender" in active_topic or "game" in active_topic:
            if self.hypergraph.has_vertex(host_vid) and self.hypergraph.has_vertex(t_vid):
                self.hypergraph.add_hyperedge(
                    sources=[t_vid],
                    targets=[host_vid],
                    relation="heavy_compute_affinity",
                    weight=1.1,
                )

        # Somatic desk anchor -> Host Toughbook
        desk_vid = "somatic:user_present_desk"
        if self.hypergraph.has_vertex(desk_vid) and self.hypergraph.has_vertex(host_vid):
            self.hypergraph.add_hyperedge(
                sources=[desk_vid],
                targets=[host_vid],
                relation="presence_alignment",
                weight=1.0,
            )

    # -------------------------------------------------------------------------
    # Pillar 5: Master Boot Execution
    # -------------------------------------------------------------------------
    def boot(
        self,
        notes_data: Any,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        sensory_telemetry: Optional[PhoneSensoryTelemetry] = None,
        fleet_snapshot: Optional[Dict[str, Any]] = None,
        session_id: str = "boot_session",
        current_user_prompt: str = "",
    ) -> UnifiedCognitiveBootState:
        """
        Executes complete multi-pillar boot sequence and returns the unitized mental state.
        Enforces 7-target working memory gating and checks subconscious novelty gating.
        """
        now = time.time()

        # 1. Ingest Notes
        active_topic, working_notes, revisits = self.ingest_notes(notes_data)

        # 2. Ingest History
        history_turns = self.ingest_history(chat_history or [], now=now)
        turn_counter = max(1, history_turns + 1)

        # 3. Ingest Sensory Telemetry
        somatic_labels, somatic_frame = self.ingest_sensory(sensory_telemetry)

        # 4. Ingest Fleet & Capabilities
        fleet_cap = self.ingest_fleet(fleet_snapshot)

        # 5. Build Synaptic Bridges
        self.bridge_cross_domain_hyperedges(active_topic)

        # 6. Spreading Activation Dynamics across Seed Vertices
        seed_boosts: Dict[str, float] = {}

        # Boost active topic & working notes
        topic_vid = f"topic:{active_topic.strip().lower()}"
        if self.hypergraph.has_vertex(topic_vid):
            seed_boosts[topic_vid] = 1.0
        if self.hypergraph.has_vertex("note:working_scratchpad"):
            seed_boosts["note:working_scratchpad"] = 1.2

        # Boost somatic anchors
        for slab in somatic_labels:
            if self.hypergraph.has_vertex(slab):
                seed_boosts[slab] = 0.8

        # Boost host node
        if self.hypergraph.has_vertex("node:toughbook-hub"):
            seed_boosts["node:toughbook-hub"] = 0.9

        # Spread activation
        profile: ActivationResult = self.activation_engine.spread(seeds=seed_boosts, t_now=now)

        # 7. Check Subconscious Novelty Gating Filter
        prompt_to_check = str(current_user_prompt or active_topic)
        is_novel, novelty_eval = self.subconscious_worker.check_and_ignite(
            task_prompt=prompt_to_check,
            active_topic=active_topic,
        )
        subconscious_status = "active_incubation" if is_novel else "dormant"

        # Drain any existing epiphanies from channel into working memory gate
        while not self.epiphany_channel.is_empty():
            ep = self.epiphany_channel.pop()
            if ep:
                self.directional_gate.traject_epiphany(
                    spark_label=ep.spark_name,
                    domain_bridge=ep.domain_bridge,
                    feasibility_score=ep.feasibility_score,
                    summary=ep.summary,
                )

        # 8. 7-Slot Working Memory Gating & Dynamic Depth Hierarchy
        self.directional_gate.update_trajectory(
            current_intent=prompt_to_check,
            active_topic=active_topic,
        )
        wm_snapshot: WorkingMemorySnapshot = self.directional_gate.gate_and_filter(
            graph=self.hypergraph,
            candidate_activations=profile.node_activations,
            t_now=now,
        )

        # 9. Extract Spotlight Items
        spotlight: List[FocusItem] = []
        for vid, score, label in profile.get_top_nodes(top_n=12):
            spotlight.append(FocusItem(
                concept_id=label,
                energy=_safe_float(score, 0.5, 0.0, 50.0),
                primed_hops=profile.hops_completed,
                last_activated=now,
            ))

        # Extract causal invariants
        invariants = [inv.summary for inv in profile.invariants[:4]]
        if not invariants:
            invariants = [f"Continuous operational focus on {active_topic}"]

        return UnifiedCognitiveBootState(
            boot_timestamp=now,
            turn_counter=turn_counter,
            session_id=str(session_id),
            active_topic=active_topic,
            working_notes_summary=working_notes,
            focus_spotlight=spotlight,
            working_memory_frame=wm_snapshot.get_cognitive_frame(),
            active_slots_count=len(wm_snapshot.slots),
            suppressed_concepts_count=wm_snapshot.suppressed_candidates_count,
            causal_invariants=invariants,
            revisit_queue=revisits[:5],
            somatic_context=somatic_frame,
            fleet_capability=fleet_cap,
            subconscious_status=subconscious_status,
            graph_vertices_count=len(self.hypergraph.vertices),
            graph_edges_count=len(self.hypergraph.edges),
        )

    @classmethod
    def boot_from_live_env(cls, current_user_prompt: str = "") -> UnifiedCognitiveBootState:
        """
        Convenience factory: Boots the synthesizer pulling directly from the live
        Toughbook environment: NotesManager, ChatStore, and Fleet nodes.
        """
        from gemini_app.fleet.nodes import get_fleet_snapshot
        from gemini_app.storage.chat_store import ChatStore
        from gemini_app.storage.notes_manager import NotesManager

        store = ChatStore()
        active_chat_id = store.load_state().get("active_chat", "")
        chat_data = store.load_chat(active_chat_id) if active_chat_id else {}

        notes_mgr = NotesManager.from_data(chat_data.get("notes_bundle") or chat_data.get("notes", ""))
        history = chat_data.get("history", [])
        fleet_snapshot = get_fleet_snapshot()

        synthesizer = cls()
        return synthesizer.boot(
            notes_data=notes_mgr,
            chat_history=history,
            fleet_snapshot=fleet_snapshot,
            session_id=active_chat_id or "live_toughbook_session",
            current_user_prompt=current_user_prompt,
        )
