"""Main ChatApp Textual application."""

import asyncio
import os
from pathlib import Path
import subprocess
import tempfile

import pyperclip
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, OptionList
from textual.widgets.option_list import Option

# Ensure Markdown line number patches are applied
import gemini_app.hooks.markdown  # noqa: F401
from gemini_app.config import SOCKET_PATH
from gemini_app.events import RemoteInsert
from gemini_app.screens.frame_modal import FrameSelectModal
from gemini_app.screens.palette import MenuPalette
from gemini_app.screens.title_modal import TitlePromptModal
from gemini_app.services.chat_store import (
    create_chat_session,
    delete_chat,
    get_sorted_chat_files,
    load_chat_data,
    save_chat,
    update_chat_title,
)
from gemini_app.services.emacs import get_emacs_frames, send_to_emacs_buffer
from gemini_app.services.gemini import generate_response
from gemini_app.services.socket_server import SocketServer
from gemini_app.widgets.feed import FeedArea
from gemini_app.widgets.history_list import HistoryList
from gemini_app.widgets.input_area import ExpandingInput
from gemini_app.widgets.snippet_preview import SnippetPreview


class ChatApp(App):
    CSS_PATH = "styles.tcss"
    COMMAND_PALETTE_BINDING = "alt+x"
    COMMAND_PALETTE = MenuPalette

    BINDINGS = [
        Binding("alt+x", "command_palette", "Menu (M-x)", show=True),
        Binding("ctrl+n", "new_chat", "C-c n (New)", show=True),
        Binding("ctrl+b", "toggle_history", "C-c b (History)", show=True),
        Binding("ctrl+y", "copy_last_response", "C-c y (Yank/Emacs)", show=True),
        Binding("ctrl+e", "open_in_editor", "C-c e (Editor)", show=True),
        Binding("ctrl+t", "rename_chat", "C-c t (Rename)", show=True),
        Binding("escape", "toggle_focus", "Focus Swap", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.current_chat_id: str = ""
        self.current_chat_title: str = ""
        self.history: list[dict] = []
        self._server: SocketServer | None = None
        self._prefix_c_c: bool = False

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        super().copy_to_clipboard(text)

    def set_c_c_prefix(self) -> None:
        self._prefix_c_c = True

    def handle_c_c_prefix(self, event: events.Key) -> bool:
        """Centralized Emacs C-c chord interceptor."""
        if not self._prefix_c_c:
            return False

        self._prefix_c_c = False

        if event.key in ("ctrl+n", "n"):
            event.prevent_default(); event.stop()
            self.action_new_chat()
            return True
        elif event.key in ("ctrl+b", "b"):
            event.prevent_default(); event.stop()
            self.action_toggle_history()
            return True
        elif event.key in ("ctrl+e", "e"):
            event.prevent_default(); event.stop()
            self.action_open_in_editor()
            return True
        elif event.key in ("ctrl+y", "y"):
            event.prevent_default(); event.stop()
            self.action_copy_last_response()
            return True
        elif event.key in ("ctrl+t", "t"):
            event.prevent_default(); event.stop()
            self.action_rename_chat()
            return True
        elif event.key in ("ctrl+c", "ctrl+g", "escape"):
            event.prevent_default(); event.stop()
            self.notify("Quit", timeout=1.0)
            return True

        return False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield FeedArea(id="feed")
            yield HistoryList(id="history")
            yield SnippetPreview(id="snippet_preview")
            yield ExpandingInput(id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self._server = SocketServer(SOCKET_PATH, self._handle_remote_insert)
        await self._server.start(on_error=lambda err: self.notify(f"Socket server error: {err}", severity="error"))

        files = get_sorted_chat_files()
        if files:
            first_id = files[0].stem
            await self.load_chat(first_id)
        else:
            self._start_new_chat(title="")

        self.query_one("#input").focus()

    def _handle_remote_insert(self, payload: dict) -> None:
        self.post_message(RemoteInsert(
            text=payload.get("text", ""),
            lang=payload.get("lang", ""),
            file=payload.get("file", ""),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line"),
        ))

    @on(RemoteInsert)
    def on_remote_insert(self, event: RemoteInsert) -> None:
        input_widget = self.query_one("#input", ExpandingInput)
        preview_widget = self.query_one("#snippet_preview", SnippetPreview)

        input_widget.focus()
        tag, num = input_widget.register_and_insert_snippet(
            code=event.text,
            lang=event.lang,
            file=event.file,
            start_line=event.start_line,
            end_line=event.end_line,
        )

        preview_widget.show_snippet(
            tag=tag,
            num=num,
            code=event.text,
            lang=event.lang,
            file=event.file,
            start_line=event.start_line,
            end_line=event.end_line,
        )

        loc = f" ({event.file}:{event.start_line}-{event.end_line})" if event.file else ""
        self.notify(f"Inserted {tag}{loc} at cursor")

    def on_unmount(self) -> None:
        if self._server:
            self._server.stop()

    def refresh_history_list(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        history_widget.clear_options()

        files = get_sorted_chat_files()
        for idx, f in enumerate(files):
            data = load_chat_data(f.stem)
            if data:
                title = data.get("title", f.stem)
                active = " (Active)" if data["id"] == self.current_chat_id else ""
                history_widget.add_option(
                    Option(prompt=f"{idx + 1}. {title}{active}", id=data["id"])
                )

    async def load_chat(self, chat_id: str) -> None:
        self.current_chat_id = chat_id
        data = load_chat_data(chat_id)
        if data:
            self.history = data.get("messages", [])
            self.current_chat_title = data.get("title", "")
        else:
            self.history = []
            self.current_chat_title = ""

        feed = self.query_one("#feed", FeedArea)
        await feed.set_messages(self.history)
        self.query_one("#input", ExpandingInput).reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()

    def save_current_chat(self) -> None:
        if not self.current_chat_id or not self.history:
            return
        self.current_chat_title = save_chat(
            self.current_chat_id,
            self.current_chat_title,
            self.history,
        )

    async def delete_highlighted_chat(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        if history_widget.highlighted is None or history_widget.option_count == 0:
            return

        option = history_widget.get_option_at_index(history_widget.highlighted)
        target_id = str(option.id)
        delete_chat(target_id)

        files = get_sorted_chat_files()
        if self.current_chat_id == target_id:
            if files:
                await self.load_chat(files[0].stem)
            else:
                self._start_new_chat(title="")
                return

        current_idx = history_widget.highlighted
        self.refresh_history_list()
        if history_widget.option_count > 0:
            history_widget.highlighted = min(
                current_idx, history_widget.option_count - 1
            )

    def rename_highlighted_chat(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        if history_widget.highlighted is None or history_widget.option_count == 0:
            return

        option = history_widget.get_option_at_index(history_widget.highlighted)
        target_id = str(option.id)
        data = load_chat_data(target_id)
        if not data:
            return

        current_title = data.get("title", "")

        def on_rename(new_title: str | None) -> None:
            if new_title is not None and new_title.strip():
                clean_title = new_title.strip()
                update_chat_title(target_id, clean_title)
                if target_id == self.current_chat_id:
                    self.current_chat_title = clean_title
                self.refresh_history_list()
                self.notify("Chat renamed.")

        self.push_screen(
            TitlePromptModal(prompt="Edit chat title:", default_title=current_title),
            callback=on_rename,
        )

    def action_next_snippet(self) -> None:
        self.query_one("#feed", FeedArea).navigate_snippet(1)

    def action_prev_snippet(self) -> None:
        self.query_one("#feed", FeedArea).navigate_snippet(-1)

    def action_rename_chat(self) -> None:
        def on_renamed(new_title: str | None) -> None:
            if new_title is not None and new_title.strip():
                self.current_chat_title = new_title.strip()
                self.save_current_chat()
                self.notify(f"Renamed chat to: {self.current_chat_title}")

        self.push_screen(
            TitlePromptModal(
                prompt="Edit chat title:",
                default_title=self.current_chat_title,
            ),
            callback=on_renamed,
        )

    def action_toggle_focus(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        preview_box = self.query_one("#snippet_preview", SnippetPreview)
        input_widget = self.query_one("#input", ExpandingInput)

        if feed.has_focus:
            if preview_box.styles.display != "none":
                preview_box.focus()
            else:
                input_widget.focus()
        elif preview_box.has_focus:
            input_widget.focus()
        else:
            feed.focus()

    def action_toggle_history(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        history_widget = self.query_one("#history", HistoryList)
        input_widget = self.query_one("#input", ExpandingInput)

        if history_widget.styles.display == "none":
            self.refresh_history_list()
            feed.styles.display = "none"
            history_widget.styles.display = "block"
            history_widget.focus()
        else:
            history_widget.styles.display = "none"
            feed.styles.display = "block"
            input_widget.focus()

    def action_new_chat(self) -> None:
        def on_title_chosen(chosen_title: str | None) -> None:
            if chosen_title is None:
                return
            self._start_new_chat(title=chosen_title)

        self.push_screen(
            TitlePromptModal(prompt="Enter topic for new chat:"),
            callback=on_title_chosen,
        )

    def _start_new_chat(self, title: str) -> None:
        self.query_one("#history").styles.display = "none"
        self.query_one("#feed").styles.display = "block"

        self.current_chat_id, self.current_chat_title = create_chat_session(title)
        self.history = []

        self.query_one("#feed", FeedArea).clear()
        input_widget = self.query_one("#input", ExpandingInput)
        input_widget.reset_snippets()
        self.query_one("#snippet_preview", SnippetPreview).hide_preview()
        input_widget.focus()

    def action_copy_last_response(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        snippet_text = feed.get_active_snippet()

        text_to_send = ""
        if snippet_text is not None:
            text_to_send = snippet_text
        else:
            for turn in reversed(self.history):
                if turn["role"] == "model":
                    text_to_send = turn["text"]
                    break

        if not text_to_send:
            self.notify("Nothing to yank.", severity="warning")
            return

        self.copy_to_clipboard(text_to_send)
        frames = get_emacs_frames()

        if len(frames) <= 1:
            success = send_to_emacs_buffer(text_to_send)
            if success:
                self.notify("Yanked & sent to active Emacs window")
            else:
                self.notify("Yanked to clipboard")
            return

        def on_window_chosen(chosen: dict | None) -> None:
            if chosen:
                buf = chosen.get("buf_name")
                send_to_emacs_buffer(text_to_send, target_buf=buf)
                self.notify(f"Sent to {chosen.get('file_name')}")

        self.push_screen(FrameSelectModal(frames), callback=on_window_chosen)

    def action_open_in_editor(self) -> None:
        feed = self.query_one("#feed", FeedArea)
        if not getattr(feed, "_raw_markdown", ""):
            self.notify("No conversation to open.", severity="warning")
            return

        editor = os.environ.get("EDITOR") or os.environ.get("PAGER") or "nano"

        with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", delete=False, encoding="utf-8") as tmp:
            tmp.write(feed._raw_markdown)
            tmp.flush()
            tmp_path = tmp.name

        try:
            with self.suspend():
                subprocess.run([editor, tmp_path])
        except Exception as e:
            self.notify(f"Failed to launch editor: {e}", severity="error")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @on(OptionList.OptionSelected, "#history")
    async def on_history_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            await self.load_chat(str(event.option_id))
            self.query_one("#history").styles.display = "none"
            self.query_one("#feed").styles.display = "block"
            self.query_one("#input").focus()

    async def append_to_feed(self, sender: str, text: str) -> None:
        feed = self.query_one("#feed", FeedArea)
        await feed.append_message(sender, text)

    async def on_expanding_input_submitted(self, event: ExpandingInput.Submitted) -> None:
        user_msg = event.value
        await self.append_to_feed("You", user_msg)

        self.history.append({"role": "user", "text": user_msg})
        self.save_current_chat()

        self.ask_gemini()

    @work(exclusive=True)
    async def ask_gemini(self) -> None:
        chat_id_snapshot = self.current_chat_id
        try:
            reply = await generate_response(self.history)
        except Exception as e:
            self.notify(f"API Error: {e}", severity="error")
            return

        if self.current_chat_id == chat_id_snapshot:
            self.history.append({"role": "model", "text": reply})
            self.save_current_chat()
            await self.append_to_feed("Gemini", reply)
