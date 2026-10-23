"""
sandbox/mind_twin/core/directional_gate.py

7-Slot Directional Working Memory Gate & Dynamic Depth Engine.
Implements Miller's Law (7 ± 2 active chunks) with variable-depth relevance trees
and directional momentum to prevent cognitive flooding and attention diffusion.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex


@dataclass
class WorkingMemoryNode:
    """A single node inside a hierarchical working memory branch."""
    vid: str
    label: str
    vtype: str
    energy: float
    depth: int = 0
    relevance: float = 1.0
    children: List["WorkingMemoryNode"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vid": self.vid,
            "label": self.label,
            "vtype": self.vtype,
            "energy": round(self.energy, 3),
            "depth": self.depth,
            "relevance": round(self.relevance, 3),
            "children": [c.to_dict() for c in self.children],
        }

    def format_tree(self, prefix: str = "") -> List[str]:
        lines = [f"{prefix}└─ [{self.label}] (e={self.energy:.2f}, r={self.relevance:.2f})"]
        for child in self.children:
            lines.extend(child.format_tree(prefix + "   "))
        return lines


@dataclass
class WorkingMemorySlot:
    """One of at most 7 active slots in working memory."""
    slot_index: int
    target_id: str
    label: str
    domain: str
    root: WorkingMemoryNode
    momentum: float = 0.0
    is_epiphany: bool = False
    max_depth_reached: int = 0
    total_nodes_in_branch: int = 1

    @property
    def vertex_id(self) -> str:
        """Alias for target_id to support legacy tests and callers."""
        return self.target_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "target_id": self.target_id,
            "label": self.label,
            "domain": self.domain,
            "momentum": round(self.momentum, 3),
            "is_epiphany": self.is_epiphany,
            "max_depth_reached": self.max_depth_reached,
            "total_nodes_in_branch": self.total_nodes_in_branch,
            "root": self.root.to_dict(),
        }


@dataclass
class WorkingMemorySnapshot:
    """The constrained, non-flooded mental snapshot."""
    timestamp: float
    slots: List[WorkingMemorySlot]
    intent_vector_summary: str
    suppressed_candidates_count: int
    total_active_nodes: int
    directional_momentum: float

    def get_cognitive_frame(self) -> str:
        """Emits a concise, dense mental frame constrained to at most 7 targets."""
        lines = [
            f"[WORKING MEMORY FRAME: {len(self.slots)}/7 Slots Active | Momentum: {self.directional_momentum:.2f}]",
            f"• Directional Trajectory: {self.intent_vector_summary}",
        ]
        for s in self.slots:
            tag = "★ EPIPHANY" if s.is_epiphany else f"Depth {s.max_depth_reached}"
            lines.append(f"  Slot {s.slot_index + 1} [{s.domain}] {s.label} ({tag}, e={s.root.energy:.2f})")
            for c in s.root.children:
                for line in c.format_tree("    "):
                    lines.append(line)
        if self.suppressed_candidates_count > 0:
            lines.append(f"• Latent Suppressed: {self.suppressed_candidates_count} concepts dormant to prevent attention diffusion.")
        return "\n".join(lines)


class DirectionalGateEngine:
    """
    Directional Working Memory Gate.
    - Limits working memory to 7 concurrent targets (Miller's Law).
    - Governs hierarchy expansion via relevance checking and exponential depth resistance.
    - Tracks directional trajectory across conversational beats.
    - Manages trajection of subconscious epiphanies into active slots.
    """

    def __init__(
        self,
        max_slots: int = 7,
        max_depth_limit: int = 4,
        depth_resistance_gamma: float = 1.45,
        relevance_threshold: float = 0.20,
    ) -> None:
        self.max_slots = max_slots
        self.max_depth_limit = max_depth_limit
        self.depth_resistance_gamma = depth_resistance_gamma
        self.relevance_threshold = relevance_threshold

        self.current_slots: List[WorkingMemorySlot] = []
        self.trajectory_tokens: Set[str] = set()
        self.previous_tokens: Set[str] = set()
        self.momentum_score: float = 0.5

    def update_trajectory(self, current_intent: str, active_topic: str = "") -> None:
        """
        Updates directional intent vector based on dialogue flow.
        """
        words = set(re.findall(r"\w{3,}", f"{current_intent} {active_topic}".lower()))
        self.previous_tokens = set(self.trajectory_tokens)
        self.trajectory_tokens = words

        # Momentum is high if there is continuity with previous tokens
        if self.previous_tokens:
            overlap = len(self.trajectory_tokens.intersection(self.previous_tokens))
            continuity = overlap / max(1, len(self.trajectory_tokens.union(self.previous_tokens)))
            self.momentum_score = 0.4 + 0.6 * continuity
        else:
            self.momentum_score = 0.5

    def compute_relevance(self, label: str, vtype: str, attributes: Dict[str, Any]) -> float:
        """
        Calculates directional relevance against the current trajectory.
        """
        if not self.trajectory_tokens:
            return 0.5

        tokens = set(re.findall(r"\w{3,}", f"{label} {vtype}".lower()))
        for v in attributes.values():
            if isinstance(v, str):
                tokens.update(re.findall(r"\w{3,}", v.lower()))

        overlap = len(self.trajectory_tokens.intersection(tokens))
        if overlap == 0:
            return 0.15

        score = min(1.0, 0.35 + 0.25 * overlap)
        return score

    def gate_and_filter(
        self,
        graph: Hypergraph,
        candidate_activations: Dict[str, float],
        t_now: Optional[float] = None,
    ) -> WorkingMemorySnapshot:
        """
        Filters flooded graph activations through the 7-slot gate and builds dynamic depth trees.
        """
        now = t_now or time.time()

        # 1. Rank candidate root concepts based on competition metric
        scored_candidates: List[Tuple[str, float, float, Vertex]] = []
        for vid, energy in candidate_activations.items():
            if not isinstance(energy, (int, float)) or not math.isfinite(energy) or energy <= 0.0:
                continue
            vertex = graph.get_vertex(vid)
            if not vertex:
                continue

            relevance = self.compute_relevance(vertex.label, vertex.vtype, vertex.attributes)
            # Competition metric: Energy * Relevance * Momentum
            competition_score = energy * (0.4 + 0.6 * relevance) * (0.8 + 0.2 * self.momentum_score)
            if math.isfinite(competition_score):
                scored_candidates.append((vid, competition_score, relevance, vertex))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # 2. Select top 7 targets
        top_targets = scored_candidates[: self.max_slots]
        suppressed_count = max(0, len(scored_candidates) - len(top_targets))

        # 3. Dynamic Depth Expansion for each of the 7 slots
        active_slots: List[WorkingMemorySlot] = []

        for idx, (vid, comp_score, root_rel, vertex) in enumerate(top_targets):
            domain = vertex.vtype.replace("_", " ").title()
            root_node = WorkingMemoryNode(
                vid=vid,
                label=vertex.label,
                vtype=vertex.vtype,
                energy=comp_score,
                depth=0,
                relevance=root_rel,
            )

            # Drill down hierarchically based on relevance check
            max_depth, total_nodes = self._expand_depth(
                graph=graph,
                parent_node=root_node,
                current_depth=0,
                budget=comp_score,
                visited={vid},
                t_now=now,
            )

            slot = WorkingMemorySlot(
                slot_index=idx,
                target_id=vid,
                label=vertex.label,
                domain=domain,
                root=root_node,
                momentum=self.momentum_score,
                is_epiphany=False,
                max_depth_reached=max_depth,
                total_nodes_in_branch=total_nodes,
            )
            active_slots.append(slot)

        self.current_slots = active_slots

        total_active_nodes = sum(s.total_nodes_in_branch for s in active_slots)
        trajectory_summary = ", ".join(list(self.trajectory_tokens)[:6]) if self.trajectory_tokens else "Unanchored"

        return WorkingMemorySnapshot(
            timestamp=now,
            slots=active_slots,
            intent_vector_summary=trajectory_summary,
            suppressed_candidates_count=suppressed_count,
            total_active_nodes=total_active_nodes,
            directional_momentum=self.momentum_score,
        )

    def _expand_depth(
        self,
        graph: Hypergraph,
        parent_node: WorkingMemoryNode,
        current_depth: int,
        budget: float,
        visited: Set[str],
        t_now: float,
    ) -> Tuple[int, int]:
        """
        Recursively expands child thoughts if relevance crosses the exponential threshold.
        Threshold = relevance_threshold * (gamma ^ depth)
        """
        if current_depth >= self.max_depth_limit:
            return current_depth, 1

        if not math.isfinite(budget) or budget <= 0.0:
            return current_depth, 1

        required_relevance = self.relevance_threshold * math.pow(self.depth_resistance_gamma, current_depth + 1)
        if budget < required_relevance:
            return current_depth, 1

        # Inspect incident outgoing edges from current parent
        edges = graph.incident_hyperedges(parent_node.vid, direction="outgoing")
        candidates: List[Tuple[str, Vertex, float]] = []

        for eid in edges:
            edge = graph.get_hyperedge(eid)
            if not edge:
                continue
            for tgt in edge.targets:
                if tgt in visited:
                    continue
                tgt_v = graph.get_vertex(tgt)
                if not tgt_v:
                    continue
                rel = self.compute_relevance(tgt_v.label, tgt_v.vtype, tgt_v.attributes)
                transferred_budget = budget * edge.effective_weight(t_now=t_now) * rel
                if transferred_budget >= required_relevance:
                    candidates.append((tgt, tgt_v, transferred_budget))

        # Sort candidates to expand only the most relevant (max 3 branches per level)
        candidates.sort(key=lambda x: x[2], reverse=True)
        max_reached = current_depth
        node_count = 1

        for tgt, tgt_v, sub_budget in candidates[:3]:
            visited.add(tgt)
            rel = self.compute_relevance(tgt_v.label, tgt_v.vtype, tgt_v.attributes)
            child_node = WorkingMemoryNode(
                vid=tgt,
                label=tgt_v.label,
                vtype=tgt_v.vtype,
                energy=sub_budget,
                depth=current_depth + 1,
                relevance=rel,
            )
            parent_node.children.append(child_node)

            deepest, sub_nodes = self._expand_depth(
                graph=graph,
                parent_node=child_node,
                current_depth=current_depth + 1,
                budget=sub_budget,
                visited=visited,
                t_now=t_now,
            )
            max_reached = max(max_reached, deepest)
            node_count += sub_nodes

        return max_reached, node_count

    def traject_epiphany(
        self,
        spark_label: str,
        domain_bridge: List[str],
        feasibility_score: float,
        summary: str,
    ) -> bool:
        """
        Injects a verified subconscious epiphany into the 7-slot working memory.
        If all 7 slots are occupied, demotes the lowest energy / lowest momentum slot.
        """
        if not isinstance(feasibility_score, (int, float)) or not math.isfinite(feasibility_score) or feasibility_score < 0.70:
            return False

        epiphany_node = WorkingMemoryNode(
            vid=f"epiphany:{int(time.time())}",
            label=spark_label,
            vtype="epiphany_spark",
            energy=2.0 * feasibility_score,
            depth=0,
            relevance=1.0,
        )
        # Add summary child
        epiphany_node.children.append(
            WorkingMemoryNode(
                vid=f"epiphany_desc:{int(time.time())}",
                label=summary[:60],
                vtype="actionable_insight",
                energy=1.5 * feasibility_score,
                depth=1,
                relevance=0.9,
            )
        )

        domain_str = " + ".join(domain_bridge) if domain_bridge else "Creative Epiphany"

        # If we have free slots under 7:
        if len(self.current_slots) < self.max_slots:
            new_slot = WorkingMemorySlot(
                slot_index=len(self.current_slots),
                target_id=epiphany_node.vid,
                label=spark_label,
                domain=domain_str,
                root=epiphany_node,
                momentum=1.0,
                is_epiphany=True,
                max_depth_reached=1,
                total_nodes_in_branch=2,
            )
            self.current_slots.append(new_slot)
            return True

        # If full (7 slots), locate the slot with lowest energy root
        # FAILSAFE / IMMUNITY: Slot 0 (Foreground Focus) is anchored and protected from eviction
        # unless incoming epiphany energy exceeds the active focus root energy by a factor of 1.5x.
        lowest_idx = -1
        min_energy = float("inf")
        start_idx = 1 if len(self.current_slots) > 1 else 0

        for i in range(start_idx, len(self.current_slots)):
            s = self.current_slots[i]
            # Epiphanies have temporary immunity unless another higher epiphany arrives
            effective_e = s.root.energy * (0.5 if not s.is_epiphany else 1.2)
            if effective_e < min_energy:
                min_energy = effective_e
                lowest_idx = i

        if lowest_idx == -1:
            # Fallback if only 1 slot exists
            if epiphany_node.energy <= self.current_slots[0].root.energy * 1.5:
                return False
            lowest_idx = 0

        # Replace lowest slot
        replaced_slot = WorkingMemorySlot(
            slot_index=lowest_idx,
            target_id=epiphany_node.vid,
            label=spark_label,
            domain=domain_str,
            root=epiphany_node,
            momentum=1.0,
            is_epiphany=True,
            max_depth_reached=1,
            total_nodes_in_branch=2,
        )
        self.current_slots[lowest_idx] = replaced_slot
        return True
