"""Unified Gemini-Managed Notes Engine.

Provides topic association, cognitive categorization (working, think_about, get_back_to),
chat scanning, user-note ingestion, relevance filtering, and persistence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
import time
from typing import Any
from uuid import uuid4


@dataclass
class NoteItem:
    """Represents a single atomic note managed by Gemini."""

    id: str
    topic: str
    content: str
    status: str = "working"  # "working", "think_about", "get_back_to", "completed", "reference"
    author: str = "gemini"  # "gemini" or "user"
    relevant: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turn_id: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NoteItem:
        return cls(
            id=data.get("id") or f"n_{uuid4().hex[:6]}",
            topic=(data.get("topic") or "general").strip().lower(),
            content=str(data.get("content") or "").strip(),
            status=data.get("status") or "working",
            author=data.get("author") or "gemini",
            relevant=bool(data.get("relevant", True)),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            turn_id=str(data.get("turn_id") or ""),
            tags=list(data.get("tags") or []),
        )


class NotesManager:
    """Unified Notes Engine managing all project notes, topics, follow-ups, and working state."""

    def __init__(
        self,
        working_notes: str = "",
        current_topic: str = "general",
        notes: list[NoteItem] | None = None,
        active_topic: str | None = None,
    ) -> None:
        self.working_notes: str = (working_notes or "").strip()
        topic_to_use = active_topic or current_topic or "general"
        self.current_topic: str = (topic_to_use or "general").strip().lower()
        self.notes: list[NoteItem] = notes or []
        self._last_rendered_view: str = ""

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
        self.working_notes = (content or "").strip()

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
    ) -> NoteItem:
        """Records a new note or updates an existing one associated with a topic."""
        clean_content = (content or "").strip()
        clean_topic = (topic or self.current_topic or "general").strip().lower()
        status_clean = (status or "working").strip().lower()

        # Normalize status aliases
        if status_clean in ("think", "thinkabout", "ponder", "consider"):
            status_clean = "think_about"
        elif status_clean in ("getback", "getbackto", "todo", "followup", "follow_up", "action"):
            status_clean = "get_back_to"
        elif status_clean in ("done", "finished"):
            status_clean = "completed"

        # Update if ID exists
        if note_id:
            for item in self.notes:
                if item.id == note_id:
                    item.content = clean_content
                    item.topic = clean_topic
                    item.status = status_clean
                    item.relevant = relevant
                    item.updated_at = time.time()
                    if tags is not None:
                        item.tags = tags
                    return item

        # Check for duplicate content under same topic to update in place
        for item in self.notes:
            if item.topic == clean_topic and item.content.lower() == clean_content.lower():
                item.status = status_clean
                item.relevant = relevant
                item.updated_at = time.time()
                if author == "user":
                    item.author = "user"
                return item

        new_item = NoteItem(
            id=note_id or f"n_{uuid4().hex[:6]}",
            topic=clean_topic,
            content=clean_content,
            status=status_clean,
            author=author,
            relevant=relevant,
            created_at=time.time(),
            updated_at=time.time(),
            turn_id=turn_id,
            tags=tags or [],
        )
        self.notes.append(new_item)
        return new_item

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
        if "# 🧠 Gemini Working Notes" in text or "# 📌 Relevant Notes" in text:
            consumed: list[NoteItem] = []

            # Extract Working Notes section
            w_match = re.search(r"# 🧠 Gemini Working Notes.*?\n(.*?)(?=\n#|\Z)", text, re.DOTALL)
            if w_match:
                extracted_w = w_match.group(1).strip()
                placeholder = "*(No active working notes set. Gemini updates working notes autonomously as tasks proceed.)*"
                if extracted_w and extracted_w != placeholder:
                    self.working_notes = extracted_w

            # Extract any newly added notes or lines outside the template headers
            # Match bullet points like "• [👤 User] ...", "• ...", or lines starting with "-" or "*"
            lines = text.split("\n")
            for line in lines:
                l_clean = line.strip()
                if not l_clean or l_clean.startswith("#") or "*(No " in l_clean:
                    continue

                # Strip bullet symbol and badges
                cleaned_line = re.sub(r"^[•\-\*]\s*", "", l_clean).strip()
                cleaned_line = re.sub(r"^\[(?:👤 User|🧠 Gemini)\]\s*", "", cleaned_line).strip()

                # Check topic tag in parenthesis: e.g. (ui): content
                line_topic = target_topic
                t_match = re.search(r"^\(([a-zA-Z0-9_\-]+)\):\s*(.+)$", cleaned_line)
                if t_match:
                    line_topic = t_match.group(1).strip().lower()
                    cleaned_line = t_match.group(2).strip()

                # Infer status
                status = "think_about"
                cl_lower = cleaned_line.lower()
                if any(w in cl_lower for w in ("todo", "must", "get back", "fix", "remember to", "need to", "action:")):
                    status = "get_back_to"
                elif any(w in cl_lower for w in ("working on", "in progress", "current task", "implementing")):
                    status = "working"

                item = self.record_note(
                    content=cleaned_line,
                    topic=line_topic,
                    status=status,
                    author="user",
                    relevant=True,
                    turn_id=turn_id,
                )
                consumed.append(item)

            return consumed

        # Pure raw input: parse explicit topic directive
        topic_match = re.search(r"(?:^|\n)(?:#\s*topic:|\bTopic:)\s*([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
        if topic_match:
            target_topic = topic_match.group(1).strip().lower()
            text = re.sub(r"(?:^|\n)(?:#\s*topic:|\bTopic:)\s*[a-zA-Z0-9_\-]+", "", text, flags=re.IGNORECASE).strip()

        # Infer status from text semantics
        status = "think_about"
        text_lower = text.lower()
        if any(w in text_lower for w in ("todo", "must", "get back", "fix", "remember to", "need to", "action:")):
            status = "get_back_to"
        elif any(w in text_lower for w in ("working on", "in progress", "current task", "implementing")):
            status = "working"

        extracted_tags = re.findall(r"#([a-zA-Z0-9_\-]+)", text)

        item = self.record_note(
            content=text,
            topic=target_topic,
            status=status,
            author="user",
            relevant=True,
            turn_id=turn_id,
            tags=extracted_tags,
        )
        return [item]

    def scan_chat_for_notes(self, history: list[dict], default_topic: str = "") -> list[NoteItem]:
        """Scans conversation chat turns, extracts notes and directives, and associates them with topics."""
        new_items: list[NoteItem] = []
        base_topic = (default_topic or self.current_topic or "general").strip().lower()

        directive_regex = re.compile(
            r"(?:^|\n)((?:NOTE|Note|note|REMEMBER TO|Remember to|REMEMBER|Remember|TODO|Todo|todo|FIX|Fix|NEED TO|Need to|MUST|Must|THINK ABOUT|Think about|GET BACK TO|Get back to|ACTION|Action)s?):\s*(.+?)(?=\n(?:[A-Z#•\*-]|\Z)|\Z)",
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
                content = raw_content.strip()
                if not content or len(content) < 3:
                    continue

                p_lower = prefix.lower()
                c_lower = content.lower()

                # Infer status from directive prefix and content
                if any(w in p_lower or w in c_lower for w in ("todo", "must", "get back", "fix", "remember", "need to", "action")):
                    status = "get_back_to"
                elif any(w in p_lower or w in c_lower for w in ("think", "consider", "ponder", "idea", "brainstorm")):
                    status = "think_about"
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
                new_items.append(item)

        return new_items

    def delete_note(self, note_id: str) -> bool:
        initial_len = len(self.notes)
        self.notes = [n for n in self.notes if n.id != note_id]
        return len(self.notes) < initial_len

    def get_notes(
        self,
        topic: str | None = None,
        status: str | None = None,
        author: str | None = None,
        relevant_only: bool = False,
    ) -> list[NoteItem]:
        results = list(self.notes)
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
        # Returns notes marked relevant, or matching active topic, or user notes not completed
        relevant = [
            n for n in self.notes
            if n.relevant or n.topic == active_t or (n.author == "user" and n.status != "completed")
        ]
        return relevant

    def get_notes_to_think_about(self) -> list[NoteItem]:
        return [n for n in self.notes if n.status == "think_about"]

    def get_notes_to_get_back_to(self) -> list[NoteItem]:
        return [n for n in self.notes if n.status == "get_back_to"]

    def get_notes_by_topic(self, topic: str) -> list[NoteItem]:
        clean_t = (topic or "").strip().lower()
        return [n for n in self.notes if n.topic == clean_t]

    def get_all_topics(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for n in self.notes:
            counts[n.topic] = counts.get(n.topic, 0) + 1
        if self.current_topic not in counts:
            counts[self.current_topic] = 0
        sorted_topics = sorted(counts.items(), key=lambda x: (x[0] != self.current_topic, -x[1], x[0]))
        return sorted_topics

    def search_notes(self, query: str) -> list[NoteItem]:
        q = (query or "").strip().lower()
        if not q:
            return list(self.notes)
        matches = []
        for n in self.notes:
            if q in n.content.lower() or q in n.topic.lower() or q in n.status.lower() or any(q in t.lower() for t in n.tags):
                matches.append(n)
        return matches

    def format_working_view(self, view_mode: str = "working") -> str:
        """Formats the Markdown view displayed inside the Notes Editor Area."""
        mode = (view_mode or "working").strip().lower()

        # 1. Working Notes View (Default: Working Notes + Relevant User & Topic Notes)
        if mode in ("working", "gemini"):
            sections = []
            sections.append(f"# 🧠 Gemini Working Notes [Topic: {self.current_topic}]")
            if self.working_notes:
                sections.append(self.working_notes)
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

        # 5. All Topics View
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
        topics_str = ", ".join(f"{t}({c})" for t, c in all_topics[:8]) if all_topics else "general"

        lines = [
            f"• ACTIVE TOPIC: {self.current_topic}",
            f"• CURRENT WORKING NOTES: {self.working_notes or 'None set'}",
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

        lines.append(f"• TOPICS INDEX: [{topics_str}] (Total: {len(self.notes)} notes)")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serializes manager state while preserving backward-compatible keys."""
        return {
            "managed_notes": {
                "working_notes": self.working_notes,
                "current_topic": self.current_topic,
                "notes": [n.to_dict() for n in self.notes],
            },
            # Backward compatibility fields for legacy test & storage routines
            "working_notes": self.working_notes,
            "gemini_notes": self.working_notes,
            "global_notes": self.get_global_notes_text(),
            "relational_notes": self.get_relational_notes_dict(),
            "notes": [n.to_dict() for n in self.notes],
        }

    def get_global_notes_text(self) -> str:
        ref_notes = [n.content for n in self.notes if n.topic == "global" or n.status == "reference"]
        return "\n".join(ref_notes) if ref_notes else ""

    def get_relational_notes_dict(self) -> dict[str, str]:
        rel: dict[str, str] = {}
        for n in self.notes:
            if n.turn_id:
                rel[n.turn_id] = n.content
        return rel

    @classmethod
    def from_dict(cls, data: Any) -> NotesManager:
        return cls.from_data(data)

    @classmethod
    def from_data(cls, data: Any) -> NotesManager:
        """Constructs NotesManager from arbitrary raw storage data (str, dict, or None)."""
        if not data:
            return cls()

        # Handle plain string from old saves
        if isinstance(data, str):
            clean_str = data.strip()
            return cls(working_notes=clean_str)

        if isinstance(data, dict):
            # Nested managed_notes dict
            if "managed_notes" in data and isinstance(data["managed_notes"], dict):
                inner = data["managed_notes"]
                w_notes = str(inner.get("working_notes", "") or "")
                c_topic = str(inner.get("current_topic", "general") or "general")
                items = [NoteItem.from_dict(d) for d in inner.get("notes", []) if isinstance(d, dict)]
                return cls(working_notes=w_notes, current_topic=c_topic, notes=items)

            # Direct manager dict
            if "working_notes" in data or "notes" in data:
                w_notes = str(data.get("working_notes") or data.get("gemini_notes") or "")
                c_topic = str(data.get("current_topic", "general") or "general")
                items = [NoteItem.from_dict(d) for d in data.get("notes", []) if isinstance(d, dict)]

                # Ingest legacy relational_notes if notes list was empty
                if not items and "relational_notes" in data and isinstance(data["relational_notes"], dict):
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

                # Ingest legacy global_notes if notes list was empty
                if "global_notes" in data and data["global_notes"] and str(data["global_notes"]).strip():
                    items.append(NoteItem(
                        id=f"n_{uuid4().hex[:6]}",
                        topic="global",
                        content=str(data["global_notes"]).strip(),
                        status="reference",
                        author="user",
                        relevant=False,
                    ))

                return cls(working_notes=w_notes, current_topic=c_topic, notes=items)

        return cls()
