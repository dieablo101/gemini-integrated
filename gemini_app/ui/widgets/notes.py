"""Notes panel components supporting Gemini Work Notes, Relational Turn Notes, and Global Notes."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Static, TextArea

from gemini_app.ui.widgets.text_areas import EmacsBaseTextArea
from gemini_app.ui.widgets.feed import FeedArea

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp


class NotesEditorArea(EmacsBaseTextArea):
    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_nav_time: float = 0.0
        self._nav_cooldown: float = 0.022
        self._suppress_change_sync: bool = False

    def on_mount(self) -> None:
        super().on_mount()
        self.show_line_numbers = False

    def _cycle_relational_note(self, delta: int) -> None:
        app: ChatApp = self.app  # type: ignore
        feed = app.query_one("#feed", FeedArea)
        all_turns = getattr(feed, "_all_messages", [])
        rel_dict = getattr(app, "relational_notes", {})
        id_to_idx = {t.get("turn_id"): i for i, t in enumerate(all_turns) if t.get("turn_id")}
        noted_indices = sorted([id_to_idx[tid] for tid, c in rel_dict.items() if c and c.strip() and tid in id_to_idx])
        if not noted_indices:
            app.notify("No relational notes in session yet.", timeout=2.0)
            return
        curr = getattr(app, "current_focused_turn_index", 0)
        if curr in noted_indices:
            idx_in_list = noted_indices.index(curr)
            next_idx = noted_indices[(idx_in_list + delta) % len(noted_indices)]
        else:
            next_idx = noted_indices[0] if delta > 0 else noted_indices[-1]
        feed.jump_to_turn(next_idx)
        try:
            panel = app.query_one("#notes_panel", NotesPanel)
            if getattr(app, "active_notes_mode", "") != "turn":
                panel.switch_mode("turn")
        except Exception:
            pass

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._suppress_change_sync or not self.has_focus:
            return

        app: ChatApp = self.app  # type: ignore
        mode = getattr(app, "active_notes_mode", "gemini")

        if mode == "global":
            app.global_notes = self.text
            app.schedule_notes_flush()
        elif mode == "turn":
            active_tid = getattr(app, "current_focused_turn_id", "")
            if active_tid:
                app.relational_notes[active_tid] = self.text
                app.schedule_notes_flush()
                # Update visual note badge on active turn card
                try:
                    feed = app.query_one("#feed", FeedArea)
                    card = feed._get_target_widget_by_id(active_tid)
                    if card:
                        card.update_display()
                except Exception:
                    pass
                try:
                    notes_panel = app.query_one("#notes_panel", NotesPanel)
                    notes_panel.refresh_related_chips()
                except Exception:
                    pass
        else:  # "gemini"
            app.gemini_notes = self.text
            app.schedule_notes_flush()

    def _on_key(self, event: events.Key) -> None:
        if self.app.intercept_c_c_key(event):
            return

        # Fast mode switching shortcuts: Alt+1 / Alt+2 / Alt+3
        if event.key in ("alt+1", "meta+1"):
            event.prevent_default()
            event.stop()
            try:
                self.app.query_one("#notes_panel", NotesPanel).switch_mode("gemini")
            except Exception:
                pass
            return
        elif event.key in ("alt+2", "meta+2"):
            event.prevent_default()
            event.stop()
            try:
                self.app.query_one("#notes_panel", NotesPanel).switch_mode("turn")
            except Exception:
                pass
            return
        elif event.key in ("alt+3", "meta+3"):
            event.prevent_default()
            event.stop()
            try:
                self.app.query_one("#notes_panel", NotesPanel).switch_mode("global")
            except Exception:
                pass
            return

        if event.key in ("alt+left", "meta+left"):
            event.prevent_default()
            event.stop()
            self._cycle_relational_note(-1)
            return
        elif event.key in ("alt+right", "meta+right"):
            event.prevent_default()
            event.stop()
            self._cycle_relational_note(1)
            return

        if event.key in ("ctrl+j", "shift+enter", "shift+return"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return

        if event.key in ("enter", "return"):
            event.prevent_default()
            event.stop()
            self.app.flush_current_notes()
            self.app.action_toggle_notes()
            return

        if event.key in ("escape", "ctrl+g"):
            event.prevent_default()
            event.stop()
            if self._mark_point is not None or self.selected_text:
                self._clear_mark()
                self.app.notify("Quit", timeout=1.0)
            else:
                self.app.flush_current_notes()
                self.app.action_toggle_notes()
            return

        if event.key in ("tab", "shift+tab"):
            event.prevent_default()
            event.stop()
            direction = -1 if event.key == "shift+tab" else 1
            self.app.cycle_global_focus(direction=direction)
            return

        # Feed navigation keys while in notes panel for lock-step inspection
        feed = self.app.query_one("#feed", FeedArea)
        now = time.monotonic()
        if event.key in ("down", "up", "shift+up", "shift+down"):
            if now - self._last_nav_time < self._nav_cooldown:
                event.prevent_default()
                event.stop()
                return
            self._last_nav_time = now

        if event.key in ("shift+up", "shift+down"):
            event.prevent_default()
            event.stop()
            direction = -1 if event.key == "shift+up" else 1
            feed.viewport_page_navigate(direction)
            return
        elif event.key == "down":
            event.prevent_default()
            event.stop()
            feed.arrow_navigate(1)
            return
        elif event.key == "up":
            event.prevent_default()
            event.stop()
            feed.arrow_navigate(-1)
            return
        elif event.key == "pagedown":
            event.prevent_default()
            event.stop()
            feed.step_card(1)
            return
        elif event.key == "pageup":
            event.prevent_default()
            event.stop()
            feed.step_card(-1)
            return
        elif event.key in ("alt+n", "meta+n"):
            event.prevent_default()
            event.stop()
            feed.navigate_snippet(1)
            return
        elif event.key in ("alt+p", "meta+p"):
            event.prevent_default()
            event.stop()
            feed.navigate_snippet(-1)
            return
        elif event.key == "home":
            event.prevent_default()
            event.stop()
            feed.jump_to_home()
            return
        elif event.key == "end":
            event.prevent_default()
            event.stop()
            feed.jump_to_end()
            return

        super()._on_key(event)


class NotesPanel(Vertical):
    """Tri-modal Notes Panel supporting Gemini Notes, Contextual Turn Notes, and Global Notes."""

    def __init__(self, **kwargs) -> None:
        super().__init__(id="notes_panel", **kwargs)
        self.border_title = " 🧠 Gemini Notes "

    def clear_session_expansion_states(self) -> None:
        """Compatibility helper for session reset."""
        pass

    def compose(self) -> ComposeResult:
        with Horizontal(id="notes_tabs_row"):
            yield Static("🧠 Gemini", id="tab_gemini", classes="notes_tab tab-active")
            yield Static("🎯 Turn Note", id="tab_turn", classes="notes_tab")
            yield Static("🌐 Global", id="tab_global", classes="notes_tab")
        with Horizontal(id="notes_chips_row"):
            yield Static("Related Notes:", id="notes_chips_title", classes="notes_chips_title")
        yield Static("Mode: 🧠 Gemini Work Notes | Alt+1: Gemini | Alt+2: Turn | Alt+3: Global", id="notes_header_info")
        yield NotesEditorArea(id="notes_editor")

    def refresh_related_chips(self) -> None:
        """Refreshes the horizontal chip row of all turns in this session that possess relational notes."""
        app: ChatApp = self.app  # type: ignore
        try:
            chips_row = self.query_one("#notes_chips_row", Horizontal)
        except Exception:
            return

        rel_dict = getattr(app, "relational_notes", {})
        active_t_id = getattr(app, "current_focused_turn_id", "")
        feed = app.query_one("#feed", FeedArea)
        all_turns = getattr(feed, "_all_messages", [])

        id_to_idx = {t.get("turn_id"): i for i, t in enumerate(all_turns) if t.get("turn_id")}

        noted_indices: list[tuple[int, str]] = []
        for tid, content in rel_dict.items():
            if content and content.strip() and tid in id_to_idx:
                noted_indices.append((id_to_idx[tid], tid))

        noted_indices.sort(key=lambda x: x[0])

        # Remove existing chips
        for child in list(chips_row.children):
            if "note_chip" in child.classes:
                child.remove()

        if not noted_indices:
            chips_row.styles.display = "none"
            return

        chips_row.styles.display = "block"
        for t_idx, tid in noted_indices:
            is_active = (tid == active_t_id)
            active_class = " chip-active" if is_active else ""
            chip = Static(f"T#{t_idx + 1}", id=f"chip_turn_{t_idx}", classes=f"note_chip{active_class}")
            chips_row.mount(chip)

    def switch_mode(self, new_mode: str) -> None:
        app: ChatApp = self.app  # type: ignore
        old_mode = getattr(app, "active_notes_mode", "gemini")

        # 1. Flush current editor content to appropriate buffer
        app.flush_current_notes()

        # 2. Update active mode
        app.active_notes_mode = new_mode

        # 3. Update tab highlighting
        for tab_id, m in (("tab_gemini", "gemini"), ("tab_turn", "turn"), ("tab_global", "global")):
            try:
                w = self.query_one(f"#{tab_id}", Static)
                if m == new_mode:
                    w.add_class("tab-active")
                else:
                    w.remove_class("tab-active")
            except Exception:
                pass

        # 4. Load corresponding content into editor
        editor = self.query_one("#notes_editor", NotesEditorArea)
        hint = self.query_one("#notes_header_info", Static)

        editor._suppress_change_sync = True
        try:
            if new_mode == "gemini":
                self.border_title = " 🧠 Gemini Notes "
                hint.update("Mode: 🧠 Gemini Work Notes | Alt+1: Gemini | Alt+2: Turn | Alt+3: Global")
                editor.load_text(getattr(app, "gemini_notes", "") or "")
            elif new_mode == "turn":
                turn_idx = getattr(app, "current_focused_turn_index", 0)
                turn_id = getattr(app, "current_focused_turn_id", "")
                turn_label = f"Turn #{turn_idx + 1}" if turn_idx >= 0 else "Active Turn"
                self.border_title = f" 🎯 Relational Note ({turn_label}) "
                hint.update(f"Attached to {turn_label} | Alt+1: Gemini | Alt+2: Turn | Alt+3: Global")
                note_text = app.relational_notes.get(turn_id, "") if turn_id else ""
                editor.load_text(note_text)
            else:  # "global"
                self.border_title = " 🌐 Global Notes "
                hint.update("Mode: 🌐 Global Persistent Notes | Alt+1: Gemini | Alt+2: Turn | Alt+3: Global")
                editor.load_text(getattr(app, "global_notes", "") or "")

            editor.move_cursor(editor.document.end, select=False)
        finally:
            editor._suppress_change_sync = False

        self.refresh_related_chips()

    def on_turn_changed(self, turn_idx: int, turn_id: str, sender: str = "") -> None:
        """Called whenever the active card in the 10-card feed slider changes."""
        app: ChatApp = self.app  # type: ignore

        # Update the turn tab label to indicate which turn is centered
        try:
            tab_turn = self.query_one("#tab_turn", Static)
            tab_turn.update(f"🎯 Turn #{turn_idx + 1}")
        except Exception:
            pass

        # If currently in turn mode, seamlessly switch the note to the newly centered turn
        if getattr(app, "active_notes_mode", "gemini") == "turn":
            editor = self.query_one("#notes_editor", NotesEditorArea)
            hint = self.query_one("#notes_header_info", Static)

            # Flush current editor to previous turn_id if different
            old_tid = getattr(app, "current_focused_turn_id", "")
            if old_tid and old_tid != turn_id and editor.has_focus:
                app.relational_notes[old_tid] = editor.text

            app.current_focused_turn_index = turn_idx
            app.current_focused_turn_id = turn_id

            sender_info = f" ({sender})" if sender else ""
            self.border_title = f" 🎯 Relational Note (Turn #{turn_idx + 1}{sender_info}) "
            hint.update(f"Attached to Turn #{turn_idx + 1}{sender_info} | Alt+1: Gemini | Alt+2: Turn | Alt+3: Global")

            editor._suppress_change_sync = True
            try:
                note_text = app.relational_notes.get(turn_id, "")
                editor.load_text(note_text)
                editor.move_cursor(editor.document.end, select=False)
            finally:
                editor._suppress_change_sync = False
        else:
            app.current_focused_turn_index = turn_idx
            app.current_focused_turn_id = turn_id

        self.refresh_related_chips()

    @on(events.Click, "#tab_gemini")
    def on_gemini_tab_click(self) -> None:
        self.switch_mode("gemini")
        self.query_one("#notes_editor", NotesEditorArea).focus()

    @on(events.Click, "#tab_turn")
    def on_turn_tab_click(self) -> None:
        self.switch_mode("turn")
        self.query_one("#notes_editor", NotesEditorArea).focus()

    @on(events.Click, "#tab_global")
    def on_global_tab_click(self) -> None:
        self.switch_mode("global")
        self.query_one("#notes_editor", NotesEditorArea).focus()

    @on(events.Click, ".note_chip")
    def on_chip_click(self, event: events.Click) -> None:
        chip = event.widget
        chip_id = getattr(chip, "id", "")
        if chip_id and chip_id.startswith("chip_turn_"):
            try:
                target_idx = int(chip_id.split("_")[-1])
                app: ChatApp = self.app  # type: ignore
                feed = app.query_one("#feed", FeedArea)
                feed.jump_to_turn(target_idx)
                if app.active_notes_mode != "turn":
                    self.switch_mode("turn")
                self.query_one("#notes_editor", NotesEditorArea).focus()
            except Exception:
                pass
