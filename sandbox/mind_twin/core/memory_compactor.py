"""
sandbox/mind_twin/core/memory_compactor.py

Deep Epistemic Drift & Hierarchical Memory Compaction Engine.
Manages:
1. Long-horizon (100,000-turn) Ebbinghaus decay simulation.
2. Anchor protection against catastrophic forgetting via periodic reinforcement.
3. Hierarchical graph compaction: collapses dense clusters of decayed transient
   vertices into high-level abstract summary hyperedges, preserving causal provenance.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sandbox.mind_twin.core.hypergraph import Hypergraph, Hyperedge, Vertex


class HierarchicalCompactor:
    """
    Autonomous Graph Compactor.
    Scans the hypergraph for clusters of decayed, low-energy vertices and collapses
    them into consolidated summary vertices, pruning clutter while maintaining causal edges.
    """

    def __init__(
        self,
        decay_energy_threshold: float = 0.08,
        min_cluster_size: int = 3,
    ) -> None:
        self.decay_energy_threshold = decay_energy_threshold
        self.min_cluster_size = min_cluster_size

    def compact(self, graph: Hypergraph, t_now: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes hierarchical compaction:
        1. Identifies vertices whose current ebbinghaus energy < decay_energy_threshold.
        2. Filters out anchor vertices (anchor vertices are never compacted).
        3. Groups decayed vertices by domain/vtype.
        4. For each cluster >= min_cluster_size:
           - Creates an abstract summary vertex.
           - Rewires external edges to/from cluster members to point to the summary vertex.
           - Removes the decayed leaf vertices.
        """
        now = t_now if t_now is not None else time.time()
        snapshots = graph.get_vertices_snapshot()

        decayed_candidates: Dict[str, List[str]] = {}
        preserved_anchors = 0

        for vid, v in snapshots.items():
            if v.vtype == "anchor" or v.attributes.get("is_anchor", False):
                preserved_anchors += 1
                continue

            current_e = v.ebbinghaus_energy(t_now=now)
            if current_e <= self.decay_energy_threshold:
                domain = v.attributes.get("topic") or v.vtype
                decayed_candidates.setdefault(domain, []).append(vid)

        collapsed_clusters = 0
        pruned_vertices_count = 0

        for domain, vids in decayed_candidates.items():
            if len(vids) < self.min_cluster_size:
                continue

            summary_vid = f"abstract_summary:{domain}:{int(now)}"
            summary_label = f"Consolidated Summary: {len(vids)} past events in '{domain}'"

            # Create abstract summary vertex
            graph.add_vertex(
                summary_vid,
                label=summary_label,
                vtype="abstract_summary",
                base_energy=0.25,
                attributes={
                    "domain": domain,
                    "compacted_nodes_count": len(vids),
                    "original_node_ids": vids[:15],
                    "compacted_at": now,
                },
            )

            # Rewire incident hyperedges
            for old_vid in vids:
                # Ingoing
                for in_eid in graph.incident_hyperedges(old_vid, direction="incoming"):
                    edge = graph.get_hyperedge(in_eid)
                    if edge:
                        edge.targets.discard(old_vid)
                        edge.targets.add(summary_vid)
                # Outgoing
                for out_eid in graph.incident_hyperedges(old_vid, direction="outgoing"):
                    edge = graph.get_hyperedge(out_eid)
                    if edge:
                        edge.sources.discard(old_vid)
                        edge.sources.add(summary_vid)

                # Remove old vertex from graph
                graph.remove_vertex(old_vid)
                pruned_vertices_count += 1

            collapsed_clusters += 1

        return {
            "preserved_anchors": preserved_anchors,
            "collapsed_clusters": collapsed_clusters,
            "pruned_vertices": pruned_vertices_count,
            "remaining_vertices": graph.vertex_count(),
        }


class LongHorizonDecaySimulator:
    """
    Simulates thousands of turns and tracks energy dynamics of anchors vs trivia.
    """

    @staticmethod
    def simulate_100k_turns(
        graph: Hypergraph,
        total_turns: int = 100_000,
        seconds_per_turn: float = 30.0,
        anchor_reinforce_interval: int = 1_000,
    ) -> Dict[str, Any]:
        """
        Fast discrete-time stepping for 100k turns:
        - Anchors are re-accessed and refreshed every anchor_reinforce_interval turns.
        - Transient trivia vertices are never accessed again after birth.
        """
        t_sim = 1_000_000.0  # arbitrary baseline epoch
        anchor_vids = [
            vid for vid, v in graph.get_vertices_snapshot().items()
            if v.vtype == "anchor" or v.attributes.get("is_anchor", False)
        ]

        turns_per_chunk = 500
        num_chunks = total_turns // turns_per_chunk

        for chunk in range(num_chunks):
            turn_now = chunk * turns_per_chunk
            t_sim += turns_per_chunk * seconds_per_turn

            # Reinforce anchors if interval reached
            if turn_now % anchor_reinforce_interval == 0:
                for avid in anchor_vids:
                    v = graph.get_vertex(avid)
                    if v:
                        v.last_accessed = t_sim
                        v.access_count += 1
                        v.base_energy = min(10.0, v.base_energy + 0.1)

        # Final evaluation at t_sim
        anchor_energies = {
            avid: graph.get_vertex(avid).ebbinghaus_energy(t_now=t_sim)
            for avid in anchor_vids if graph.get_vertex(avid)
        }

        transient_vids = [
            vid for vid, v in graph.get_vertices_snapshot().items()
            if vid not in anchor_vids and v.vtype != "abstract_summary"
        ]
        transient_energies = {
            tvid: graph.get_vertex(tvid).ebbinghaus_energy(t_now=t_sim)
            for tvid in transient_vids if graph.get_vertex(tvid)
        }

        return {
            "simulated_turns": total_turns,
            "simulated_duration_days": round((total_turns * seconds_per_turn) / 86400.0, 1),
            "anchor_count": len(anchor_energies),
            "avg_anchor_energy": sum(anchor_energies.values()) / max(1, len(anchor_energies)),
            "min_anchor_energy": min(anchor_energies.values()) if anchor_energies else 0.0,
            "transient_count": len(transient_energies),
            "max_transient_energy": max(transient_energies.values()) if transient_energies else 0.0,
            "avg_transient_energy": sum(transient_energies.values()) / max(1, len(transient_energies)),
            "sim_end_time": t_sim,
        }
