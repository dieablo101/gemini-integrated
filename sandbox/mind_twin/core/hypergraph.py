"""
sandbox/mind_twin/core/hypergraph.py

Attributed Directed Hypergraph Mathematical Primitive.
G = (V, E, W, T)

A hypergraph where vertices represent semantic primitives (nodes, errors, protocols,
concepts, tools, code anchors) and directed hyperedges link multiple antecedents
to multiple consequences under defined causal/associative relations.
"""

from __future__ import annotations
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, Any, Iterable


@dataclass
class Vertex:
    """An atomic semantic entity in the cognitive graph."""
    id: str
    label: str
    vtype: str = "concept"
    base_energy: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 1
    attributes: Dict[str, Any] = field(default_factory=dict)

    def touch(self, t_now: Optional[float] = None) -> None:
        now = t_now if t_now is not None else time.time()
        self.last_accessed = now
        self.access_count += 1

    def ebbinghaus_energy(self, t_now: Optional[float] = None, alpha: float = 0.005, beta: float = 0.3) -> float:
        """
        Calculates retention energy under the Ebbinghaus Power-Law curve:
        R(t) = base_energy * (1 + alpha * delta_t)^(-beta)
        """
        now = t_now if t_now is not None else time.time()
        delta_t = max(0.0, now - self.last_accessed)
        retention = math.pow(1.0 + alpha * delta_t, -beta)
        # Scale retention with logarithmic frequency reinforcement
        frequency_boost = 1.0 + 0.1 * math.log(max(1, self.access_count))
        return self.base_energy * retention * frequency_boost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "vtype": self.vtype,
            "base_energy": self.base_energy,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Vertex:
        return cls(
            id=data["id"],
            label=data["label"],
            vtype=data.get("vtype", "concept"),
            base_energy=float(data.get("base_energy", 1.0)),
            created_at=float(data.get("created_at", time.time())),
            last_accessed=float(data.get("last_accessed", time.time())),
            access_count=int(data.get("access_count", 1)),
            attributes=dict(data.get("attributes", {})),
        )


@dataclass
class Hyperedge:
    """
    Directed Hyperedge connecting a set of source vertices (antecedents)
    to a set of target vertices (consequences) under a causal relation.
    """
    id: str
    sources: Set[str]
    targets: Set[str]
    relation: str = "associates_with"
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_reinforced: float = field(default_factory=time.time)
    reinforce_count: int = 1
    attributes: Dict[str, Any] = field(default_factory=dict)

    def effective_weight(self, t_now: Optional[float] = None, alpha: float = 0.005, beta: float = 0.3) -> float:
        """
        Effective associative weight incorporating temporal decay:
        w_eff = weight * (1 + alpha * delta_t)^(-beta)
        """
        now = t_now if t_now is not None else time.time()
        delta_t = max(0.0, now - self.last_reinforced)
        retention = math.pow(1.0 + alpha * delta_t, -beta)
        return self.weight * retention

    def reinforce(
        self,
        src_activation: float = 1.0,
        tgt_activation: float = 1.0,
        eta: float = 0.15,
        gamma: float = 0.02,
        t_now: Optional[float] = None,
    ) -> float:
        """
        Hebbian Plasticity update:
        Delta w = eta * (a_src * a_tgt) - gamma * w
        """
        now = t_now if t_now is not None else time.time()
        delta_w = eta * (src_activation * tgt_activation) - gamma * self.weight
        self.weight = max(0.001, self.weight + delta_w)
        self.last_reinforced = now
        self.reinforce_count += 1
        return self.weight

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sources": sorted(list(self.sources)),
            "targets": sorted(list(self.targets)),
            "relation": self.relation,
            "weight": self.weight,
            "created_at": self.created_at,
            "last_reinforced": self.last_reinforced,
            "reinforce_count": self.reinforce_count,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Hyperedge:
        return cls(
            id=data["id"],
            sources=set(data.get("sources", [])),
            targets=set(data.get("targets", [])),
            relation=data.get("relation", "associates_with"),
            weight=float(data.get("weight", 1.0)),
            created_at=float(data.get("created_at", time.time())),
            last_reinforced=float(data.get("last_reinforced", time.time())),
            reinforce_count=int(data.get("reinforce_count", 1)),
            attributes=dict(data.get("attributes", {})),
        )


class Hypergraph:
    """
    Mathematical Attributed Directed Hypergraph Engine: G = (V, E, W, T)
    Maintains fast dual indices for topological traversal and spreading activation.
    """

    def __init__(self, decay_alpha: float = 0.005, decay_beta: float = 0.3) -> None:
        self.decay_alpha = decay_alpha
        self.decay_beta = decay_beta
        self.vertices: Dict[str, Vertex] = {}
        self.edges: Dict[str, Hyperedge] = {}

        # Dual index: vertex_id -> set of hyperedge ids
        self._source_index: Dict[str, Set[str]] = {}
        self._target_index: Dict[str, Set[str]] = {}
        self._incident_index: Dict[str, Set[str]] = {}

    def apply_hebbian_reinforcement(
        self,
        sources: Iterable[str],
        targets: Iterable[str],
        eta: float = 0.15,
        t_now: Optional[float] = None,
    ) -> Optional[Hyperedge]:
        """
        Finds or instantiates hyperedge between sources and targets, then applies Hebbian reinforcement.
        """
        src_set = set(sources)
        tgt_set = set(targets)
        # Check if matching edge already exists
        for eid in self.edges:
            edge = self.edges[eid]
            if edge.sources == src_set and edge.targets == tgt_set:
                edge.reinforce(eta=eta, t_now=t_now)
                return edge
        # If not, add new edge with initial weight
        return self.add_hyperedge(sources=src_set, targets=tgt_set, relation="co_occurs_with", weight=1.0 + eta)

    def add_vertex(
        self,
        v_id: str,
        label: str,
        vtype: str = "concept",
        base_energy: float = 1.0,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Vertex:
        """Adds or updates a vertex in the hypergraph."""
        if v_id in self.vertices:
            v = self.vertices[v_id]
            v.label = label
            v.vtype = vtype
            if attributes:
                v.attributes.update(attributes)
            v.touch()
            return v

        v = Vertex(
            id=v_id,
            label=label,
            vtype=vtype,
            base_energy=base_energy,
            attributes=attributes or {},
        )
        self.vertices[v_id] = v
        self._source_index[v_id] = set()
        self._target_index[v_id] = set()
        self._incident_index[v_id] = set()
        return v

    def get_vertex(self, v_id: str) -> Optional[Vertex]:
        return self.vertices.get(v_id)

    def has_vertex(self, v_id: str) -> bool:
        return v_id in self.vertices

    def add_hyperedge(
        self,
        sources: Iterable[str],
        targets: Iterable[str],
        relation: str = "associates_with",
        weight: float = 1.0,
        edge_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Hyperedge:
        """
        Creates a directed hyperedge connecting source vertices to target vertices.
        Sources and targets must not be empty.
        """
        src_set = set(sources)
        tgt_set = set(targets)
        if not src_set:
            raise ValueError("Hyperedge must have at least one source vertex.")
        if not tgt_set:
            raise ValueError("Hyperedge must have at least one target vertex.")

        # Ensure all vertices exist
        for s in src_set:
            if s not in self.vertices:
                self.add_vertex(s, label=s, vtype="inferred")
        for t in tgt_set:
            if t not in self.vertices:
                self.add_vertex(t, label=t, vtype="inferred")

        e_id = edge_id or f"hedge_{uuid.uuid4().hex[:12]}"
        edge = Hyperedge(
            id=e_id,
            sources=src_set,
            targets=tgt_set,
            relation=relation,
            weight=weight,
            attributes=attributes or {},
        )
        self.edges[e_id] = edge

        # Update indices
        for s in src_set:
            self._source_index.setdefault(s, set()).add(e_id)
            self._incident_index.setdefault(s, set()).add(e_id)
        for t in tgt_set:
            self._target_index.setdefault(t, set()).add(e_id)
            self._incident_index.setdefault(t, set()).add(e_id)

        return edge

    def get_hyperedge(self, edge_id: str) -> Optional[Hyperedge]:
        return self.edges.get(edge_id)

    def incident_hyperedges(self, v_id: str, direction: str = "both") -> Set[str]:
        """
        Returns edge IDs incident to vertex v_id.
        direction: 'outgoing' (source), 'incoming' (target), or 'both'
        """
        if direction == "outgoing":
            return set(self._source_index.get(v_id, set()))
        elif direction == "incoming":
            return set(self._target_index.get(v_id, set()))
        else:
            return set(self._incident_index.get(v_id, set()))

    def neighbors(self, v_id: str, direction: str = "outgoing") -> Set[str]:
        """Returns adjacent vertices reached via incident hyperedges."""
        out = set()
        edge_ids = self.incident_hyperedges(v_id, direction=direction)
        for eid in edge_ids:
            edge = self.edges.get(eid)
            if not edge:
                continue
            if direction == "outgoing":
                out.update(edge.targets)
            elif direction == "incoming":
                out.update(edge.sources)
            else:
                out.update(edge.sources)
                out.update(edge.targets)
        out.discard(v_id)
        return out

    def prune_decayed_edges(
        self,
        retention_threshold: float = 0.05,
        t_now: Optional[float] = None,
    ) -> int:
        """
        Prunes hyperedges whose effective weight drops below threshold.
        Returns count of pruned edges.
        """
        now = t_now if t_now is not None else time.time()
        to_remove = [
            eid for eid, edge in self.edges.items()
            if edge.effective_weight(t_now=now) < retention_threshold
        ]
        for eid in to_remove:
            self.remove_hyperedge(eid)
        return len(to_remove)

    def remove_hyperedge(self, edge_id: str) -> bool:
        """Removes a hyperedge and updates internal dual indices."""
        edge = self.edges.pop(edge_id, None)
        if not edge:
            return False
        for s in edge.sources:
            if s in self._source_index:
                self._source_index[s].discard(edge_id)
            if s in self._incident_index:
                self._incident_index[s].discard(edge_id)
        for t in edge.targets:
            if t in self._target_index:
                self._target_index[t].discard(edge_id)
            if t in self._incident_index:
                self._incident_index[t].discard(edge_id)
        return True

    def extract_subgraph(self, vertex_ids: Iterable[str]) -> Hypergraph:
        """Extracts an induced sub-hypergraph over the given vertex IDs."""
        v_set = set(vertex_ids)
        sub = Hypergraph()
        for vid in v_set:
            v = self.get_vertex(vid)
            if v:
                sub.add_vertex(v.id, v.label, v.vtype, v.base_energy, dict(v.attributes))

        for eid, edge in self.edges.items():
            # Edge is included if all sources or targets intersect the set
            if edge.sources.issubset(v_set) and edge.targets.issubset(v_set):
                sub.add_hyperedge(
                    sources=edge.sources,
                    targets=edge.targets,
                    relation=edge.relation,
                    weight=edge.weight,
                    edge_id=edge.id,
                    attributes=dict(edge.attributes),
                )
        return sub

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "vertex_count": len(self.vertices),
            "edge_count": len(self.edges),
            "vertices": [v.to_dict() for v in self.vertices.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Hypergraph:
        hg = cls()
        for v_data in data.get("vertices", []):
            v = Vertex.from_dict(v_data)
            hg.vertices[v.id] = v
            hg._source_index[v.id] = set()
            hg._target_index[v.id] = set()
            hg._incident_index[v.id] = set()

        for e_data in data.get("edges", []):
            edge = Hyperedge.from_dict(e_data)
            hg.edges[edge.id] = edge
            for s in edge.sources:
                hg._source_index.setdefault(s, set()).add(edge.id)
                hg._incident_index.setdefault(s, set()).add(edge.id)
            for t in edge.targets:
                hg._target_index.setdefault(t, set()).add(edge.id)
                hg._incident_index.setdefault(t, set()).add(edge.id)

        return hg
