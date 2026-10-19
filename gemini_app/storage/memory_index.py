"""High-performance SQLite FTS5 Memory Index for dual-core chat recall and autonomous indexing."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, Iterator, List, Optional

from gemini_app.config import CHATS_DIR, GEMINI_HOME

DEFAULT_MEMORY_DB: Path = GEMINI_HOME / "memory_index.db"


class MemoryIndex:
    """Manages full-text indexing, fast search, and retrieval of turns across all sessions."""

    def __init__(self, db_path: Path | str = DEFAULT_MEMORY_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    project_dir TEXT,
                    title TEXT
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_turns_chat_id ON turns(chat_id, turn_number);
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                    turn_id UNINDEXED,
                    chat_id UNINDEXED,
                    turn_number UNINDEXED,
                    role UNINDEXED,
                    title,
                    content,
                    project_dir,
                    tokenize='porter unicode61'
                );
            """)
            conn.commit()

    def index_turn(
        self,
        turn_id: str,
        chat_id: str,
        turn_number: int,
        role: str,
        content: str,
        timestamp: Optional[float] = None,
        project_dir: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """Indexes an individual conversation turn atomically."""
        if not turn_id or not content:
            return

        ts = timestamp if timestamp is not None else time.time()
        p_dir = project_dir or ""
        t_title = title or ""

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT turn_id FROM turns WHERE turn_id = ?", (turn_id,))
            exists = cursor.fetchone()

            if exists:
                cursor.execute("""
                    UPDATE turns
                    SET chat_id = ?, turn_number = ?, role = ?, content = ?, timestamp = ?, project_dir = ?, title = ?
                    WHERE turn_id = ?
                """, (chat_id, turn_number, role, content, ts, p_dir, t_title, turn_id))
                cursor.execute("DELETE FROM turns_fts WHERE turn_id = ?", (turn_id,))
            else:
                cursor.execute("""
                    INSERT INTO turns (turn_id, chat_id, turn_number, role, content, timestamp, project_dir, title)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (turn_id, chat_id, turn_number, role, content, ts, p_dir, t_title))

            cursor.execute("""
                INSERT INTO turns_fts (turn_id, chat_id, turn_number, role, title, content, project_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (turn_id, chat_id, turn_number, role, t_title, content, p_dir))
            conn.commit()

    def index_chat(
        self,
        chat_id: str,
        history: List[Dict[str, Any]],
        title: str = "",
        working_dir: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        """Indexes all turns from a chat session. Returns count of indexed turns."""
        if not chat_id or not history:
            return 0

        indexed_count = 0
        ts = timestamp if timestamp is not None else time.time()
        p_dir = working_dir or ""

        with self._connection() as conn:
            cursor = conn.cursor()
            for idx, turn in enumerate(history):
                turn_id = turn.get("turn_id") or f"turn_{chat_id}_{idx}"
                role = turn.get("role", "user")
                content = turn.get("text", "")
                if not content:
                    continue

                cursor.execute("SELECT turn_id FROM turns WHERE turn_id = ?", (turn_id,))
                exists = cursor.fetchone()

                if exists:
                    cursor.execute("""
                        UPDATE turns
                        SET chat_id = ?, turn_number = ?, role = ?, content = ?, timestamp = ?, project_dir = ?, title = ?
                        WHERE turn_id = ?
                    """, (chat_id, idx + 1, role, content, ts, p_dir, title, turn_id))
                    cursor.execute("DELETE FROM turns_fts WHERE turn_id = ?", (turn_id,))
                else:
                    cursor.execute("""
                        INSERT INTO turns (turn_id, chat_id, turn_number, role, content, timestamp, project_dir, title)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (turn_id, chat_id, idx + 1, role, content, ts, p_dir, title))

                cursor.execute("""
                    INSERT INTO turns_fts (turn_id, chat_id, turn_number, role, title, content, project_dir)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (turn_id, chat_id, idx + 1, role, title, content, p_dir))
                indexed_count += 1
            conn.commit()

        return indexed_count

    def index_all_existing_chats(self, chats_dir: Path | str = CHATS_DIR) -> int:
        """Scans the chats directory and absorbs legacy and modern chats into the memory index."""
        target_dir = Path(chats_dir)
        if not target_dir.exists():
            return 0

        total_indexed = 0

        # 1. Sharded Directories
        for item in target_dir.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_dir():
                meta_file = item / "meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        cid = meta.get("id", item.name)
                        title = meta.get("title", "")
                        p_dir = meta.get("working_dir")
                        history: list[dict] = []
                        segment_files = sorted(
                            item.glob("segment_*.json"),
                            key=lambda f: int(f.stem.split("_")[1]) if "_" in f.stem else 0,
                        )
                        for sf in segment_files:
                            try:
                                turns = json.loads(sf.read_text(encoding="utf-8"))
                                history.extend(turns)
                            except Exception:
                                pass
                        total_indexed += self.index_chat(cid, history, title=title, working_dir=p_dir)
                    except Exception:
                        pass
                continue

            # 2. Legacy Flat JSON files
            if item.is_file() and item.suffix == ".json":
                try:
                    data = json.loads(item.read_text(encoding="utf-8"))
                    cid = data.get("id", item.stem)
                    title = data.get("title", "")
                    p_dir = data.get("working_dir")
                    history = data.get("messages", [])
                    total_indexed += self.index_chat(cid, history, title=title, working_dir=p_dir)
                except Exception:
                    pass

        return total_indexed

    def search(
        self,
        query: str,
        chat_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fast full-text search with highlight snippet extraction."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # Sanitize query for FTS5 syntax
        fts_tokens = re.findall(r"\w+", clean_query)
        if not fts_tokens:
            return []

        fts_query = " OR ".join(f'"{token}"*' for token in fts_tokens)

        with self._connection() as conn:
            cursor = conn.cursor()
            results: list[dict[str, Any]] = []

            try:
                if chat_id:
                    cursor.execute("""
                        SELECT t.turn_id, t.chat_id, t.turn_number, t.role, t.title,
                               snippet(turns_fts, 5, '[match]', '[/match]', '...', 25) AS match_snippet,
                               t.content, t.timestamp, t.project_dir
                        FROM turns_fts f
                        JOIN turns t ON f.turn_id = t.turn_id
                        WHERE turns_fts MATCH ? AND t.chat_id = ?
                        ORDER BY rank
                        LIMIT ?
                    """, (fts_query, chat_id, limit))
                else:
                    cursor.execute("""
                        SELECT t.turn_id, t.chat_id, t.turn_number, t.role, t.title,
                               snippet(turns_fts, 5, '[match]', '[/match]', '...', 25) AS match_snippet,
                               t.content, t.timestamp, t.project_dir
                        FROM turns_fts f
                        JOIN turns t ON f.turn_id = t.turn_id
                        WHERE turns_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """, (fts_query, limit))

                for row in cursor.fetchall():
                    results.append({
                        "turn_id": row["turn_id"],
                        "chat_id": row["chat_id"],
                        "turn_number": row["turn_number"],
                        "role": row["role"],
                        "title": row["title"],
                        "snippet": row["match_snippet"],
                        "content": row["content"],
                        "timestamp": row["timestamp"],
                        "project_dir": row["project_dir"],
                    })
            except Exception:
                # Fallback to standard LIKE if FTS fails
                like_pat = f"%{clean_query}%"
                if chat_id:
                    cursor.execute("""
                        SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir
                        FROM turns
                        WHERE chat_id = ? AND content LIKE ?
                        ORDER BY turn_number DESC
                        LIMIT ?
                    """, (chat_id, like_pat, limit))
                else:
                    cursor.execute("""
                        SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir
                        FROM turns
                        WHERE content LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (like_pat, limit))

                for row in cursor.fetchall():
                    content = row["content"]
                    snippet = content[:150] + "..." if len(content) > 150 else content
                    results.append({
                        "turn_id": row["turn_id"],
                        "chat_id": row["chat_id"],
                        "turn_number": row["turn_number"],
                        "role": row["role"],
                        "title": row["title"],
                        "snippet": snippet,
                        "content": content,
                        "timestamp": row["timestamp"],
                        "project_dir": row["project_dir"],
                    })

            return results

    def get_turn_by_id(self, turn_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir
                FROM turns
                WHERE turn_id = ?
            """, (turn_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def get_turns_by_numbers(self, chat_id: str, turn_numbers: List[int]) -> List[Dict[str, Any]]:
        if not turn_numbers:
            return []

        placeholders = ",".join("?" for _ in turn_numbers)
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir
                FROM turns
                WHERE chat_id = ? AND turn_number IN ({placeholders})
                ORDER BY turn_number ASC
            """, [chat_id] + turn_numbers)
            return [dict(r) for r in cursor.fetchall()]
