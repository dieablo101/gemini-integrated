"""
sandbox/mind_twin/harness/seeder.py

Offline Knowledge Ingestion & Graph Compiler.
Parses sandbox/mind_twin/data/meta_snapshot.json (180 notes + anchors)
and compiles them into an Attributed Directed Hypergraph.
"""

from __future__ import annotations
import json
import os
import re
import sys
from typing import Dict, List, Set, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex, Hyperedge

SNAPSHOT_PATH = "sandbox/mind_twin/data/meta_snapshot.json"
COMPILED_GRAPH_PATH = "sandbox/mind_twin/data/graph_compiled.json"


def extract_entities(text: str) -> List[str]:
    """Extracts salient technical entities from text using pattern matching."""
    patterns = [
        r"(iPad(?:\s+\(iSH\))?)",
        r"(Android(?:\s+\(Termux\))?)",
        r"(Blender(?:\s+3D)?)",
        r"(Godot(?:\s+Engine)?)",
        r"(PyPI(?:\s+token)?)",
        r"(PBKDF2(?:\s+passkey)?)",
        r"(Mothership(?:\s+port\s+7331)?)",
        r"(Wingman(?:\s+port\s+8888)?)",
        r"(Emacs(?:\s+Coding\s+Dojo)?)",
        r"(Photon(?:\s+AI)?(?:\s+game\s+engine)?)",
        r"(Nomad\s+Sculpt)",
        r"(Material\s+Maker)",
        r"(Git(?:Hub)?(?:\s+repo)?)",
        r"(Ebbinghaus(?:\s+decay)?)",
        r"(Hypergraph)",
        r"(Spreading\s+Activation)",
        r"(Carrier\s+NAT|Errno\s+110)",
        r"(Emergency\s+Interrupt|Safe\s+Mode)",
        r"(P2P|Reverse\s+Polling)",
    ]

    entities = []
    for pat in patterns:
        matches = re.findall(pat, text, re.IGNORECASE)
        for m in matches:
            cleaned = m.strip()
            if cleaned and cleaned not in entities:
                entities.append(cleaned)
    return entities


def build_graph_from_snapshot(snapshot_path: str = SNAPSHOT_PATH) -> Hypergraph:
    if not os.path.exists(snapshot_path):
        raise FileNotFoundError(f"Snapshot file not found: {snapshot_path}")

    with open(snapshot_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    notes_data = meta.get("notes", {}).get("managed_notes", {}).get("notes", [])
    graph = Hypergraph()

    # Track topic vertices
    topics: Set[str] = set()

    for idx, note in enumerate(notes_data):
        topic = note.get("topic", "general").strip()
        content = note.get("content", "").strip()
        status = note.get("status", "active")
        author = note.get("author", "gemini")
        created_at = float(note.get("created_at", 0.0))

        if not content:
            continue

        topics.add(topic)
        topic_v_id = f"topic:{topic.lower().replace(' ', '_').replace('&', 'and')}"
        if not graph.has_vertex(topic_v_id):
            graph.add_vertex(topic_v_id, label=topic, vtype="topic", base_energy=1.5)

        note_v_id = f"note:{note.get('id', f'n_{idx}')}"
        graph.add_vertex(
            note_v_id,
            label=content[:60] + ("..." if len(content) > 60 else ""),
            vtype="note",
            base_energy=1.0,
            attributes={
                "full_content": content,
                "topic": topic,
                "status": status,
                "author": author,
                "created_at": created_at,
            },
        )

        # Extract entities from note content
        entities = extract_entities(content)
        entity_v_ids = []
        for ent in entities:
            ent_id = f"concept:{ent.lower().replace(' ', '_').replace('(', '').replace(')', '')}"
            if not graph.has_vertex(ent_id):
                graph.add_vertex(ent_id, label=ent, vtype="entity", base_energy=1.2)
            entity_v_ids.append(ent_id)

        # Create hyperedge linking topic + note to extracted concepts
        if entity_v_ids:
            # Topic + Note -> encapsulates -> Entities
            graph.add_hyperedge(
                sources=[topic_v_id, note_v_id],
                targets=entity_v_ids,
                relation="contextualizes",
                weight=1.2 if status == "working" else 0.9,
                attributes={"status": status, "author": author},
            )

            # Reciprocal associative cross-linking among entities if multiple exist
            if len(entity_v_ids) > 1:
                graph.add_hyperedge(
                    sources=[entity_v_ids[0]],
                    targets=entity_v_ids[1:],
                    relation="co_occurs_with",
                    weight=0.8,
                    attributes={"source_note": note_v_id},
                )
        else:
            # Fallback simple edge topic -> note
            graph.add_hyperedge(
                sources=[topic_v_id],
                targets=[note_v_id],
                relation="contains_note",
                weight=0.7,
            )

    return graph


def compile_and_save() -> Hypergraph:
    hg = build_graph_from_snapshot()
    data = hg.to_dict()
    os.makedirs(os.path.dirname(COMPILED_GRAPH_PATH), exist_ok=True)
    with open(COMPILED_GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return hg


if __name__ == "__main__":
    graph = compile_and_save()
    print(f"Successfully compiled hypergraph:")
    print(f"  • Vertices: {len(graph.vertices)}")
    print(f"  • Hyperedges: {len(graph.edges)}")
    print(f"  • Destination: {COMPILED_GRAPH_PATH}")
