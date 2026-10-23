"""
sandbox/mind_twin/core/activation.py

ACT-R Spreading Activation & Cognitive Dynamics Engine.
Implements associative spreading activation over Attributed Directed Hypergraphs:
A_i = B_i + sum_j ( W_j * S_ji )

Enables rapid invariant retrieval and causal subgraph distillation without
costly exhaustive vector searches.
"""

from __future__ import annotations
import math
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple, Any

from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge


@dataclass
class InvariantFrame:
    """A distilled causal or associative frame extracted from the active subgraph."""
    edge_id: str
    relation: str
    sources: List[str]
    targets: List[str]
    confidence: float
    summary: str


@dataclass
class ActivationResult:
    """The result of a spreading activation cycle across the hypergraph."""
    query: str
    seed_nodes: Dict[str, float]
    node_activations: Dict[str, float]
    activated_edges: List[str]
    active_subgraph: Hypergraph
    invariants: List[InvariantFrame]
    hops_completed: int
    elapsed_ms: float
    total_energy: float

    def get_top_nodes(self, top_n: int = 10) -> List[Tuple[str, float, str]]:
        """Returns sorted (vertex_id, score, label)."""
        sorted_nodes = sorted(self.node_activations.items(), key=lambda x: x[1], reverse=True)
        out = []
        for vid, score in sorted_nodes[:top_n]:
            v = self.active_subgraph.get_vertex(vid)
            label = v.label if v else vid
            out.append((vid, score, label))
        return out


class ActivationEngine:
    """
    Executes ACT-R Spreading Activation over a Hypergraph.
    """

    def __init__(
        self,
        graph: Hypergraph,
        default_decay: float = 0.55,
        default_threshold: float = 0.18,
        max_hops: int = 3,
    ) -> None:
        self.graph = graph
        self.default_decay = default_decay
        self.default_threshold = default_threshold
        self.max_hops = max_hops

    def match_seeds(self, query: str, top_k: int = 8) -> Dict[str, float]:
        """
        Extracts semantic seed nodes from raw text query using token matching,
        label containment, and attribute matching.
        """
        tokens = set(re.findall(r"\w+", query.lower()))
        if not tokens:
            return {}

        seeds: Dict[str, float] = {}

        for vid, v in self.graph.vertices.items():
            vid_lower = vid.lower()
            label_lower = v.label.lower()
            vtype_lower = v.vtype.lower()

            match_score = 0.0

            # Exact token overlaps in label or ID
            v_tokens = set(re.findall(r"\w+", f"{vid_lower} {label_lower} {vtype_lower}"))
            overlap = tokens.intersection(v_tokens)
            if overlap:
                match_score += 1.0 * len(overlap)

            # Substring bonus
            if query.lower() in label_lower or label_lower in query.lower():
                match_score += 1.5

            for attr_k, attr_v in v.attributes.items():
                if isinstance(attr_v, str):
                    attr_tokens = set(re.findall(r"\w+", attr_v.lower()))
                    attr_overlap = tokens.intersection(attr_tokens)
                    if attr_overlap:
                        match_score += 0.5 * len(attr_overlap)

            if match_score > 0.0:
                # Modulate by vertex baseline Ebbinghaus retention energy
                retention = v.ebbinghaus_energy()
                initial_energy = match_score * (0.8 + 0.2 * retention)
                seeds[vid] = initial_energy

        # Normalize and select top_k
        if not seeds:
            return {}

        max_val = max(seeds.values())
        normalized = {k: v / max_val for k, v in seeds.items()}
        sorted_seeds = sorted(normalized.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return dict(sorted_seeds)

    def spread(
        self,
        seeds: Dict[str, float],
        query: str = "",
        max_hops: Optional[int] = None,
        decay: Optional[float] = None,
        threshold: Optional[float] = None,
        t_now: Optional[float] = None,
    ) -> ActivationResult:
        """
        Executes ACT-R spreading activation from seed vertices.
        """
        t0 = time.perf_counter()
        now = t_now if t_now is not None else time.time()
        hops = max_hops if max_hops is not None else self.max_hops
        decay_factor = decay if decay is not None else self.default_decay
        act_threshold = threshold if threshold is not None else self.default_threshold

        # Current total activation map
        total_activations: Dict[str, float] = {}

        # Front of newly injected energy per hop
        frontier: Dict[str, float] = {}

        for vid, energy in seeds.items():
            if vid in self.graph.vertices:
                total_activations[vid] = energy
                frontier[vid] = energy

        activated_edges: Set[str] = set()

        hop_count = 0
        for hop in range(hops):
            if not frontier:
                break
            hop_count += 1
            next_frontier: Dict[str, float] = {}

            # For every active vertex in the frontier, inspect incident outgoing edges
            candidate_edges: Set[str] = set()
            for vid in frontier:
                candidate_edges.update(self.graph.incident_hyperedges(vid, direction="outgoing"))

            for edge_id in candidate_edges:
                edge = self.graph.get_hyperedge(edge_id)
                if not edge:
                    continue

                # Measure antecedent satisfaction (geometric mean of source activations)
                src_energies = [
                    total_activations.get(s, 0.0) for s in edge.sources
                ]
                # If any source is completely unactivated, antecedent is weak
                # We compute geometric mean with floor 0.05 for partially active multi-source edges
                product = 1.0
                for se in src_energies:
                    product *= max(0.01, se)
                geometric_src_act = math.pow(product, 1.0 / len(edge.sources))

                # Effective edge weight under temporal decay
                w_eff = edge.effective_weight(t_now=now)

                # Transferred energy
                transfer = geometric_src_act * w_eff * math.pow(decay_factor, hop + 1)

                if transfer > 0.02:
                    activated_edges.add(edge_id)
                    # Reinforce edge Hebbian plasticity slightly on traversal
                    edge.reinforce(src_activation=geometric_src_act, tgt_activation=1.0, t_now=now)

                    # Spread to all target vertices
                    for tgt in edge.targets:
                        next_frontier[tgt] = next_frontier.get(tgt, 0.0) + transfer

            # Accumulate into total activations
            for vid, delta in next_frontier.items():
                total_activations[vid] = total_activations.get(vid, 0.0) + delta

            frontier = {
                vid: delta for vid, delta in next_frontier.items()
                if delta >= (act_threshold * 0.5)
            }

        # Attention spotlight filtering
        active_nodes = {
            vid: score for vid, score in total_activations.items()
            if score >= act_threshold
        }

        # Extract induced subgraph
        subgraph = self.graph.extract_subgraph(active_nodes.keys())

        # Distill causal invariants
        invariants = self._distill_invariants(subgraph, active_nodes)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        total_energy = sum(active_nodes.values())

        return ActivationResult(
            query=query,
            seed_nodes=seeds,
            node_activations=active_nodes,
            activated_edges=list(activated_edges),
            active_subgraph=subgraph,
            invariants=invariants,
            hops_completed=hop_count,
            elapsed_ms=elapsed_ms,
            total_energy=total_energy,
        )

    def _distill_invariants(
        self,
        subgraph: Hypergraph,
        activations: Dict[str, float],
    ) -> List[InvariantFrame]:
        """Distills active hyperedges into clear causal invariant frames."""
        invariants: List[InvariantFrame] = []

        for edge_id, edge in subgraph.edges.items():
            src_labels = [
                subgraph.get_vertex(s).label if subgraph.get_vertex(s) else s
                for s in edge.sources
            ]
            tgt_labels = [
                subgraph.get_vertex(t).label if subgraph.get_vertex(t) else t
                for t in edge.targets
            ]

            src_scores = [activations.get(s, 0.5) for s in edge.sources]
            confidence = (sum(src_scores) / len(src_scores)) * min(1.0, edge.weight)

            summary = f"[{' + '.join(src_labels)}] --({edge.relation})--> [{' + '.join(tgt_labels)}]"

            invariants.append(
                InvariantFrame(
                    edge_id=edge_id,
                    relation=edge.relation,
                    sources=src_labels,
                    targets=tgt_labels,
                    confidence=confidence,
                    summary=summary,
                )
            )

        # Sort by confidence
        invariants.sort(key=lambda x: x.confidence, reverse=True)
        return invariants
