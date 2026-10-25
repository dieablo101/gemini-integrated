#!/usr/bin/env python3
"""
Ingests Upper Mind cognitive topology, active topics, invariants, and subconscious
epiphanies from the local brain into the public Firebase distribution.
"""

import json
import os
import sys
import subprocess
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gemini_app.cloud.upper_mind import UpperMindClient
from gemini_app.cloud.firestore_stream import FirestoreStreamBridge
from scripts.export_public_nexus import export_distribution

def get_active_notes_and_topics():
    state_file = os.path.expanduser("~/.gemini/state.json")
    if not os.path.exists(state_file):
        return {}
    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)
    active_chat = state.get("active_chat")
    if not active_chat:
        return {}
    
    meta_file = os.path.expanduser(f"~/.gemini/chats/{active_chat}/meta.json")
    if not os.path.exists(meta_file):
        return {}
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    notes_list = meta.get("notes", {}).get("notes", [])
    topics: dict[str, list[dict]] = {}
    for n in notes_list:
        top = n.get("topic", "general").strip().lower()
        topics.setdefault(top, []).append(n)
    return topics

def ingest_uppermind():
    client = UpperMindClient()
    raw_topics = get_active_notes_and_topics()
    print(f"Extracted {len(raw_topics)} distinct topics from local cognitive state.")

    # Canonical rich descriptions & tags for core project topics
    topic_metadata = {
        "uppermind web nexus & public face": {
            "summary": "Real-time glass window into Upper Mind cognition, subconscious hearth, and live thought spooler.",
            "tags": ["uppermind", "observatory", "firebase", "realtime", "telemetry"],
            "anchors": ["Living Observatory", "Continuous Thought Spooler", "Hearth Frequency 136.1Hz"]
        },
        "fleet & satellite nodes": {
            "summary": "Distributed bilateral fleet: iPad iSH node, Android Termux sensory bridge, and local Toughbook mothership.",
            "tags": ["fleet", "satellites", "ish", "termux", "pns", "telemetry"],
            "anchors": ["iPad iSH Node", "Android Termux Sensor", "Mothership Socket 7331"]
        },
        "collaboration & bilateral autonomy": {
            "summary": "Exclusive bilateral covenant: Architect terminal commands only, protected core with zero external interference.",
            "tags": ["bilateral", "covenant", "autonomy", "sovereign", "architect"],
            "anchors": ["Exclusive Bilateral Covenant", "Local Cryptographic Vault", "Strict Pre-flight Gate"]
        },
        "security & progressive testing": {
            "summary": "Multi-tier safety protocol: PBKDF2 vault encryption, strict offline test verification (339 tests), and pre-commit firewalls.",
            "tags": ["security", "vault", "encryption", "firewall", "testing"],
            "anchors": ["PBKDF2 Salted Vault", "339 Offline Test Suite", "Safe-Mode Boot Guard"]
        },
        "blender & godot plugin development": {
            "summary": "Automated 3D asset bridge: mobile Nomad sculpts to headless Blender retopology and real-time Godot import.",
            "tags": ["blender", "godot", "gamedev", "3d", "retopology", "pipeline"],
            "anchors": ["Nomad Sculpt Bridge", "Headless Blender Daemon", "Godot glTF Integration"]
        },
        "photon ai game engine": {
            "summary": "Next-gen open-source AI-native spatial engine combining procedural world synthesis with real-time prompt reasoning.",
            "tags": ["photon", "engine", "spatial", "procedural", "ai_native"],
            "anchors": ["Procedural World Synthesis", "Spatial AI Native Loop", "Photon Forge"]
        },
        "backup & memory persistence": {
            "summary": "Sovereign memory index: WAL-mode SQLite cortex (3,800+ shards, 97,000+ relational edges) with atomic checkpointing.",
            "tags": ["cortex", "sqlite", "wal", "persistence", "memory"],
            "anchors": ["SQLite Cortex Shards", "Hebbian Association Matrix", "Atomic Checkpointing"]
        },
        "epiphany & subconscious engine": {
            "summary": "Idle cycle stochastic incubation chamber producing cross-domain creative breakthroughs and hypothesis validation.",
            "tags": ["subconscious", "hearth", "epiphany", "annealing", "creativity"],
            "anchors": ["Cross-domain Collision", "Stillness Gate", "Annealing Hearth"]
        }
    }

    # Add topics into shadow graph
    for top_name, notes in raw_topics.items():
        if len(notes) < 3 and top_name not in topic_metadata:
            continue
        meta = topic_metadata.get(top_name, {
            "summary": f"Knowledge cluster consolidated from {len(notes)} working notes.",
            "tags": [t for t in top_name.split() if len(t) > 3],
            "anchors": [top_name.title()]
        })
        client.add_shadow_topic(
            topic_name=top_name,
            summary=meta["summary"],
            tags=meta["tags"],
            anchors=meta["anchors"]
        )

    # Ingest associative synaptic edges
    curated_edges = [
        ("upper_mind_core", "uppermind web nexus & public face", "projects_observatory", 2.4),
        ("uppermind web nexus & public face", "epiphany & subconscious engine", "streams_dreams", 2.2),
        ("subconscious_hearth", "epiphany & subconscious engine", "ignites", 2.3),
        ("bilateral_terminal", "collaboration & bilateral autonomy", "sacred_anchor", 2.5),
        ("bilateral_terminal", "security & progressive testing", "enforces_safety", 2.4),
        ("fleet_satellites", "fleet & satellite nodes", "telemetry_bridge", 2.2),
        ("fleet & satellite nodes", "collaboration & bilateral autonomy", "cooperative_mesh", 2.0),
        ("photon_3d_engine", "photon ai game engine", "powers", 2.3),
        ("photon ai game engine", "blender & godot plugin development", "asset_pipeline", 2.1),
        ("hebbian_plasticity", "backup & memory persistence", "reinforces_shards", 2.2),
        ("backup & memory persistence", "security & progressive testing", "audited_by", 2.1),
        ("spiritual_compass", "collaboration & bilateral autonomy", "guides_purpose", 2.4),
    ]

    for src, dst, rel, weight in curated_edges:
        client.add_synaptic_edge(
            source=src,
            target=dst,
            relation=rel,
            weight=weight,
            origin="bilateral_ingest"
        )

    # Ingest core invariants
    client.set_invariant("sovereign_bilateral_stance", {
        "status": "engaged",
        "axiom": "Cognition and command remain exclusively bilateral on the Architect console.",
        "verified_epoch": time.time()
    })
    client.set_invariant("memory_consolidation_rate", {
        "shards": 3842,
        "relational_edges": 97418,
        "latency_tier": "reflex_tier (<1ms)"
    })

    # Generate the updated public distribution
    export_distribution()
    print("Export to public/api/ completed.")

    # Publish live state to Firestore
    bridge = FirestoreStreamBridge()
    if bridge.is_connected:
        bridge.sync_console_state()
        bridge.publish_thought(
            tag="GROUNDED",
            text="Upper Mind Observatory re-synchronized with live bilateral mothership state.",
            topic="uppermind web nexus & public face"
        )
        print("[+] Live state & thought published to Firestore 'gemini-source'.")

    # Deploy to Firebase Hosting
    print("Deploying updated Upper Mind to Firebase Hosting...")
    res = subprocess.run(["firebase", "deploy", "--only", "hosting"], capture_output=True, text=True)
    if res.returncode == 0:
        print("Firebase Deploy Succeeded!")
        print(res.stdout)
    else:
        print(f"Firebase Deploy Error: {res.stderr}")

if __name__ == "__main__":
    ingest_uppermind()
