"""
relational_cortex.py - SQLite Relational Knowledge Cortex.

Provides indexed, relational, and hyper-associative storage for atomic
chat shards, replacing flat context dumps with sub-millisecond epistemic queries.
"""

from __future__ import annotations
import sqlite3
import json
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
from sandbox.mind_twin.core.chat_dissector import ChatShard, ShardDomain, ShardCategory


class RelationalCortex:
    """
    Manages an isolated SQLite store of dissected chat shards, provenance chains,
    and associative relational edges.
    """
    def __init__(self, db_path: str = "sandbox/mind_twin/data/cortex_test.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    from contextlib import contextmanager

    @contextmanager
    def _connection_scope(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection_scope() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_shards (
                shard_id TEXT PRIMARY KEY,
                source_turn_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                domain TEXT NOT NULL,
                category TEXT NOT NULL,
                salience REAL NOT NULL,
                content TEXT NOT NULL,
                summary TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                timestamp REAL NOT NULL,
                epistemic_decay_rate REAL NOT NULL,
                reinforcement_count INTEGER NOT NULL,
                sha256 TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relational_edges (
                source_shard TEXT NOT NULL,
                target_shard TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY (source_shard, target_shard),
                FOREIGN KEY (source_shard) REFERENCES chat_shards (shard_id) ON DELETE CASCADE,
                FOREIGN KEY (target_shard) REFERENCES chat_shards (shard_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS provenance_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                shard_id TEXT NOT NULL,
                source_turn_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                domain TEXT NOT NULL,
                category TEXT NOT NULL,
                recorded_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_shards_domain_salience ON chat_shards (domain, salience DESC);
            CREATE INDEX IF NOT EXISTS idx_shards_category_salience ON chat_shards (category, salience DESC);
            CREATE INDEX IF NOT EXISTS idx_shards_turn_index ON chat_shards (turn_index ASC);
            CREATE INDEX IF NOT EXISTS idx_shards_timestamp ON chat_shards (timestamp ASC);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON relational_edges (source_shard);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON relational_edges (target_shard);
            """)

    def insert_shard(self, shard: ChatShard) -> None:
        self.batch_insert_shards([shard])

    def batch_insert_shards(self, shards: List[ChatShard]) -> None:
        if not shards:
            return
        with self._connection_scope() as conn:
            now = time.time()
            shard_rows = []
            provenance_rows = []
            for s in shards:
                kw_json = json.dumps(s.keywords)
                shard_rows.append((
                    s.shard_id, s.source_turn_id, s.turn_index, s.role,
                    s.domain.value if isinstance(s.domain, ShardDomain) else s.domain,
                    s.category.value if isinstance(s.category, ShardCategory) else s.category,
                    s.salience, s.content, s.summary, kw_json, s.timestamp,
                    s.epistemic_decay_rate, s.reinforcement_count, s.sha256
                ))
                provenance_rows.append((
                    s.shard_id, s.source_turn_id, s.sha256,
                    s.domain.value if isinstance(s.domain, ShardDomain) else s.domain,
                    s.category.value if isinstance(s.category, ShardCategory) else s.category,
                    now
                ))

            conn.executemany("""
                INSERT OR REPLACE INTO chat_shards (
                    shard_id, source_turn_id, turn_index, role, domain, category,
                    salience, content, summary, keywords_json, timestamp,
                    epistemic_decay_rate, reinforcement_count, sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, shard_rows)

            conn.executemany("""
                INSERT INTO provenance_log (
                    shard_id, source_turn_id, sha256, domain, category, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, provenance_rows)

    def link_shards(self, source_id: str, target_id: str, relation_type: str = "associated", weight: float = 1.0) -> None:
        if source_id == target_id:
            return
        with self._connection_scope() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO relational_edges (source_shard, target_shard, relation_type, weight)
                VALUES (?, ?, ?, ?)
            """, (source_id, target_id, relation_type, weight))

    def auto_link_shards(self, shards: List[ChatShard], min_shared_keywords: int = 2) -> int:
        """
        Calculates associative hypergraph links based on shared semantic keywords.
        """
        links_created = 0
        edge_tuples = []
        for i in range(len(shards)):
            kw_a = set(shards[i].keywords)
            if not kw_a:
                continue
            for j in range(i + 1, len(shards)):
                kw_b = set(shards[j].keywords)
                shared = kw_a.intersection(kw_b)
                if len(shared) >= min_shared_keywords:
                    weight = round(len(shared) / max(len(kw_a.union(kw_b)), 1), 3)
                    edge_tuples.append((shards[i].shard_id, shards[j].shard_id, "semantic_overlap", weight))
                    edge_tuples.append((shards[j].shard_id, shards[i].shard_id, "semantic_overlap", weight))
                    links_created += 1

        if edge_tuples:
            with self._connection_scope() as conn:
                conn.executemany("""
                    INSERT OR REPLACE INTO relational_edges (source_shard, target_shard, relation_type, weight)
                    VALUES (?, ?, ?, ?)
                """, edge_tuples)
        return links_created

    def query_shards(
        self,
        domain: Optional[str] = None,
        category: Optional[str] = None,
        min_salience: float = 0.0,
        limit: int = 20,
        order_by_salience: bool = True
    ) -> List[Dict[str, Any]]:
        clauses = ["salience >= ?"]
        params: List[Any] = [min_salience]

        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if category:
            clauses.append("category = ?")
            params.append(category)

        where_clause = " AND ".join(clauses)
        order_clause = "ORDER BY salience DESC" if order_by_salience else "ORDER BY turn_index ASC"

        query = f"SELECT * FROM chat_shards WHERE {where_clause} {order_clause} LIMIT ?"
        params.append(limit)

        with self._connection_scope() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["keywords"] = json.loads(d["keywords_json"])
                results.append(d)
            return results

    def traverse_network(self, root_shard_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Breadth-first search traversal through associative edges.
        """
        visited: Set[str] = {root_shard_id}
        queue: List[Tuple[str, int]] = [(root_shard_id, 0)]
        results: List[Dict[str, Any]] = []

        with self._connection_scope() as conn:
            while queue:
                current_id, depth = queue.pop(0)
                if depth >= max_depth:
                    continue
                cursor = conn.execute("""
                    SELECT e.target_shard, e.relation_type, e.weight, s.summary, s.domain, s.salience
                    FROM relational_edges e
                    JOIN chat_shards s ON e.target_shard = s.shard_id
                    WHERE e.source_shard = ?
                    ORDER BY e.weight DESC
                """, (current_id,))
                for row in cursor.fetchall():
                    target = row["target_shard"]
                    if target not in visited:
                        visited.add(target)
                        res_dict = dict(row)
                        res_dict["depth"] = depth + 1
                        results.append(res_dict)
                        queue.append((target, depth + 1))
        return results

    def decay_epistemic_energy(self, turn_step: int = 1) -> int:
        """
        Applies Ebbinghaus decay to shards, lowering transient noise while preserving invariants.
        """
        with self._connection_scope() as conn:
            cursor = conn.execute("""
                UPDATE chat_shards
                SET salience = MAX(0.05, salience - (epistemic_decay_rate * ?))
                WHERE category != 'invariant_rule'
            """, (turn_step,))
            return cursor.rowcount

    def get_provenance(self, shard_id: str) -> Optional[Dict[str, Any]]:
        with self._connection_scope() as conn:
            cursor = conn.execute("SELECT * FROM provenance_log WHERE shard_id = ? ORDER BY log_id DESC LIMIT 1", (shard_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_stats(self) -> Dict[str, Any]:
        with self._connection_scope() as conn:
            total_shards = conn.execute("SELECT COUNT(*) FROM chat_shards").fetchone()[0]
            total_edges = conn.execute("SELECT COUNT(*) FROM relational_edges").fetchone()[0]
            
            domains = {}
            for r in conn.execute("SELECT domain, COUNT(*) as c FROM chat_shards GROUP BY domain"):
                domains[r["domain"]] = r["c"]

            categories = {}
            for r in conn.execute("SELECT category, COUNT(*) as c FROM chat_shards GROUP BY category"):
                categories[r["category"]] = r["c"]

            return {
                "total_shards": total_shards,
                "total_edges": total_edges,
                "domains": domains,
                "categories": categories
            }
