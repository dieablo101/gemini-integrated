"""
sandbox/mind_twin/harness/probe.py

Offline Cognitive Diagnostic Probe Harness.
Queries the compiled Attributed Directed Hypergraph using ACT-R Spreading Activation
and formats live diagnostic cards for bilateral inspection.
"""

from __future__ import annotations
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.activation import ActivationEngine

COMPILED_GRAPH_PATH = "sandbox/mind_twin/data/graph_compiled.json"


def load_compiled_graph() -> Hypergraph:
    if not os.path.exists(COMPILED_GRAPH_PATH):
        from sandbox.mind_twin.harness.seeder import compile_and_save
        return compile_and_save()

    with open(COMPILED_GRAPH_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Hypergraph.from_dict(data)


def run_probe(query: str, max_hops: int = 3, threshold: float = 0.15) -> str:
    graph = load_compiled_graph()
    engine = ActivationEngine(graph, max_hops=max_hops, default_threshold=threshold)

    seeds = engine.match_seeds(query, top_k=6)
    if not seeds:
        return f"[PROBE] No seed concepts matched for query: '{query}'"

    result = engine.spread(seeds, query=query, max_hops=max_hops, threshold=threshold)

    # Format diagnostic telemetry card
    top_nodes = result.get_top_nodes(top_n=6)
    lines = []
    lines.append("┌── [SANDBOX DIGITAL TWIN: COGNITIVE PROBE] " + "─" * 32 + "┐")
    lines.append(f"│ Query: {query[:65]}")
    lines.append(f"│ Seed Nodes Activated: {len(result.seed_nodes)} seed(s)")
    for s_id, s_energy in sorted(result.seed_nodes.items(), key=lambda x: x[1], reverse=True)[:4]:
        sv = graph.get_vertex(s_id)
        s_lbl = sv.label[:40] if sv else s_id
        lines.append(f"│   • {s_lbl} (Energy: {s_energy:.2f})")

    lines.append("├" + "─" * 74 + "┤")
    lines.append(
        f"│ Spreading Dynamics: {result.hops_completed} hops | "
        f"Latency: {result.elapsed_ms:.2f}ms | Active Energy: {result.total_energy:.2f}"
    )
    lines.append(
        f"│ Subgraph Focus: {len(result.node_activations)} nodes | "
        f"{len(result.activated_edges)} hyperedges traversed"
    )
    lines.append("├" + "─" * 74 + "┤")
    lines.append("│ Top Activated Entities in Working Spotlight:")
    for nid, score, label in top_nodes:
        lines.append(f"│   [{score:.3f}] {label[:64]}")

    if result.invariants:
        lines.append("├" + "─" * 74 + "┤")
        lines.append("│ Causal Invariant Frames Distilled:")
        for inv in result.invariants[:4]:
            lines.append(f"│   * {inv.summary[:68]}")

    lines.append("└" + "─" * 74 + "┘")
    return "\n".join(lines)


if __name__ == "__main__":
    test_query = sys.argv[1] if len(sys.argv) > 1 else "Blender Godot pipeline iPad sculpt"
    output = run_probe(test_query)
    print(output)
