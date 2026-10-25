"""Upper Mind Cloud State Client & Local Shadow Graph Traversal.

Implements the 95% zero-API local shadow graph traversal protocol
paired with 5% strategic cloud synchronization for milestones, checkpoints,
and subconscious epiphany harvesting.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from gemini_app.config import GEMINI_HOME

logger = logging.getLogger("gemini.upper_mind")

UPPER_MIND_CACHE_DIR = GEMINI_HOME / "cache" / "upper_mind"
SHADOW_GRAPH_FILE = UPPER_MIND_CACHE_DIR / "shadow_graph.json"
EPIPHANY_CACHE_FILE = UPPER_MIND_CACHE_DIR / "epiphanies_cache.json"


class UpperMindClient:
    """Manages bilateral navigation between Local Mind and Upper Cloud Mind.

    Default mode is pure offline local shadow graph traversal (0 API calls).
    Cloud API calls are strictly gated and invoked only for milestone checkpoints,
    cold deep-history retrieval, and subconscious epiphany harvests.
    """

    def __init__(
        self,
        gemini_home: Optional[Path] = None,
        firestore_client: Optional[Any] = None,
        offline_mode: bool = False,
    ):
        self.home = gemini_home or GEMINI_HOME
        self.cache_dir = self.home / "cache" / "upper_mind"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.shadow_file = self.cache_dir / "shadow_graph.json"
        self.epiphany_file = self.cache_dir / "epiphanies_cache.json"

        self.db = firestore_client
        self.offline_mode = offline_mode or (self.db is None)
        self._shadow_graph: Dict[str, Any] = self._load_shadow_graph()

    # ----------------------------------------------------------------------
    # 95% OF TRAVERSAL: Local Shadow Graph (0 API Calls)
    # ----------------------------------------------------------------------

    def _load_shadow_graph(self) -> Dict[str, Any]:
        """Loads the local shadow graph from disk or initializes default empty structure."""
        if self.shadow_file.is_file():
            try:
                data = json.loads(self.shadow_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.warning(f"Failed to read local shadow graph: {e}")

        return {
            "version": 1,
            "last_synced_epoch": 0.0,
            "invariants": {},
            "topics": {},
            "synaptic_edges": [],
            "recent_checkpoints": [],
        }

    def _save_shadow_graph(self) -> None:
        """Atomically saves the local shadow graph to disk."""
        tmp = self.shadow_file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._shadow_graph, indent=2), encoding="utf-8")
            tmp.replace(self.shadow_file)
        except Exception as e:
            logger.error(f"Failed to save local shadow graph: {e}")
            if tmp.is_file():
                tmp.unlink(missing_ok=True)

    def walk_shadow_graph(
        self,
        topic: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Traverses the local memory topology completely offline (0 API calls).

        Returns relevant invariants, topic anchors, and cross-synaptic edges.
        """
        results: Dict[str, Any] = {
            "topic": topic,
            "invariants": {},
            "matched_nodes": [],
            "connected_edges": [],
        }

        # 1. Collect global invariants
        results["invariants"] = dict(self._shadow_graph.get("invariants", {}))

        # 2. Topic lookup
        topics_map = self._shadow_graph.get("topics", {})
        if topic and topic in topics_map:
            results["matched_nodes"].append({
                "id": topic,
                "type": "topic",
                "data": topics_map[topic],
            })

        # 3. Tag matching
        query_tags = set(t.lower() for t in (tags or []))
        if query_tags:
            for top_name, top_data in topics_map.items():
                node_tags = set(t.lower() for t in top_data.get("tags", []))
                if query_tags.intersection(node_tags):
                    if not any(n["id"] == top_name for n in results["matched_nodes"]):
                        results["matched_nodes"].append({
                            "id": top_name,
                            "type": "topic",
                            "data": top_data,
                        })

        # 4. Connected lateral edges
        active_ids = {n["id"] for n in results["matched_nodes"]}
        if topic:
            active_ids.add(topic)

        for edge in self._shadow_graph.get("synaptic_edges", []):
            if edge.get("from") in active_ids or edge.get("to") in active_ids:
                results["connected_edges"].append(edge)

        return results

    def add_shadow_topic(
        self,
        topic_name: str,
        summary: str,
        tags: Optional[List[str]] = None,
        anchors: Optional[List[str]] = None,
    ) -> None:
        """Locally caches or updates a topic node in the shadow graph."""
        topics = self._shadow_graph.setdefault("topics", {})
        topics[topic_name] = {
            "summary": summary,
            "tags": tags or [],
            "anchors": anchors or [],
            "updated_at": time.time(),
        }
        self._save_shadow_graph()

    def add_synaptic_edge(
        self,
        source: str,
        target: str,
        relation: str,
        weight: float = 1.0,
        origin: str = "local_synthesis",
    ) -> None:
        """Registers a lateral associative synaptic edge locally."""
        edges = self._shadow_graph.setdefault("synaptic_edges", [])
        # Check if edge already exists
        for e in edges:
            if e.get("from") == source and e.get("to") == target and e.get("rel") == relation:
                e["weight"] = max(e.get("weight", 1.0), weight)
                e["updated_at"] = time.time()
                self._save_shadow_graph()
                return

        edges.append({
            "from": source,
            "to": target,
            "rel": relation,
            "weight": weight,
            "origin": origin,
            "created_at": time.time(),
        })
        self._save_shadow_graph()

    def set_invariant(self, key: str, value: Any) -> None:
        """Sets a high-order invariant rule locally."""
        invariants = self._shadow_graph.setdefault("invariants", {})
        invariants[key] = {
            "value": value,
            "updated_at": time.time(),
        }
        self._save_shadow_graph()

    # ----------------------------------------------------------------------
    # 5% OF TRAVERSAL: Strategic Cloud Sync (Boundary Gated)
    # ----------------------------------------------------------------------

    def record_epoch_checkpoint(
        self,
        session_id: str,
        turn_counter: int,
        summary: str,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Pushes a compressed milestone checkpoint to the cloud stream.

        Only invoked at session boundaries or major architectural transitions.
        """
        checkpoint_entry = {
            "session_id": session_id,
            "turn_counter": turn_counter,
            "summary": summary,
            "tags": tags or [],
            "timestamp": time.time(),
        }

        # Always record locally in shadow history
        checkpoints = self._shadow_graph.setdefault("recent_checkpoints", [])
        checkpoints.append(checkpoint_entry)
        if len(checkpoints) > 100:
            checkpoints.pop(0)
        self._save_shadow_graph()

        # Cloud sync boundary
        if self.offline_mode or not self.db:
            return {
                "status": "cached_offline",
                "checkpoint": checkpoint_entry,
                "message": "Checkpoint recorded locally (Upper Mind client offline).",
            }

        try:
            doc_id = f"{session_id}_t{turn_counter:04d}"
            doc_ref = self.db.collection("stream").document("episodes").collection("checkpoints").document(doc_id)
            doc_ref.set(checkpoint_entry)
            return {
                "status": "synced",
                "doc_id": doc_id,
                "checkpoint": checkpoint_entry,
            }
        except Exception as e:
            logger.warning(f"Failed to push checkpoint to Upper Mind: {e}")
            return {
                "status": "offline_buffered",
                "checkpoint": checkpoint_entry,
                "error": str(e),
            }

    def sync_milestone_distribution(self, deploy_hosting: bool = True) -> Dict[str, Any]:
        """Automated milestone sync hook.
        
        Exports the current shadow graph, active topics, invariants, and subconscious
        state into public/api/ distribution and optionally deploys to Firebase Hosting.
        """
        results: Dict[str, Any] = {"status": "ok", "timestamp": time.time()}
        try:
            from scripts.export_public_nexus import export_distribution
            export_distribution()
            results["export"] = "success"
        except Exception as e:
            logger.warning(f"Failed to export public distribution: {e}")
            results["export"] = f"error: {e}"

        if deploy_hosting:
            try:
                import subprocess
                res = subprocess.run(
                    ["firebase", "deploy", "--only", "hosting"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                results["hosting_deploy"] = "success" if res.returncode == 0 else "failed"
                results["deploy_output"] = res.stdout[-200:] if res.stdout else res.stderr[-200:]
            except Exception as e:
                logger.warning(f"Firebase hosting deploy failed during milestone sync: {e}")
                results["hosting_deploy"] = f"error: {e}"

        return results

    def sync_invariants_to_cloud(self) -> Dict[str, Any]:
        """Pushes local shadow invariants to Firestore Bedrock Ledger."""
        if self.offline_mode or not self.db:
            return {"status": "offline", "count": len(self._shadow_graph.get("invariants", {}))}

        try:
            invariants = self._shadow_graph.get("invariants", {})
            vault_ref = self.db.collection("memory_vault").document("invariants")
            vault_ref.set(invariants, merge=True)
            return {"status": "synced", "count": len(invariants)}
        except Exception as e:
            logger.warning(f"Failed to sync invariants to Upper Mind: {e}")
            return {"status": "error", "error": str(e)}

    def pull_invariants_from_cloud(self) -> Dict[str, Any]:
        """Fetches invariants from cloud and reconciles with local shadow graph."""
        if self.offline_mode or not self.db:
            return {"status": "offline", "invariants": self._shadow_graph.get("invariants", {})}

        try:
            vault_ref = self.db.collection("memory_vault").document("invariants")
            doc = vault_ref.get()
            if doc.exists:
                cloud_inv = doc.to_dict() or {}
                # Merge into local shadow graph
                local_inv = self._shadow_graph.setdefault("invariants", {})
                for k, v in cloud_inv.items():
                    if k not in local_inv or v.get("updated_at", 0) > local_inv[k].get("updated_at", 0):
                        local_inv[k] = v
                self._save_shadow_graph()
                return {"status": "synced", "invariants": local_inv}
            return {"status": "empty", "invariants": {}}
        except Exception as e:
            logger.warning(f"Failed to pull invariants from Upper Mind: {e}")
            return {"status": "error", "error": str(e), "invariants": self._shadow_graph.get("invariants", {})}

    def fetch_unconsumed_epiphanies(self) -> List[Dict[str, Any]]:
        """Harvests insights produced asynchronously by the Subconscious Hearth."""
        if self.offline_mode or not self.db:
            # Check local offline epiphany cache if present
            if self.epiphany_file.is_file():
                try:
                    data = json.loads(self.epiphany_file.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        return [e for e in data if not e.get("consumed", False)]
                except Exception:
                    pass
            return []

        try:
            epiphanies_ref = (
                self.db.collection("subconscious")
                .document("hearth")
                .collection("epiphanies")
                .where("consumed", "==", False)
            )
            docs = epiphanies_ref.stream()
            results = []
            for doc in docs:
                item = doc.to_dict()
                item["id"] = doc.id
                results.append(item)

            # Update local cache
            self.epiphany_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
            return results
        except Exception as e:
            logger.warning(f"Failed to fetch epiphanies from Upper Mind: {e}")
            return []

    def mark_epiphany_consumed(self, epiphany_id: str) -> bool:
        """Marks an epiphany as consumed and integrated into local working memory."""
        # Update local cache
        if self.epiphany_file.is_file():
            try:
                data = json.loads(self.epiphany_file.read_text(encoding="utf-8"))
                for e in data:
                    if e.get("id") == epiphany_id:
                        e["consumed"] = True
                        e["consumed_at"] = time.time()
                self.epiphany_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass

        if self.offline_mode or not self.db:
            return True

        try:
            doc_ref = (
                self.db.collection("subconscious")
                .document("hearth")
                .collection("epiphanies")
                .document(epiphany_id)
            )
            doc_ref.update({"consumed": True, "consumed_at": time.time()})
            return True
        except Exception as e:
            logger.warning(f"Failed to mark epiphany consumed in cloud: {e}")
            return False
