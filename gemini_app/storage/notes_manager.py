"""Unified Gemini-Managed Notes Engine.

Provides topic association, cognitive categorization (working, think_about, get_back_to),
chat scanning, user-note ingestion, relevance filtering, deduplication, pruning, archiving,
and persistence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
import time
from typing import Any
from uuid import uuid4


def sanitize_working_notes(text: str) -> str:
    """Strips rendered template headers, placeholders, badges, or relevant notes sections.

    Ensures that working_notes stores only Gemini's actual working scratchpad text,
    preventing duplicate headers or leaked bullet lists.
    """
    if not text:
        return ""

    clean = text.strip()
    placeholder = "*(No active working notes set. Gemini updates working notes autonomously as tasks proceed.)*"

    # If the text has template headers, extract only the actual working notes content
    if "# 🧠 Gemini Working Notes" in clean or "# 📌 Relevant Notes" in clean:
        match = re.search(r"# 🧠 Gemini Working Notes[^\n]*\n(.*?)(?=\n#|\Z)", clean, re.DOTALL)
        if match:
            clean = match.group(1).strip()
        else:
            clean = re.sub(r"# 🧠 Gemini Working Notes[^\n]*", "", clean)
            clean = re.sub(r"# 📌 Relevant Notes[^\n]*.*", "", clean, flags=re.DOTALL)
            clean = clean.strip()

    # Strip any cascaded/nested headers if repeatedly appended
    while "# 🧠 Gemini Working Notes" in clean:
        clean = re.sub(r"# 🧠 Gemini Working Notes[^\n]*", "", clean).strip()
    while "# 📌 Relevant Notes" in clean:
        clean = re.sub(r"# 📌 Relevant Notes[^\n]*.*", "", clean, flags=re.DOTALL).strip()

    if clean == placeholder:
        return ""

    # Strip bullet lines that originated from the rendered relevant/topic lists
    clean_lines: list[str] = []
    for line in clean.splitlines():
        l_str = line.strip()
        if not l_str or l_str == placeholder or l_str.startswith("*(No user or topic notes"):
            continue
        # Drop lines that are bullet notes with author badges e.g. "• [👤 User]" or "• [🧠 Gemini]"
        if re.match(r"^[•\-\*]\s*\[(?:👤 User|🧠 Gemini)\]", l_str):
            continue
        clean_lines.append(line)

    return "\n".join(clean_lines).strip()


def normalize_note_text(text: str) -> str:
    """Normalizes note content by stripping badges, status tags, topic tags, and whitespace."""
    s = (text or "").strip()
    # Strip leading bullets
    s = re.sub(r"^[•\-\*]\s*", "", s).strip()
    # Strip user/model badges
    s = re.sub(r"^\[(?:👤 User|🧠 Gemini|User|Gemini)\]\s*", "", s).strip()
    # Strip status tag e.g. [think_about], [get_back_to], [working], [completed], [archived]
    s = re.sub(r"^\[(?:think_about|think|get_back_to|todo|working|completed|reference|archived)\]\s*", "", s, flags=re.IGNORECASE).strip()
    # Strip topic prefix in parens e.g. (ui):
    s = re.sub(r"^\([^\)]+\):\s*", "", s).strip()
    return s.strip()


def infer_note_status(content: str) -> str:
    """Thoughtfully infers note status (get_back_to, working, reference, think_about) from content semantics."""
    cl = (content or "").lower()
    # Action items / todos / follow-ups
    if re.search(r"\b(todo|must|get\s*back|fix|remember\s*to|need\s*to|action(?:\s*item)?|follow-?up|verify)\b", cl):
        return "get_back_to"
    # Working / active development scratchpad items
    elif re.search(r"\b(working\s*on|in\s*progress|current\s*task|implementing|active:|scratchpad|wip)\b", cl):
        return "working"
    # Informational reference / lookup / general notes / docs
    elif re.search(r"\b(fyi|ref:|reference:|info:|docs:|documentation:|general\s*note|lookup:)\b", cl):
        return "reference"
    # Brainstorming / thoughts
    elif re.search(r"\b(think(?:\s*about)?|idea:|consider|ponder|brainstorm|maybe|what\s*if)\b", cl):
        return "think_about"
    # Thoughtful default for general notes / observations
    return "think_about"


@dataclass
class NoteItem:
    """Represents a single atomic note managed by Gemini."""

    id: str
    topic: str
    content: str
    status: str = "working"  # "working", "think_about", "get_back_to", "completed", "reference", "archived"
    author: str = "gemini"  # "gemini" or "user"
    relevant: bool = True
    archived: bool = False
    archived_at: float | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turn_id: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NoteItem:
        status_val = data.get("status") or "working"
        is_archived = bool(data.get("archived", False) or status_val == "archived")
        return cls(
            id=data.get("id") or f"n_{uuid4().hex[:6]}",
            topic=(data.get("topic") or "general").strip().lower(),
            content=str(data.get("content") or "").strip(),
            status="archived" if is_archived else status_val,
            author=data.get("author") or "gemini",
            relevant=bool(data.get("relevant", True)) and not is_archived,
            archived=is_archived,
            archived_at=float(data["archived_at"]) if data.get("archived_at") else (time.time() if is_archived else None),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            turn_id=str(data.get("turn_id") or ""),
            tags=list(data.get("tags") or []),
        )


class NotesManager:
    """Unified Notes Engine managing all project notes, topics, follow-ups, pruning, and archiving."""

    def __init__(
        self,
        working_notes: str = "",
        current_topic: str = "general",
        notes: list[NoteItem] | None = None,
        active_topic: str | None = None,
    ) -> None:
        self.working_notes: str = sanitize_working_notes(working_notes)
        topic_to_use = active_topic or current_topic or "general"
        self.current_topic: str = (topic_to_use or "general").strip().lower()
        self.notes: list[NoteItem] = notes or []
        self._last_rendered_view: str = ""
        # Automatically clean and deduplicate on instantiation
        if self.notes:
            self.deduplicate_notes()

    @property
    def active_topic(self) -> str:
        return self.current_topic

    @active_topic.setter
    def active_topic(self, value: str) -> None:
        self.set_current_topic(value)

    def set_current_topic(self, topic: str) -> None:
        clean = (topic or "general").strip().lower()
        if clean:
            self.current_topic = clean

    def set_working_notes(self, content: str) -> None:
        self.working_notes = sanitize_working_notes(content)

    def record_note(
        self,
        content: str,
        topic: str = "",
        status: str = "working",
        author: str = "gemini",
        relevant: bool = True,
        turn_id: str = "",
        tags: list[str] | None = None,
        note_id: str = "",
        archived: bool = False,
    ) -> NoteItem | None:
        """Records a new note or updates an existing one associated with a topic.

        Cleans up any embedded badges, status prefixes, or topic wrappers, and deduplicates
        in place against existing items.
        """
        raw_content = (content or "").strip()
        if not raw_content:
            return None

        # Clean content and extract any embedded metadata
        status_clean = (status or "working").strip().lower()
        clean_topic = (topic or self.current_topic or "general").strip().lower()

        # Strip badge if present e.g. "[👤 User]"
        raw_content = re.sub(r"^\[(?:👤 User|🧠 Gemini|User|Gemini)\]\s*", "", raw_content).strip()

        # Check for status tag prefix e.g. [think_about]
        st_match = re.match(r"^\[([a-zA-Z_]+)\]\s*", raw_content)
        if st_match:
            pot_status = st_match.group(1).lower()
            if pot_status in ("working", "think_about", "think", "get_back_to", "todo", "completed", "reference", "archived"):
                status_clean = pot_status
                raw_content = raw_content[st_match.end():].strip()

        # Check for topic prefix in parentheses e.g. (ui):
        tp_match = re.match(r"^\(([a-zA-Z0-9_\-\s]+)\):\s*", raw_content)
        if tp_match:
            clean_topic = tp_match.group(1).strip().lower()
            raw_content = raw_content[tp_match.end():].strip()

        clean_content = normalize_note_text(raw_content)
        if not clean_content:
            return None

        # Normalize status aliases
        if status_clean in ("think", "thinkabout", "ponder", "consider"):
            status_clean = "think_about"
        elif status_clean in ("getback", "getbackto", "todo", "followup", "follow_up", "action"):
            status_clean = "get_back_to"
        elif status_clean in ("done", "finished"):
            status_clean = "completed"
        elif status_clean in ("archive", "archived"):
            status_clean = "archived"
            archived = True

        if archived:
            relevant = False

        # 1. Update if explicit note_id exists
        if note_id:
            for item in self.notes:
                if item.id == note_id:
                    item.content = clean_content
                    item.topic = clean_topic
                    item.status = status_clean
                    item.relevant = relevant
                    item.archived = archived
                    if archived and not item.archived_at:
                        item.archived_at = time.time()
                    elif not archived:
                        item.archived_at = None
                    item.updated_at = time.time()
                    if tags is not None:
                        item.tags = tags
                    return item

        # 2. Check for duplicate content under same topic (or cross-topic if content is identical)
        norm_clean = clean_content.lower()
        for item in self.notes:
            norm_item = normalize_note_text(item.content).lower()
            # Match identical content under same topic, or match when one has general topic
            if (item.topic == clean_topic or item.topic == "general" or clean_topic == "general") and norm_item == norm_clean:
                # Prefer more specific topic
                if clean_topic != "general" and item.topic == "general":
                    item.topic = clean_topic
                item.content = clean_content
                item.status = status_clean
                item.relevant = relevant and not item.archived
                item.updated_at = time.time()
                if author == "user":
                    item.author = "user"
                if turn_id and not item.turn_id:
                    item.turn_id = turn_id
                if tags:
                    for t in tags:
                        if t not in item.tags:
                            item.tags.append(t)
                return item

        new_item = NoteItem(
            id=note_id or f"n_{uuid4().hex[:6]}",
            topic=clean_topic,
            content=clean_content,
            status=status_clean,
            author=author,
            relevant=relevant and not archived,
            archived=archived,
            archived_at=time.time() if archived else None,
            created_at=time.time(),
            updated_at=time.time(),
            turn_id=turn_id,
            tags=tags or [],
        )
        self.notes.append(new_item)
        return new_item

    # -----------------------------------------------------------------------
    # Note Archiving & Pruning Engine
    # -----------------------------------------------------------------------

    def archive_note(self, note_id_or_query: str) -> bool:
        """Archives a note by ID, exact topic/content, or query."""
        target = (note_id_or_query or "").strip().lower()
        if not target:
            return False

        # Try exact ID match first
        for n in self.notes:
            if n.id.lower() == target:
                n.archived = True
                n.archived_at = time.time()
                n.status = "archived"
                n.relevant = False
                n.updated_at = time.time()
                return True

        # Try matching content
        for n in self.notes:
            if target in n.content.lower():
                n.archived = True
                n.archived_at = time.time()
                n.status = "archived"
                n.relevant = False
                n.updated_at = time.time()
                return True

        return False

    def unarchive_note(self, note_id_or_query: str, restore_status: str = "working") -> bool:
        """Unarchives a note and restores it to active tracking."""
        target = (note_id_or_query or "").strip().lower()
        if not target:
            return False

        for n in self.notes:
            if n.id.lower() == target or target in n.content.lower():
                n.archived = False
                n.archived_at = None
                n.status = restore_status if n.status == "archived" else n.status
                n.relevant = True
                n.updated_at = time.time()
                return True

        return False

    def archive_completed_notes(self) -> int:
        """Archives all completed notes so they no longer clutter active views."""
        count = 0
        now = time.time()
        for n in self.notes:
            if n.status == "completed" and not n.archived:
                n.archived = True
                n.archived_at = now
                n.relevant = False
                n.updated_at = now
                count += 1
        return count

    def get_archived_notes(self) -> list[NoteItem]:
        """Returns all archived notes."""
        return [n for n in self.notes if n.archived or n.status == "archived"]

    def deduplicate_notes(self) -> int:
        """Deduplicates note items, preserving the most comprehensive/recent note.

        Returns count of duplicates removed.
        """
        seen: dict[tuple[str, str], NoteItem] = {}
        unique_notes: list[NoteItem] = []
        duplicates_removed = 0

        for item in self.notes:
            clean_c = normalize_note_text(item.content)
            if not clean_c:
                continue

            item.content = clean_c
            key = (item.topic.lower(), clean_c.lower())

            if key in seen:
                existing = seen[key]
                # Merge tags and metadata into the existing one
                for t in item.tags:
                    if t not in existing.tags:
                        existing.tags.append(t)
                if item.updated_at > existing.updated_at:
                    existing.updated_at = item.updated_at
                    existing.status = item.status
                if item.author == "user":
                    existing.author = "user"
                duplicates_removed += 1
            else:
                seen[key] = item
                unique_notes.append(item)

        # Retain empty notes so prune_notes can explicitly report empty_removed
        empty_notes = [n for n in self.notes if not normalize_note_text(n.content)]
        self.notes = unique_notes + empty_notes
        return duplicates_removed

    def prune_notes(
        self,
        max_per_topic: int | None = None,
        remove_completed: bool = False,
        remove_archived_older_than_days: int | None = None,
    ) -> dict[str, int]:
        """Prunes notes: removes duplicates, purges stale/empty items, and sanitizes working state.

        Returns a dictionary summarizing pruned actions.
        """
        # 1. Sanitize working notes scratchpad
        self.working_notes = sanitize_working_notes(self.working_notes)

        # 2. Deduplicate notes list
        dups_removed = self.deduplicate_notes()

        # 3. Optional removals
        empty_removed = 0
        archived_purged = 0
        now = time.time()
        kept: list[NoteItem] = []

        for n in self.notes:
            norm_content = normalize_note_text(n.content)
            if not norm_content:
                empty_removed += 1
                continue

            n.content = norm_content

            if remove_completed and n.status == "completed":
                empty_removed += 1
                continue

            if n.archived and remove_archived_older_than_days is not None:
                arch_time = n.archived_at or n.updated_at or n.created_at
                max_age_sec = remove_archived_older_than_days * 86400
                if now - arch_time > max_age_sec:
                    archived_purged += 1
                    continue

            kept.append(n)

        # 4. Optional topic cap
        if max_per_topic and max_per_topic > 0:
            by_topic: dict[str, list[NoteItem]] = {}
            for n in kept:
                by_topic.setdefault(n.topic, []).append(n)

            capped_kept: list[NoteItem] = []
            for topic, t_notes in by_topic.items():
                # Sort newest updated first
                t_notes.sort(key=lambda x: x.updated_at, reverse=True)
                capped_kept.extend(t_notes[:max_per_topic])
                # Archive the overflow instead of hard deletion
                for overflow in t_notes[max_per_topic:]:
                    if not overflow.archived:
                        overflow.archived = True
                        overflow.archived_at = now
                        overflow.relevant = False
                        capped_kept.append(overflow)

            kept = capped_kept

        self.notes = kept
        return {
            "duplicates_removed": dups_removed,
            "empty_removed": empty_removed,
            "archived_purged": archived_purged,
            "total_remaining": len(self.notes),
            "archived_count": len(self.get_archived_notes()),
        }

    # -----------------------------------------------------------------------
    # Ingestion & Scanning
    # -----------------------------------------------------------------------

    def consume_user_input(
        self,
        raw_input: str = "",
        default_topic: str = "",
        raw_text: str = "",
        active_topic: str = "",
        turn_id: str = "",
    ) -> list[NoteItem]:
        """Consumes user note input from editor or command, categorizing and associating with topic."""
        text = (raw_text or raw_input or "").strip()
        if not text:
            return []

        target_topic = (active_topic or default_topic or self.current_topic or "general").strip().lower()

        # Check if the user input contains Markdown view structure from format_working_view
        if "# 🧠 Gemini Working Notes" in text or "# 📌 Relevant Notes" in text or "# ⏳ Notes" in text:
            consumed: list[NoteItem] = []

            # 1. Extract Working Notes section cleanly
            w_match = re.search(r"# 🧠 Gemini Working Notes[^\n]*\n(.*?)(?=\n#|\Z)", text, re.DOTALL)
            if w_match:
                extracted_w = sanitize_working_notes(w_match.group(1))
                if extracted_w:
                    self.working_notes = extracted_w

            # 2. Extract only newly added bullet points or lines that are NOT already in self.notes
            # Collect normalized content of existing notes to avoid duplication
            existing_contents = {normalize_note_text(n.content).lower() for n in self.notes}

            # Only scan lines that appear after the first header
            lines = text.split("\n")
            in_relevant_section = False

            for line in lines:
                l_clean = line.strip()
                if not l_clean:
                    continue

                if l_clean.startswith("# 📌 Relevant Notes") or l_clean.startswith("# ⏳ Notes") or l_clean.startswith("# 💡 Notes"):
                    in_relevant_section = True
                    continue
                elif l_clean.startswith("#"):
                    in_relevant_section = False
                    continue

                if "*(No " in l_clean:
                    continue

                if in_relevant_section or re.match(r"^[•\-\*]\s*", l_clean):
                    clean_line = normalize_note_text(l_clean)
                    if not clean_line or len(clean_line) < 2:
                        continue

                    # If this line's content already exists, do not duplicate it
                    if clean_line.lower() in existing_contents:
                        continue

                    # Infer status
                    status = infer_note_status(clean_line)

                    item = self.record_note(
                        content=clean_line,
                        topic=target_topic,
                        status=status,
                        author="user",
                        relevant=True,
                        turn_id=turn_id,
                    )
                    if item:
                        consumed.append(item)
                        existing_contents.add(clean_line.lower())

            self.deduplicate_notes()
            return consumed

        # Pure raw input: parse explicit topic directive
        topic_match = re.search(r"(?:^|\n)(?:#\s*topic:|\bTopic:)\s*([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
        if topic_match:
            target_topic = topic_match.group(1).strip().lower()
            text = re.sub(r"(?:^|\n)(?:#\s*topic:|\bTopic:)\s*[a-zA-Z0-9_\-]+", "", text, flags=re.IGNORECASE).strip()

        # Check if the input is a bullet list or numbered list with multiple items
        raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
        is_bullet_list = len(raw_lines) > 1 and all(re.match(r"^(?:[•\-\*]|\d+[\.\)])\s+", l) for l in raw_lines)

        if is_bullet_list:
            consumed_items: list[NoteItem] = []
            for line in raw_lines:
                clean_line = re.sub(r"^(?:[•\-\*]|\d+[\.\)])\s+", "", line).strip()
                clean_line = normalize_note_text(clean_line)
                if not clean_line or len(clean_line) < 2:
                    continue
                line_status = infer_note_status(clean_line)
                line_tags = re.findall(r"#([a-zA-Z0-9_\-]+)", clean_line)
                item = self.record_note(
                    content=clean_line,
                    topic=target_topic,
                    status=line_status,
                    author="user",
                    relevant=True,
                    turn_id=turn_id,
                    tags=line_tags,
                )
                if item:
                    consumed_items.append(item)
            self.deduplicate_notes()
            return consumed_items

        # Single note item or cohesive multiline note
        extracted_tags = re.findall(r"#([a-zA-Z0-9_\-]+)", text)
        status = infer_note_status(text)

        item = self.record_note(
            content=text,
            topic=target_topic,
            status=status,
            author="user",
            relevant=True,
            turn_id=turn_id,
            tags=extracted_tags,
        )
        self.deduplicate_notes()
        return [item] if item else []

    def scan_chat_for_notes(self, history: list[dict], default_topic: str = "") -> list[NoteItem]:
        """Scans conversation chat turns, extracts notes and directives, and associates them with topics."""
        new_items: list[NoteItem] = []
        base_topic = (default_topic or self.current_topic or "general").strip().lower()

        directive_regex = re.compile(
            r"(?:^|\n)((?:NOTE|Note|note|REMEMBER TO|Remember to|REMEMBER|Remember|TODO|Todo|todo|FIX|Fix|NEED TO|Need to|MUST|Must|THINK ABOUT|Think about|GET BACK TO|Get back to|ACTION|Action|FYI|Fyi|fyi|GENERAL NOTE|General note|GENERAL|General|REF|Ref|REFERENCE|Reference)s?):\s*(.+?)(?=\n(?:[A-Z#•\*-]|\Z)|\Z)",
            re.MULTILINE,
        )

        for turn in history:
            text = str(turn.get("text", "") or "")
            if not text:
                continue

            role = turn.get("role", "user")
            turn_id = turn.get("turn_id", "")
            author = "user" if role == "user" else "gemini"

            # Check for topic annotations
            topic_match = re.search(r"(?:#\s*topic:|\bTopic:)\s*([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
            assigned_topic = topic_match.group(1).strip().lower() if topic_match else base_topic

            matches = directive_regex.findall(text)
            for prefix, raw_content in matches:
                content = normalize_note_text(raw_content.strip())
                if not content or len(content) < 3:
                    continue

                p_lower = prefix.lower()
                c_lower = content.lower()

                # Infer status thoughtfully from directive prefix and content
                if any(w in p_lower or w in c_lower for w in ("todo", "must", "get back", "fix", "remember", "need to", "action")):
                    status = "get_back_to"
                elif any(w in p_lower or w in c_lower for w in ("think", "consider", "ponder", "idea", "brainstorm")):
                    status = "think_about"
                elif any(w in p_lower or w in c_lower for w in ("fyi", "ref", "reference", "general")):
                    status = "reference"
                else:
                    status = "working"

                item = self.record_note(
                    content=content,
                    topic=assigned_topic,
                    status=status,
                    author=author,
                    relevant=True,
                    turn_id=turn_id,
                )
                if item and item not in new_items:
                    new_items.append(item)

        self.deduplicate_notes()
        return new_items

    def delete_note(self, note_id: str) -> bool:
        initial_len = len(self.notes)
        self.notes = [n for n in self.notes if n.id != note_id]
        return len(self.notes) < initial_len

    # -----------------------------------------------------------------------
    # Queries & Filters (Excluding Archived Notes from Active Views)
    # -----------------------------------------------------------------------

    def get_notes(
        self,
        topic: str | None = None,
        status: str | None = None,
        author: str | None = None,
        relevant_only: bool = False,
        include_archived: bool = False,
    ) -> list[NoteItem]:
        results = [n for n in self.notes if include_archived or (not n.archived and n.status != "archived")]
        if topic:
            clean_t = topic.strip().lower()
            results = [n for n in results if n.topic == clean_t]
        if status:
            clean_s = status.strip().lower()
            results = [n for n in results if n.status == clean_s]
        if author:
            clean_a = author.strip().lower()
            results = [n for n in results if n.author == clean_a]
        if relevant_only:
            results = [n for n in results if n.relevant]
        return results

    def get_relevant_notes(self, topic: str | None = None) -> list[NoteItem]:
        active_t = (topic or self.current_topic).strip().lower()
        relevant = [
            n for n in self.notes
            if not n.archived and n.status != "archived" and (n.relevant or n.topic == active_t or (n.author == "user" and n.status != "completed"))
        ]
        return relevant

    def get_notes_to_think_about(self) -> list[NoteItem]:
        return [n for n in self.notes if not n.archived and n.status == "think_about"]

    def get_notes_to_get_back_to(self) -> list[NoteItem]:
        return [n for n in self.notes if not n.archived and n.status == "get_back_to"]

    def get_notes_by_topic(self, topic: str) -> list[NoteItem]:
        clean_t = (topic or "").strip().lower()
        return [n for n in self.notes if not n.archived and n.status != "archived" and n.topic == clean_t]

    def get_all_topics(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for n in self.notes:
            if not n.archived and n.status != "archived":
                counts[n.topic] = counts.get(n.topic, 0) + 1
        if self.current_topic not in counts:
            counts[self.current_topic] = 0
        sorted_topics = sorted(counts.items(), key=lambda x: (x[0] != self.current_topic, -x[1], x[0]))
        return sorted_topics

    def search_notes(self, query: str, include_archived: bool = True) -> list[NoteItem]:
        q = (query or "").strip().lower()
        pool = self.notes if include_archived else [n for n in self.notes if not n.archived]
        if not q:
            return list(pool)
        matches = []
        for n in pool:
            if q in n.content.lower() or q in n.topic.lower() or q in n.status.lower() or any(q in t.lower() for t in n.tags):
                matches.append(n)
        return matches

    # -----------------------------------------------------------------------
    # Rendering & Markdown Formatting
    # -----------------------------------------------------------------------

    def format_working_view(self, view_mode: str = "working") -> str:
        """Formats the Markdown view displayed inside the Notes Editor Area."""
        mode = (view_mode or "working").strip().lower()

        # 1. Working Notes View (Default: Working Notes + Relevant User & Topic Notes)
        if mode in ("working", "gemini"):
            sections = []
            sections.append(f"# 🧠 Gemini Working Notes [Topic: {self.current_topic}]")
            clean_w = sanitize_working_notes(self.working_notes)
            if clean_w:
                sections.append(clean_w)
            else:
                sections.append("*(No active working notes set. Gemini updates working notes autonomously as tasks proceed.)*")

            relevant = self.get_relevant_notes()
            sections.append(f"\n# 📌 Relevant Notes in Relation to Current Work ({len(relevant)})")
            if not relevant:
                sections.append("*(No user or topic notes currently flagged as relevant to this work.)*")
            else:
                for n in relevant:
                    badge = "👤 User" if n.author == "user" else "🧠 Gemini"
                    status_lbl = f" [{n.status}]" if n.status != "working" else ""
                    sections.append(f"• [{badge}]{status_lbl} ({n.topic}): {n.content}")

            self._last_rendered_view = "\n".join(sections)
            return self._last_rendered_view

        # 2. Relevant Only View
        elif mode in ("relevant", "turn"):
            sections = [f"# 📌 Relevant Notes [Topic: {self.current_topic}]"]
            relevant = self.get_relevant_notes()
            if not relevant:
                sections.append("*(No relevant notes recorded yet for this topic.)*")
            else:
                for n in relevant:
                    badge = "👤 User" if n.author == "user" else "🧠 Gemini"
                    sections.append(f"• [{badge}] [{n.status}] ({n.topic}): {n.content}")
            self._last_rendered_view = "\n".join(sections)
            return self._last_rendered_view

        # 3. Get Back To View
        elif mode in ("get_back_to", "getbackto", "todo"):
            sections = ["# ⏳ Notes to Get Back To"]
            items = self.get_notes_to_get_back_to()
            if not items:
                sections.append("*(No pending action items or follow-ups to get back to!)*")
            else:
                for n in items:
                    badge = "👤 User" if n.author == "user" else "🧠 Gemini"
                    sections.append(f"• [{badge}] ({n.topic}): {n.content}")
            self._last_rendered_view = "\n".join(sections)
            return self._last_rendered_view

        # 4. Think About View
        elif mode in ("think_about", "thinkabout", "consider"):
            sections = ["# 💡 Notes to Think About"]
            items = self.get_notes_to_think_about()
            if not items:
                sections.append("*(No ideas or thoughts marked for consideration currently.)*")
            else:
                for n in items:
                    badge = "👤 User" if n.author == "user" else "🧠 Gemini"
                    sections.append(f"• [{badge}] ({n.topic}): {n.content}")
            self._last_rendered_view = "\n".join(sections)
            return self._last_rendered_view

        # 5. Archived Notes View
        elif mode in ("archived", "archive"):
            archived = self.get_archived_notes()
            sections = [f"# 📦 Archived Notes ({len(archived)})"]
            if not archived:
                sections.append("*(No archived notes on record. Notes can be archived via /notes archive or manage_notes.)*")
            else:
                for n in archived:
                    badge = "👤 User" if n.author == "user" else "🧠 Gemini"
                    sections.append(f"• [{badge}] [archived] ({n.topic}): {n.content}")
            self._last_rendered_view = "\n".join(sections)
            return self._last_rendered_view

        # 6. All Topics View
        else:
            sections = ["# 📚 All Managed Notes by Topic"]
            all_topics = self.get_all_topics()
            for t_name, count in all_topics:
                t_notes = self.get_notes_by_topic(t_name)
                marker = " [ACTIVE]" if t_name == self.current_topic else ""
                sections.append(f"\n### Topic: {t_name}{marker} ({len(t_notes)} notes)")
                for n in t_notes:
                    badge = "👤 User" if n.author == "user" else "🧠 Gemini"
                    status_lbl = f" [{n.status}]" if n.status else ""
                    sections.append(f"• [{badge}]{status_lbl}: {n.content}")
            self._last_rendered_view = "\n".join(sections)
            return self._last_rendered_view

    def format_prompt_summary(self) -> str:
        """Crisp summary formatted for Gemini's system instructions prompt."""
        think_notes = self.get_notes_to_think_about()
        back_notes = self.get_notes_to_get_back_to()
        rel_notes = self.get_relevant_notes()
        all_topics = self.get_all_topics()
        archived_count = len(self.get_archived_notes())
        topics_str = ", ".join(f"{t}({c})" for t, c in all_topics[:8]) if all_topics else "general"

        clean_w = sanitize_working_notes(self.working_notes)
        lines = [
            f"• ACTIVE TOPIC: {self.current_topic}",
            f"• CURRENT WORKING NOTES: {clean_w or 'None set'}",
        ]

        if rel_notes:
            lines.append("• RELEVANT WORK NOTES:")
            for n in rel_notes[:5]:
                lines.append(f"  - [{n.author}] ({n.topic}/{n.status}): {n.content}")

        if back_notes:
            lines.append("• NOTES TO GET BACK TO:")
            for n in back_notes[:4]:
                lines.append(f"  - [{n.author}] ({n.topic}): {n.content}")

        if think_notes:
            lines.append("• NOTES TO THINK ABOUT:")
            for n in think_notes[:4]:
                lines.append(f"  - [{n.author}] ({n.topic}): {n.content}")

        arch_str = f" | {archived_count} archived" if archived_count > 0 else ""
        lines.append(f"• TOPICS INDEX: [{topics_str}] (Total: {len(self.notes)} notes{arch_str})")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serializes manager state while preserving backward-compatible keys."""
        clean_w = sanitize_working_notes(self.working_notes)
        return {
            "managed_notes": {
                "working_notes": clean_w,
                "current_topic": self.current_topic,
                "notes": [n.to_dict() for n in self.notes],
            },
            # Backward compatibility fields for legacy test & storage routines
            "working_notes": clean_w,
            "gemini_notes": clean_w,
            "global_notes": self.get_global_notes_text(),
            "relational_notes": self.get_relational_notes_dict(),
            "notes": [n.to_dict() for n in self.notes],
        }

    def get_global_notes_text(self) -> str:
        ref_notes = [n.content for n in self.notes if not n.archived and (n.topic == "global" or n.status == "reference")]
        return "\n".join(ref_notes) if ref_notes else ""

    def get_relational_notes_dict(self) -> dict[str, str]:
        rel: dict[str, str] = {}
        for n in self.notes:
            if n.turn_id and not n.archived:
                rel[n.turn_id] = n.content
        return rel

    @classmethod
    def from_dict(cls, data: Any) -> NotesManager:
        return cls.from_data(data)

    @classmethod
    def from_data(cls, data: Any) -> NotesManager:
        """Constructs NotesManager dynamically from arbitrary raw storage data (str, dict, list, or None)."""
        if not data:
            return cls()

        # 1. Plain string (e.g. legacy saves or direct text)
        if isinstance(data, str):
            clean_str = sanitize_working_notes(data)
            mgr = cls(working_notes=clean_str)
            if clean_str:
                mgr.consume_user_input(raw_text=data, active_topic="general")
                if clean_str and not mgr.working_notes:
                    mgr.working_notes = clean_str
            return mgr

        if isinstance(data, dict):
            # 2. Nested managed_notes dict
            if "managed_notes" in data and isinstance(data["managed_notes"], dict):
                inner = data["managed_notes"]
                w_notes = sanitize_working_notes(str(inner.get("working_notes", "") or ""))
                c_topic = str(inner.get("current_topic", "general") or "general")
                items = [NoteItem.from_dict(d) for d in inner.get("notes", []) if isinstance(d, dict)]
                return cls(working_notes=w_notes, current_topic=c_topic, notes=items)

            # 3. Direct manager dict or legacy chat payload
            raw_w = str(data.get("working_notes") or data.get("gemini_notes") or "")
            w_notes = sanitize_working_notes(raw_w)
            c_topic = str(data.get("current_topic", "general") or data.get("topic", "general") or "general")

            items: list[NoteItem] = []
            notes_field = data.get("notes")

            if isinstance(notes_field, list):
                for d in notes_field:
                    if isinstance(d, dict):
                        items.append(NoteItem.from_dict(d))
                    elif isinstance(d, str) and d.strip():
                        clean_d = normalize_note_text(d)
                        if clean_d:
                            items.append(NoteItem(
                                id=f"n_{uuid4().hex[:6]}",
                                topic=c_topic,
                                content=clean_d,
                                status=infer_note_status(clean_d),
                                author="user",
                            ))
            elif isinstance(notes_field, dict):
                nested_mgr = cls.from_data(notes_field)
                if nested_mgr.working_notes and not w_notes:
                    w_notes = nested_mgr.working_notes
                items.extend(nested_mgr.notes)
            elif isinstance(notes_field, str) and notes_field.strip():
                clean_str = sanitize_working_notes(notes_field)
                if clean_str and not w_notes:
                    w_notes = clean_str
                temp_mgr = cls(working_notes=w_notes, current_topic=c_topic)
                temp_mgr.consume_user_input(raw_text=notes_field, active_topic=c_topic)
                items.extend(temp_mgr.notes)

            # Ingest legacy relational_notes
            if "relational_notes" in data and isinstance(data["relational_notes"], dict):
                for tid, text in data["relational_notes"].items():
                    if text and str(text).strip():
                        items.append(NoteItem(
                            id=f"n_{uuid4().hex[:6]}",
                            topic="conversation",
                            content=str(text).strip(),
                            status="working",
                            author="gemini",
                            relevant=True,
                            turn_id=str(tid),
                        ))

            # Ingest legacy global_notes
            if "global_notes" in data and data["global_notes"] and str(data["global_notes"]).strip():
                items.append(NoteItem(
                    id=f"n_{uuid4().hex[:6]}",
                    topic="global",
                    content=str(data["global_notes"]).strip(),
                    status="reference",
                    author="user",
                    relevant=False,
                ))

            # If raw_w has content but no items were created, thoughtfully consume raw_w as note(s)
            if raw_w and not items and not notes_field:
                temp_mgr = cls(working_notes=raw_w, current_topic=c_topic)
                temp_mgr.consume_user_input(raw_text=raw_w, active_topic=c_topic)
                items.extend(temp_mgr.notes)

            return cls(working_notes=w_notes, current_topic=c_topic, notes=items)

        return cls()
