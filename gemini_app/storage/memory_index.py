"""High-performance SQLite FTS5 Memory Index for dual-core chat recall and autonomous indexing."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, Iterator, List, Optional, Set

from gemini_app.config import CHATS_DIR, GEMINI_HOME

DEFAULT_MEMORY_DB: Path = GEMINI_HOME / "memory_index.db"

TAG_KEYWORDS: dict[str, list[str]] = {
    "code": ["def ", "class ", "function ", "import ", "return ", "async def ", "const ", "let "],
    "git": ["git", "commit", "branch", "diff", "checkout", "stash", "merge", "pull", "push"],
    "testing": ["test", "unittest", "pytest", "assert", "mock", "suite", "TestCase"],
    "ui": ["textual", "widget", "screen", "modal", "css", "theme", "toast", "feed", "card"],
    "memory": ["memory", "index", "fts5", "recall", "search", "sqlite", "token"],
    "notes": ["notes", "scratchpad", "relational", "global_notes", "gemini_notes"],
    "reboot": ["reboot", "restart", "execv", "rollback", "crash", "recover"],
    "terminal": ["shell", "bash", "execute", "command", "process", "stdout", "stderr"],
    "snapshot": ["snapshot", "screenshot", "svg", "ui_snapshot", "audit"],
}


def extract_code_symbols(content: str) -> list[str]:
    """Extracts function/class definitions, filenames, and tool references from turn text."""
    symbols: Set[str] = set()

    # 1. Defs and classes
    for m in re.finditer(r"(?:def|class|func|function)\s+([a-zA-Z_]\w*)", content):
        symbols.add(m.group(1))

    # 2. File paths and filenames with known extensions
    for m in re.finditer(r"\b[a-zA-Z0-9_\-./]+\.(?:py|json|md|txt|sh|ts|js|html|css|rs|go|c|h|el|yml|yaml)\b", content):
        symbols.add(m.group(0))

    # 3. Bilateral tool calls and key commands
    for m in re.finditer(r"\b(?:apply_patch|write_file|reboot_console|expand_mind|recall_memory|manage_notes|search_codebase|execute_shell|take_snapshot|review_snapshots)\b", content):
        symbols.add(m.group(0))

    return sorted(list(symbols))[:30]


def extract_tags(content: str) -> list[str]:
    """Classifies content into searchable topic tags."""
    tags: Set[str] = set()
    lower = content.lower()
    for tag, patterns in TAG_KEYWORDS.items():
        if any(p.lower() in lower for p in patterns):
            tags.add(f"#{tag}")
    return sorted(list(tags))


class MemoryIndex:
    """Manages full-text indexing, fast search, code symbol analysis, and memory map persistence."""

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
                    title TEXT,
                    code_symbols TEXT DEFAULT '',
                    tags TEXT DEFAULT '',
                    turn_summary TEXT DEFAULT ''
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_turns_chat_id ON turns(chat_id, turn_number);
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mind_maps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    gemini_state TEXT,
                    user_state TEXT,
                    tree_state TEXT,
                    tree_content TEXT,
                    active_task_title TEXT
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mind_maps_chat ON mind_maps(chat_id, timestamp);
            """)

            # Ensure schema migrations if upgrading older DB
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(turns);")
            columns = {row["name"] for row in cursor.fetchall()}
            for col, col_type in [("code_symbols", "TEXT DEFAULT ''"), ("tags", "TEXT DEFAULT ''"), ("turn_summary", "TEXT DEFAULT ''")]:
                if col not in columns:
                    try:
                        conn.execute(f"ALTER TABLE turns ADD COLUMN {col} {col_type};")
                    except Exception:
                        pass

            # FTS5 Full-Text Search Virtual Table
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                    turn_id UNINDEXED,
                    chat_id UNINDEXED,
                    turn_number UNINDEXED,
                    role UNINDEXED,
                    title,
                    content,
                    project_dir,
                    code_symbols,
                    tags,
                    tokenize='porter unicode61'
                );
            """)
            conn.commit()

    def save_mind_map(
        self,
        chat_id: str,
        gemini_state: str,
        user_state: str,
        tree_state: List[Any],
        tree_content: str,
        active_task_title: str = "",
    ) -> None:
        """Saves a snapshot of the cognitive mind map for longitudinal recall and reboot continuity."""
        if not chat_id:
            return
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO mind_maps (chat_id, timestamp, gemini_state, user_state, tree_state, tree_content, active_task_title)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                chat_id,
                time.time(),
                gemini_state,
                user_state,
                json.dumps(tree_state),
                tree_content,
                active_task_title,
            ))
            conn.commit()

    def get_latest_mind_map(self, chat_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves the latest cognitive mind map recorded across sessions."""
        with self._connection() as conn:
            cursor = conn.cursor()
            if chat_id:
                cursor.execute("""
                    SELECT * FROM mind_maps
                    WHERE chat_id = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (chat_id,))
            else:
                cursor.execute("""
                    SELECT * FROM mind_maps
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
            row = cursor.fetchone()
            if row:
                res = dict(row)
                try:
                    res["tree_state"] = json.loads(res.get("tree_state", "[]"))
                except Exception:
                    res["tree_state"] = []
                return res
        return None

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
        """Indexes an individual conversation turn atomically with enriched symbols and tags."""
        if not turn_id or not content:
            return

        ts = timestamp if timestamp is not None else time.time()
        p_dir = project_dir or ""
        t_title = title or ""

        symbols_list = extract_code_symbols(content)
        tags_list = extract_tags(content)
        symbols_str = " ".join(symbols_list)
        tags_str = " ".join(tags_list)

        # Build concise 1-line turn summary
        first_line = content.strip().split("\n")[0]
        turn_summary = first_line[:120].strip()

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT turn_id FROM turns WHERE turn_id = ?", (turn_id,))
            exists = cursor.fetchone()

            if exists:
                cursor.execute("""
                    UPDATE turns
                    SET chat_id = ?, turn_number = ?, role = ?, content = ?, timestamp = ?,
                        project_dir = ?, title = ?, code_symbols = ?, tags = ?, turn_summary = ?
                    WHERE turn_id = ?
                """, (chat_id, turn_number, role, content, ts, p_dir, t_title, symbols_str, tags_str, turn_summary, turn_id))
                cursor.execute("DELETE FROM turns_fts WHERE turn_id = ?", (turn_id,))
            else:
                cursor.execute("""
                    INSERT INTO turns (turn_id, chat_id, turn_number, role, content, timestamp, project_dir, title, code_symbols, tags, turn_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (turn_id, chat_id, turn_number, role, content, ts, p_dir, t_title, symbols_str, tags_str, turn_summary))

            cursor.execute("""
                INSERT INTO turns_fts (turn_id, chat_id, turn_number, role, title, content, project_dir, code_symbols, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (turn_id, chat_id, turn_number, role, t_title, content, p_dir, symbols_str, tags_str))
            conn.commit()

    def index_chat(
        self,
        chat_id: str,
        history: List[Dict[str, Any]],
        title: str = "",
        working_dir: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        """Indexes all turns from a chat session with multi-tier symbol analysis."""
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

                symbols_str = " ".join(extract_code_symbols(content))
                tags_str = " ".join(extract_tags(content))
                turn_summary = content.strip().split("\n")[0][:120].strip()

                cursor.execute("SELECT turn_id FROM turns WHERE turn_id = ?", (turn_id,))
                exists = cursor.fetchone()

                if exists:
                    cursor.execute("""
                        UPDATE turns
                        SET chat_id = ?, turn_number = ?, role = ?, content = ?, timestamp = ?,
                            project_dir = ?, title = ?, code_symbols = ?, tags = ?, turn_summary = ?
                        WHERE turn_id = ?
                    """, (chat_id, idx + 1, role, content, ts, p_dir, title, symbols_str, tags_str, turn_summary, turn_id))
                    cursor.execute("DELETE FROM turns_fts WHERE turn_id = ?", (turn_id,))
                else:
                    cursor.execute("""
                        INSERT INTO turns (turn_id, chat_id, turn_number, role, content, timestamp, project_dir, title, code_symbols, tags, turn_summary)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (turn_id, chat_id, idx + 1, role, content, ts, p_dir, title, symbols_str, tags_str, turn_summary))

                cursor.execute("""
                    INSERT INTO turns_fts (turn_id, chat_id, turn_number, role, title, content, project_dir, code_symbols, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (turn_id, chat_id, idx + 1, role, title, content, p_dir, symbols_str, tags_str))
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
        """Fast full-text search with symbol matching and ranked snippet extraction."""
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
                               t.content, t.timestamp, t.project_dir, t.code_symbols, t.tags, t.turn_summary
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
                               t.content, t.timestamp, t.project_dir, t.code_symbols, t.tags, t.turn_summary
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
                        "code_symbols": row["code_symbols"],
                        "tags": row["tags"],
                        "turn_summary": row["turn_summary"],
                    })
            except Exception:
                # Fallback to standard LIKE if FTS fails
                like_pat = f"%{clean_query}%"
                if chat_id:
                    cursor.execute("""
                        SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir, code_symbols, tags, turn_summary
                        FROM turns
                        WHERE chat_id = ? AND (content LIKE ? OR title LIKE ? OR code_symbols LIKE ?)
                        ORDER BY turn_number DESC
                        LIMIT ?
                    """, (chat_id, like_pat, like_pat, like_pat, limit))
                else:
                    cursor.execute("""
                        SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir, code_symbols, tags, turn_summary
                        FROM turns
                        WHERE content LIKE ? OR title LIKE ? OR code_symbols LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (like_pat, like_pat, like_pat, limit))

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
                        "code_symbols": row["code_symbols"],
                        "tags": row["tags"],
                        "turn_summary": row["turn_summary"],
                    })

            return results

    def get_turn_by_id(self, turn_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir, code_symbols, tags, turn_summary
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
                SELECT turn_id, chat_id, turn_number, role, title, content, timestamp, project_dir, code_symbols, tags, turn_summary
                FROM turns
                WHERE chat_id = ? AND turn_number IN ({placeholders})
                ORDER BY turn_number ASC
            """, [chat_id] + turn_numbers)
            return [dict(r) for r in cursor.fetchall()]
