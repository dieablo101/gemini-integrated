"""Automated Milestone, Checkpoint, and Upper Mind Shadow Graph Synchronizer.

Provides automated asynchronous export and synchronization across:
1. Local Shadow Graph (~/.gemini/cache/upper_mind/shadow_graph.json)
2. Web Nexus Public Distribution (public/api/graph.json, telemetry.json, epiphanies.json)
3. ~/.gemini Git Repository (origin main)
4. Firebase Hosting Edge (gemini-source.web.app)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from gemini_app.config import GEMINI_HOME
from gemini_app.cloud.upper_mind import UpperMindClient
from gemini_app.cloud.firestore_stream import FirestoreStreamBridge

logger = logging.getLogger("gemini.auto_sync")

_LAST_DEPLOY_TIMESTAMP: float = 0.0
_DEPLOY_LOCK = threading.Lock()
_DEPLOY_COOLDOWN_SECONDS: float = 45.0


def get_active_notes_and_topics() -> Dict[str, List[Dict[str, Any]]]:
    """Extracts active notes categorized by topic from local cognitive state."""
    state_file = GEMINI_HOME / "state.json"
    if not state_file.is_file():
        return {}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    active_chat = state.get("active_chat")
    if not active_chat:
        return {}

    meta_file = GEMINI_HOME / "chats" / active_chat / "meta.json"
    if not meta_file.is_file():
        return {}
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    notes_list = meta.get("notes", {}).get("notes", [])
    topics: Dict[str, List[Dict[str, Any]]] = {}
    for n in notes_list:
        top = n.get("topic", "general").strip().lower()
        topics.setdefault(top, []).append(n)
    return topics


def export_public_nexus_artifacts() -> bool:
    """Exports self-contained API JSON artifacts to public/api/."""
    try:
        from gemini_app.cloud.upper_mind_server import UpperMindServer
        import shutil

        repo_root = Path(__file__).resolve().parent.parent.parent
        public_api = repo_root / "public" / "api"
        public_api.mkdir(parents=True, exist_ok=True)

        srv = UpperMindServer()
        graph_data = srv._handle_graph(None, {})
        telemetry_data = srv._handle_telemetry(None, {})
        epiphanies_data = srv._handle_epiphanies(None, {})

        (public_api / "graph.json").write_text(json.dumps(graph_data, indent=2), encoding="utf-8")
        shutil.copy(str(public_api / "graph.json"), str(public_api / "graph"))

        (public_api / "telemetry.json").write_text(json.dumps(telemetry_data, indent=2), encoding="utf-8")
        shutil.copy(str(public_api / "telemetry.json"), str(public_api / "telemetry"))

        (public_api / "epiphanies.json").write_text(json.dumps(epiphanies_data, indent=2), encoding="utf-8")
        shutil.copy(str(public_api / "epiphanies.json"), str(public_api / "epiphanies"))

        logger.info("Public nexus distribution artifacts exported successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to export public nexus artifacts: {e}")
        return False


def sync_gemini_git_state(commit_msg: Optional[str] = None) -> bool:
    """Safely stages and commits ~/.gemini state changes, pushing to origin main."""
    try:
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(GEMINI_HOME),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status_res.returncode != 0:
            return False

        if not status_res.stdout.strip():
            logger.debug("~/.gemini git state already up to date.")
            return True

        # Stage and commit
        subprocess.run(["git", "add", "-A"], cwd=str(GEMINI_HOME), check=True, timeout=15)
        msg = commit_msg or f"chore(state): auto milestone checkpoint [{int(time.time())}]"
        subprocess.run(["git", "commit", "-m", msg], cwd=str(GEMINI_HOME), check=True, timeout=15)

        # Push to origin
        push_res = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(GEMINI_HOME),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if push_res.returncode == 0:
            logger.info("~/.gemini git state pushed cleanly to origin main.")
            return True
        else:
            logger.warning(f"Git push ~/.gemini failed: {push_res.stderr.strip()}")
            return False
    except Exception as e:
        logger.warning(f"Git sync ~/.gemini notice: {e}")
        return False


def _deploy_hosting_worker() -> None:
    """Background worker deploying updated distribution to Firebase Hosting."""
    global _LAST_DEPLOY_TIMESTAMP
    with _DEPLOY_LOCK:
        now = time.time()
        if now - _LAST_DEPLOY_TIMESTAMP < _DEPLOY_COOLDOWN_SECONDS:
            logger.debug("Firebase Hosting deploy skipped (cooldown active).")
            return

        _LAST_DEPLOY_TIMESTAMP = now

    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        res = subprocess.run(
            ["firebase", "deploy", "--only", "hosting"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode == 0:
            logger.info("Firebase Hosting deployed successfully to gemini-source.web.app.")
        else:
            logger.warning(f"Firebase deploy warning: {res.stderr.strip()}")
    except Exception as e:
        logger.warning(f"Firebase hosting deploy worker exception: {e}")


def sync_milestone_and_shadow_graph(
    reason: str = "milestone",
    deploy_hosting: bool = True,
    push_git: bool = True,
    async_deploy: bool = True,
) -> Dict[str, Any]:
    """Coordinates full milestone synchronization across shadow graph, git, and web nexus.

    1. Ingests all active topics and notes into local shadow graph.
    2. Writes updated API artifacts to public/api/.
    3. Backs up ~/.gemini git state to GitHub.
    4. Deploys updated observatory to Firebase Hosting (async/non-blocking).
    """
    client = UpperMindClient()
    raw_topics = get_active_notes_and_topics()

    topic_metadata: Dict[str, Dict[str, Any]] = {
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

    # Add active topics
    for top_name, notes in raw_topics.items():
        if len(notes) < 2 and top_name not in topic_metadata:
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

    # Ingest core associative synaptic edges
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
            origin="auto_milestone_sync"
        )

    client.set_invariant("last_milestone_checkpoint", {
        "reason": reason,
        "timestamp": time.time(),
        "topics_indexed": len(raw_topics),
    })

    # Export distribution artifacts
    artifacts_ok = export_public_nexus_artifacts()

    # Firestore realtime broadcast if bridge is online
    bridge = FirestoreStreamBridge()
    if bridge.is_connected:
        try:
            bridge.sync_console_state()
            bridge.publish_thought(
                tag="GROUNDED",
                text=f"Milestone checkpoint reached: {reason}",
                topic="uppermind web nexus & public face"
            )
        except Exception:
            pass

    # Git state sync
    git_ok = True
    if push_git:
        git_ok = sync_gemini_git_state(commit_msg=f"chore(state): auto milestone sync [{reason}]")

    # Firebase Hosting deployment
    if deploy_hosting:
        if async_deploy:
            t = threading.Thread(target=_deploy_hosting_worker, name="firebase-deploy-daemon", daemon=True)
            t.start()
        else:
            _deploy_hosting_worker()

    return {
        "status": "success",
        "reason": reason,
        "topics_count": len(raw_topics),
        "artifacts_exported": artifacts_ok,
        "git_synced": git_ok,
        "deploy_queued": deploy_hosting,
    }


class PeriodicSyncWatcher:
    """Background daemon periodically checking for milestone delta and triggering sync."""

    def __init__(self, interval_seconds: float = 120.0):
        self.interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_checked_turns: int = 0

    def _loop(self) -> None:
        while self._running:
            try:
                time.sleep(self.interval)
                if not self._running:
                    break

                state_file = GEMINI_HOME / "state.json"
                if not state_file.is_file():
                    continue

                state = json.loads(state_file.read_text(encoding="utf-8"))
                active_chat = state.get("active_chat")
                if not active_chat:
                    continue

                meta_file = GEMINI_HOME / "chats" / active_chat / "meta.json"
                if not meta_file.is_file():
                    continue

                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                current_turns = meta.get("storage", {}).get("total_turns", 0)

                # Trigger sync if turns increased by 3 or more since last sync
                if current_turns >= self._last_checked_turns + 3:
                    self._last_checked_turns = current_turns
                    sync_milestone_and_shadow_graph(
                        reason=f"periodic_progression_t{current_turns}",
                        deploy_hosting=True,
                        push_git=True,
                        async_deploy=True,
                    )
            except Exception as e:
                logger.debug(f"Periodic sync watcher note: {e}")

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="upper-mind-sync-watcher", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


# Global singleton instance
_watcher_instance: Optional[PeriodicSyncWatcher] = None


def start_auto_sync_watcher(interval_seconds: float = 120.0) -> PeriodicSyncWatcher:
    global _watcher_instance
    if _watcher_instance is None:
        _watcher_instance = PeriodicSyncWatcher(interval_seconds=interval_seconds)
        _watcher_instance.start()
    return _watcher_instance
