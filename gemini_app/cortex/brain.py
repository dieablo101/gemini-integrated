"""
gemini_app/cortex/brain.py - Unified Bilateral Cortex Brain.

Unifies:
1. SQLite FTS5 Memory Index (Lexical & Full-Text Retrieval).
2. Relational Knowledge Cortex (Dissected Shards, Provenance, & Semantic Edges).
3. Attributed Directed Hypergraph (In-Memory Topological Traversal, Ebbinghaus Energy).
4. Subconscious Incubation Engine (Autonomous Cross-Domain Epiphany Synthesis).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from gemini_app.config import CHATS_DIR, GEMINI_HOME
from gemini_app.storage.memory_index import MemoryIndex
from gemini_app.cortex.chat_dissector import ChatDissector, ChatShard, ShardCategory, ShardDomain
from gemini_app.cortex.relational_cortex import RelationalCortex
from gemini_app.cortex.hypergraph import Hypergraph, Vertex, Hyperedge
from gemini_app.cortex.subconscious.subconscious_worker import SubconsciousWorker
from gemini_app.cortex.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from gemini_app.cortex.subconscious.novelty_detector import NoveltyDetector
from gemini_app.cortex.subconscious.resonance_gate import ResonanceGate
from gemini_app.cortex.subconscious.stillness_gate import StillnessGate
from gemini_app.cortex.subconscious.seed_packet import ObservationVector, SeedPacket

logger = logging.getLogger("gemini_app.cortex.brain")


class CortexBrain:
    """
    Central cognitive orchestrator linking storage, graph topology,
    and subconscious epiphany generation.
    """

    def __init__(
        self,
        home_dir: Optional[Path | str] = None,
        memory_index: Optional[MemoryIndex] = None,
        cortex: Optional[RelationalCortex] = None,
        graph: Optional[Hypergraph] = None,
        enable_subconscious: bool = False,
    ):
        self.home_dir = Path(home_dir) if home_dir else GEMINI_HOME
        self.graph_path = self.home_dir / "hypergraph.json"

        # 1. Lexical / FTS5 Memory Layer
        self.memory_index = memory_index or MemoryIndex(db_path=self.home_dir / "memory_index.db")

        # 2. Relational Knowledge Cortex
        cortex_db = str(self.home_dir / "cortex.db")
        self.cortex = cortex or RelationalCortex(db_path=cortex_db)
        self.dissector = ChatDissector()

        # 3. Attributed Directed Hypergraph
        self.graph = graph or Hypergraph()
        self._load_graph_if_exists()

        # 4. Subconscious Incubation Engine
        self.epiphany_channel = EpiphanyChannel(capacity=50)
        self.novelty_detector = NoveltyDetector()
        self.resonance_gate = ResonanceGate()
        self.stillness_gate = StillnessGate()
        self.subconscious_worker = SubconsciousWorker(
            graph=self.graph,
            novelty_detector=self.novelty_detector,
            epiphany_channel=self.epiphany_channel,
            resonance_gate=self.resonance_gate,
            stillness_gate=self.stillness_gate,
        )

        self._subconscious_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

        if enable_subconscious:
            self.start_subconscious()

    def _load_graph_if_exists(self) -> None:
        """Loads serialized hypergraph from disk if available."""
        if self.graph_path.exists():
            try:
                import json
                with open(self.graph_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.graph = Hypergraph.from_dict(data)
                logger.info(f"Loaded hypergraph with {len(self.graph.vertices)} vertices, {len(self.graph.edges)} edges.")
            except Exception as e:
                logger.warning(f"Could not load hypergraph from {self.graph_path}: {e}")

    def save_graph(self) -> bool:
        """Persists in-memory hypergraph to disk safely."""
        try:
            self.home_dir.mkdir(parents=True, exist_ok=True)
            temp_path = self.graph_path.with_suffix(".tmp")
            import json
            data = self.graph.to_dict()
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.graph_path)
            return True
        except Exception as e:
            logger.error(f"Failed to save hypergraph: {e}")
            return False

    def ingest_turn(
        self,
        chat_id: str,
        turn_number: int,
        role: str,
        content: str,
        turn_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Unified ingestion of a chat turn into:
        - FTS5 Memory Index
        - Relational Cortex (sharded + linked)
        - Attributed Directed Hypergraph
        - Subconscious observation seeds
        """
        t_now = timestamp or time.time()
        tid = turn_id or f"{chat_id}_{turn_number}_{int(t_now)}"

        with self._lock:
            # A. Index into FTS5
            try:
                self.memory_index.index_turn(
                    chat_id=chat_id,
                    turn_number=turn_number,
                    role=role,
                    content=content,
                    turn_id=tid,
                    timestamp=t_now,
                )
            except Exception as e:
                logger.warning(f"FTS5 indexing warning: {e}")

            # B. Dissect into atomic semantic shards
            shards = self.dissector.dissect_turn(
                turn_id=tid,
                turn_index=turn_number,
                role=role,
                text=content,
                timestamp=t_now,
            )

            # C. Batch insert and auto-link in Relational Cortex
            if shards:
                self.cortex.batch_insert_shards(shards)
                self.cortex.auto_link_shards(shards)

            # D. Insert / update hypergraph vertices & edges
            turn_v_id = f"turn:{tid}"
            domain = self.dissector.classify_domain(content).value
            self.graph.add_vertex(
                vertex_id=turn_v_id,
                label=f"Turn #{turn_number} ({role})",
                vtype="chat_turn",
                base_energy=1.2 if role == "user" else 1.0,
                attributes={
                    "chat_id": chat_id,
                    "turn_number": turn_number,
                    "role": role,
                    "domain": domain,
                    "snippet": content[:120].strip(),
                    "timestamp": t_now,
                },
            )

            # Link shards to turn vertex
            shard_ids = []
            for s in shards:
                s_vid = f"shard:{s.shard_id}"
                shard_ids.append(s_vid)
                self.graph.add_vertex(
                    vertex_id=s_vid,
                    label=s.summary or s.content[:40],
                    vtype="shard",
                    base_energy=s.salience,
                    attributes={
                        "domain": s.domain.value if hasattr(s.domain, "value") else str(s.domain),
                        "category": s.category.value if hasattr(s.category, "value") else str(s.category),
                        "keywords": s.keywords,
                        "sha256": s.sha256,
                    },
                )
                self.graph.add_hyperedge(
                    sources=[turn_v_id],
                    targets=[s_vid],
                    relation="contains_shard",
                    weight=s.salience,
                )

                # Connect keywords as concept vertices
                for kw in s.keywords:
                    kw_clean = kw.lower().strip()
                    if len(kw_clean) < 3:
                        continue
                    kw_vid = f"concept:{kw_clean}"
                    self.graph.add_vertex(
                        vertex_id=kw_vid,
                        label=kw.lower(),
                        vtype="concept",
                        base_energy=1.0,
                    )
                    self.graph.add_hyperedge(
                        sources=[s_vid],
                        targets=[kw_vid],
                        relation="references_concept",
                        weight=0.8,
                    )

            # E. Feed Subconscious Hearth with Seeds & Telemetry
            if shards:
                # If any unresolved items or high salience, drop into hearth
                if any(s.category == ShardCategory.UNRESOLVED_TODO for s in shards):
                    unresolved = [s.summary for s in shards if s.category == ShardCategory.UNRESOLVED_TODO]
                    self.subconscious_worker.hearth.drop_seed(
                        raw_thought="; ".join(unresolved),
                        conscious_context=content[:150],
                        domain_hints=[domain],
                    )
                # Touch stillness gate activity timestamp
                self.stillness_gate.record_activity()

            return {
                "turn_id": tid,
                "shards_count": len(shards),
                "graph_vertices": len(self.graph.vertices),
                "graph_edges": len(self.graph.edges),
            }

    def ingest_note(
        self,
        topic: str,
        content: str,
        status: str = "active",
        note_id: Optional[str] = None,
    ) -> str:
        """Ingests a project note into the hypergraph and relational cortex."""
        nid = note_id or f"note_{int(time.time()*1000)}"
        vid = f"note:{nid}"

        with self._lock:
            # Vertex for note
            self.graph.add_vertex(
                vertex_id=vid,
                label=f"Note: {topic}",
                vtype="note",
                base_energy=1.5 if status == "working" else 1.0,
                attributes={
                    "topic": topic,
                    "status": status,
                    "snippet": content[:120].strip(),
                },
            )

            # Topic vertex
            topic_vid = f"topic:{topic.lower().strip()}"
            self.graph.add_vertex(
                vertex_id=topic_vid,
                label=topic,
                vtype="topic",
                base_energy=1.5,
            )
            self.graph.add_hyperedge(
                sources=[vid],
                targets=[topic_vid],
                relation="annotates_topic",
                weight=1.0,
            )

            return vid

    def recall(
        self,
        query: str,
        max_results: int = 10,
        chat_id: Optional[str] = None,
        hop_depth: int = 1,
    ) -> Dict[str, Any]:
        """
        Unified multi-tiered recall:
        1. FTS5 exact & lexical matches
        2. Relational shard semantic edges
        3. Hypergraph associative neighborhood expansion
        """
        start_t = time.perf_counter()

        # Step 1: FTS5 Matches
        fts_matches = self.memory_index.search(query=query, chat_id=chat_id, limit=max_results)

        # Step 2: Extract query concepts
        tokens = [w.strip().lower() for w in query.split() if len(w.strip()) >= 3]
        matched_concepts: Set[str] = set()
        graph_associations: List[Dict[str, Any]] = []
        seen_assoc_ids: Set[str] = set()

        with self._lock:
            for token in tokens:
                matched_vids = []
                concept_vid = f"concept:{token}"
                if concept_vid in self.graph.vertices:
                    matched_vids.append(concept_vid)
                for vid, v in self.graph.vertices.items():
                    if vid not in matched_vids:
                        if token in v.label.lower() or token in v.attributes.get("keywords", []):
                            matched_vids.append(vid)

                for m_id in matched_vids:
                    matched_concepts.add(m_id)
                    # Add matching vertex itself if salient
                    mv = self.graph.get_vertex(m_id)
                    if mv and m_id not in seen_assoc_ids:
                        seen_assoc_ids.add(m_id)
                        graph_associations.append({
                            "vertex_id": mv.id,
                            "label": mv.label,
                            "vtype": mv.vtype,
                            "energy": round(mv.ebbinghaus_energy(), 3),
                            "domain": mv.attributes.get("domain", "general"),
                        })
                    neighbors = self.graph.get_neighbors(m_id)
                    for n_id in list(neighbors)[:5]:
                        if n_id not in seen_assoc_ids:
                            seen_assoc_ids.add(n_id)
                            nv = self.graph.get_vertex(n_id)
                            if nv:
                                graph_associations.append({
                                    "vertex_id": nv.id,
                                    "label": nv.label,
                                    "vtype": nv.vtype,
                                    "energy": round(nv.ebbinghaus_energy(), 3),
                                    "domain": nv.attributes.get("domain", "general"),
                                })

            # Multi-hop neighborhood expansion if matching vertices found
            if matched_concepts and hop_depth > 0:
                subg = self.graph.extract_subgraph(matched_concepts)
                sub_vertices = len(subg.vertices)
            else:
                sub_vertices = 0

        # Step 3: Query Relational Cortex shards
        relational_shards = self.cortex.search_shards(query, limit=5)

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0

        return {
            "query": query,
            "latency_ms": round(elapsed_ms, 2),
            "matches_count": len(fts_matches),
            "matches": fts_matches,
            "graph_associations": graph_associations[:10],
            "relational_shards_count": len(relational_shards),
            "relational_shards": [
                {
                    "shard_id": s.get("shard_id"),
                    "domain": s.get("domain"),
                    "category": s.get("category"),
                    "summary": s.get("summary"),
                    "salience": s.get("salience"),
                }
                for s in relational_shards
            ],
            "subgraph_nodes": sub_vertices,
        }

    def start_subconscious(self, cycle_interval: float = 2.0) -> None:
        """Launches the background subconscious incubation daemon thread."""
        if self._subconscious_thread and self._subconscious_thread.is_alive():
            return

        self._stop_event.clear()

        def _subconscious_loop():
            logger.info("Subconscious incubation thread started.")
            while not self._stop_event.is_set():
                try:
                    # Execute a single incubation step
                    with self._lock:
                        epiphany = self.subconscious_worker.incubate_step()
                    if epiphany:
                        logger.info(f"Subconscious epiphany surfaced: {epiphany.spark_name}")
                except Exception as e:
                    logger.debug(f"Subconscious loop perturbation: {e}")

                self._stop_event.wait(cycle_interval)
            logger.info("Subconscious incubation thread stopped.")

        self._subconscious_thread = threading.Thread(
            target=_subconscious_loop,
            name="CortexSubconsciousDaemon",
            daemon=True,
        )
        self._subconscious_thread.start()

    def stop_subconscious(self, timeout: float = 2.0) -> None:
        """Signals subconscious worker to stop cleanly."""
        self._stop_event.set()
        if self._subconscious_thread and self._subconscious_thread.is_alive():
            self._subconscious_thread.join(timeout=timeout)
            self._subconscious_thread = None

    def poll_epiphanies(self) -> List[Dict[str, Any]]:
        """Drains any available breakthrough epiphanies from the channel."""
        packets = self.epiphany_channel.drain_all()
        return [p.to_dict() for p in packets]

    def get_telemetry(self) -> Dict[str, Any]:
        """Provides instant bilateral cognitive telemetry."""
        with self._lock:
            v_count = len(self.graph.vertices)
            e_count = len(self.graph.edges)

        receptivity = self.stillness_gate.evaluate_receptivity()
        return {
            "vertices": v_count,
            "edges": e_count,
            "subconscious_running": bool(self._subconscious_thread and self._subconscious_thread.is_alive()),
            "epiphanies_pending": self.epiphany_channel.size(),
            "stillness_receptive": receptivity.is_receptive,
            "stillness_trigger": receptivity.trigger_type,
            "hearth_seeds": self.subconscious_worker.hearth.size(),
            "familiar_lexicon_count": len(self.novelty_detector.familiar_lexicon),
        }
