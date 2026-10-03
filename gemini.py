#!/opt/gemini/.venv/bin/python3

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

import pyperclip
from google import genai
from rich.syntax import Syntax
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, Markdown, OptionList, TextArea
from textual.widgets.markdown import MarkdownFence
from textual.widgets.option_list import Option

CHATS_DIR = Path("chats")
CHATS_DIR.mkdir(exist_ok=True)


class TitlePromptModal(ModalScreen[str | None]):
    """Modal dialog prompting the user for a chat topic/title."""

    DEFAULT_CSS = """
    TitlePromptModal {
        align: center middle;
    }

    #dialog {
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick dodgerblue;
        background: $surface;
    }

    #dialog Label {
        margin-bottom: 1;
        text-style: bold;
    }

    #dialog Input {
        margin-bottom: 1;
    }

    #dialog-buttons {
        width: 100%;
        align-horizontal: right;
    }

    #dialog-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, prompt: str = "Enter chat topic / title:", default_title: str = "") -> None:
        super().__init__()
        self.prompt_text = prompt
        self.default_title = default_title

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.prompt_text)
            yield Input(
                placeholder="Leave blank for auto-generated title...",
                value=self.default_title,
                id="title_input",
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel_btn")
                yield Button("Confirm", variant="primary", id="confirm_btn")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted, "#title_input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    @on(Button.Pressed, "#confirm_btn")
    def on_confirm_pressed(self) -> None:
        val = self.query_one(Input).value.strip()
        self.dismiss(val)

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)


class ExpandingInput(TextArea):
    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def on_mount(self) -> None:
        self.show_line_numbers = False
        self._update_layout()

    def _on_key(self, event: events.Key) -> None:
        # Submit & Newlines
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.action_submit()
        elif event.key in ("shift+enter", "ctrl+j"):
            event.prevent_default()
            event.stop()
            self.action_newline()
        elif event.key in ("ctrl+c", "y"):
            if self.selected_text:
                event.prevent_default()
                event.stop()
                self.app.copy_to_clipboard(self.selected_text)

        # Emacs / CLI power tools
        elif event.key == "ctrl+u":
            event.prevent_default()
            event.stop()
            self.clear()
            self._update_layout()
        elif event.key in ("pageup", "alt+up"):
            event.prevent_default()
            event.stop()
            self.app.query_one("#feed", FeedArea).focus()

        # App Actions passed through
        elif event.key == "ctrl+b":
            event.prevent_default()
            event.stop()
            self.app.action_toggle_history()
        elif event.key == "ctrl+n":
            event.prevent_default()
            event.stop()
            self.app.action_new_chat()
        elif event.key == "ctrl+t":
            event.prevent_default()
            event.stop()
            self.app.action_rename_chat()
        elif event.key == "ctrl+y":
            event.prevent_default()
            event.stop()
            self.app.action_copy_last_response()
        elif event.key == "ctrl+e":
            event.prevent_default()
            event.stop()
            self.app.action_open_in_editor()
        elif event.key in ("escape", "ctrl+o"):
            event.prevent_default()
            event.stop()
            self.app.action_toggle_focus()
        else:
            super()._on_key(event)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._update_layout()

    def _update_layout(self) -> None:
        lines = self.document.line_count
        self.styles.height = min(max(lines, 1), 5) + 2
        self.scroll_cursor_visible()

    def action_newline(self) -> None:
        self.insert("\n")
        self.scroll_cursor_visible()

    def action_submit(self) -> None:
        text = self.text.strip()
        if text:
            self.post_message(self.Submitted(text))
        self.clear()
        self._update_layout()


class FeedArea(Markdown):
    """Feed Markdown viewer with syntax highlighting and quick navigation keys."""

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._raw_markdown = ""

    def _enable_fence_wrapping(self) -> None:
        """Walks mounted markdown widgets and enforces word-wrapping on code blocks."""
        for fence in self.query(MarkdownFence):
            if hasattr(fence, "renderable") and isinstance(fence.renderable, Syntax):
                fence.renderable.word_wrap = True
                fence.renderable.padding = 0
                fence.refresh()
            for child in fence.walk_children():
                if hasattr(child, "renderable") and isinstance(child.renderable, Syntax):
                    child.renderable.word_wrap = True
                    child.renderable.padding = 0
                    child.refresh()

    def clear(self) -> None:
        self._raw_markdown = ""
        self.update("")

    def _scroll_to_bottom(self) -> None:
        self._enable_fence_wrapping()
        self.scroll_end(animate=False)

    async def set_messages(self, messages: list[dict]) -> None:
        blocks = []
        for turn in messages:
            label = "You" if turn["role"] == "user" else "Gemini"
            blocks.append(f"### {label}\n\n{turn['text']}")
        self._raw_markdown = "\n\n---\n\n".join(blocks)
        await self.update(self._raw_markdown)
        self.call_after_refresh(self._scroll_to_bottom)

    async def append_message(self, sender: str, text: str) -> None:
        prefix = "\n\n---\n\n" if self._raw_markdown else ""
        header = f"### {sender}\n\n"
        self._raw_markdown += f"{prefix}{header}{text}"
        await self.update(self._raw_markdown)
        self.call_after_refresh(self._scroll_to_bottom)

    def _on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "i", "ctrl+o"):
            event.prevent_default()
            event.stop()
            self.app.query_one("#input", ExpandingInput).focus()
        elif event.key == "ctrl+b":
            event.prevent_default()
            event.stop()
            self.app.action_toggle_history()
        elif event.key == "ctrl+n":
            event.prevent_default()
            event.stop()
            self.app.action_new_chat()
        elif event.key == "ctrl+t":
            event.prevent_default()
            event.stop()
            self.app.action_rename_chat()
        elif event.key == "ctrl+y":
            event.prevent_default()
            event.stop()
            self.app.action_copy_last_response()
        elif event.key in ("ctrl+e", "v"):
            event.prevent_default()
            event.stop()
            self.app.action_open_in_editor()
        # Feed scrolling navigation
        elif event.key in ("k", "up"):
            event.prevent_default()
            event.stop()
            self.scroll_up()
        elif event.key in ("j", "down"):
            event.prevent_default()
            event.stop()
            self.scroll_down()
        elif event.key in ("pageup",):
            event.prevent_default()
            event.stop()
            self.scroll_page_up()
        elif event.key in ("pagedown",):
            event.prevent_default()
            event.stop()
            self.scroll_page_down()
        elif event.key in ("home",):
            event.prevent_default()
            event.stop()
            self.scroll_home()
        elif event.key in ("end",):
            event.prevent_default()
            event.stop()
            self.scroll_end()
        else:
            super()._on_key(event)


class HistoryList(OptionList):
    """OptionList with Vim/Emacs navigation, instant deletion, and renaming."""

    async def _on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "ctrl+b", "ctrl+g", "q"):
            event.prevent_default()
            event.stop()
            self.app.action_toggle_history()
        elif event.key in ("delete", "backspace", "d", "x"):
            event.prevent_default()
            event.stop()
            await self.app.delete_highlighted_chat()
        elif event.key in ("r",):
            event.prevent_default()
            event.stop()
            self.app.rename_highlighted_chat()
        elif event.key in ("k", "ctrl+p"):
            event.prevent_default()
            event.stop()
            self.action_cursor_up()
        elif event.key in ("j", "ctrl+n"):
            event.prevent_default()
            event.stop()
            self.action_cursor_down()
        else:
            super()._on_key(event)


class ChatApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #feed {
        height: 1fr;
        border: solid green;
        overflow-y: auto;
        overflow-x: hidden;
        scrollbar-gutter: stable;
        padding: 0 2 0 1;
        width: 100%;
        max-width: 100%;
    }
    #feed MarkdownBlock,
    #feed MarkdownParagraph,
    #feed MarkdownTable {
        width: 100%;
        max-width: 100%;
        overflow-x: hidden;
    }
    #feed MarkdownFence {
        width: 100%;
        max-width: 100%;
        height: auto;
        overflow-x: hidden;
        margin: 1 0;
    }
    #feed MarkdownFence > * {
        width: 100%;
        max-width: 100%;
    }
    #feed:focus {
        border: double lightgreen;
    }
    #history {
        height: 1fr;
        border: solid yellow;
        display: none;
    }
    #input {
        border: solid dodgerblue;
    }
    #input:focus {
        border: double cyan;
    }
    """

    def copy_to_clipboard(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        super().copy_to_clipboard(text)

    BINDINGS = [
        Binding("ctrl+n", "new_chat", "New Chat", show=True),
        Binding("ctrl+t", "rename_chat", "Rename", show=True),
        Binding("ctrl+b", "toggle_history", "History", show=True),
        Binding("ctrl+y", "copy_last_response", "Yank Last", show=True),
        Binding("ctrl+e", "open_in_editor", "Editor", show=True),
        Binding("escape", "toggle_focus", "Focus Swap", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.client = genai.Client()
        self.current_chat_id: str = ""
        self.current_chat_title: str = ""
        self.history: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield FeedArea(id="feed")
            yield HistoryList(id="history")
            yield ExpandingInput(id="input")
        yield Footer()

    async def on_mount(self) -> None:
        files = self._get_sorted_files()
        if files:
            first_id = files[0].stem
            await self.load_chat(first_id)
        else:
            self._start_new_chat(title="")

        self.query_one("#input").focus()

    # --- Storage & Persistence ---

    def _get_chat_file(self, chat_id: str) -> Path:
        return CHATS_DIR / f"{chat_id}.json"

    def _get_sorted_files(self) -> list[Path]:
        return sorted(
            CHATS_DIR.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

    def refresh_history_list(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        history_widget.clear_options()

        files = self._get_sorted_files()
        for idx, f in enumerate(files):
            try:
                data = json.loads(f.read_text())
                title = data.get("title", f.stem)
                active = " (Active)" if data["id"] == self.current_chat_id else ""
                history_widget.add_option(
                    Option(prompt=f"{idx + 1}. {title}{active}", id=data["id"])
                )
            except Exception:
                continue

    async def load_chat(self, chat_id: str) -> None:
        self.current_chat_id = chat_id
        path = self._get_chat_file(chat_id)
        if path.exists():
            data = json.loads(path.read_text())
            self.history = data.get("messages", [])
            self.current_chat_title = data.get("title", "")
        else:
            self.history = []
            self.current_chat_title = ""

        feed = self.query_one("#feed", FeedArea)
        await feed.set_messages(self.history)

    def save_current_chat(self) -> None:
        if not self.current_chat_id or not self.history:
            return

        path = self._get_chat_file(self.current_chat_id)

        # Retain explicit title if given, otherwise auto-generate from 1st message
        title = self.current_chat_title.strip()
        if not title and self.history:
            title = self.history[0]["text"][:28].replace("\n", " ")
        if not title:
            title = "New Chat"

        self.current_chat_title = title

        data = {
            "id": self.current_chat_id,
            "title": self.current_chat_title,
            "updated_at": time.time(),
            "messages": self.history,
        }
        path.write_text(json.dumps(data, indent=2))

    async def delete_highlighted_chat(self) -> None:
        history_widget = self.query_one("#history", HistoryList)
        if history_widget.highlighted is None or history_widget.option_count == 0:
            return

        option = history_widget.get_option_at_index(history_widget.highlighted)
        target_id = str(option.id)

        target_file = self._get_chat_file(target_id)
        if target_file.exists():
            target_file.unlink()

        files = self._get_sorted_files()
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
        """Rename the chat selected in the History view."""
        history_widget = self.query_one("#history", HistoryList)
        if history_widget.highlighted is None or history_widget.option_count == 0:
            return

        option = history_widget.get_option_at_index(history_widget.highlighted)
        target_id = str(option.id)
        target_file = self._get_chat_file(target_id)
        if not target_file.exists():
            return

        data = json.loads(target_file.read_text())
        current_title = data.get("title", "")

        def on_rename(new_title: str | None) -> None:
            if new_title is not None and new_title.strip():
                data["title"] = new_title.strip()
                data["updated_at"] = time.time()
                target_file.write_text(json.dumps(data, indent=2))
                if target_id == self.current_chat_id:
                    self.current_chat_title = new_title.strip()
                self.refresh_history_list()
                self.notify("Chat renamed.")

        self.push_screen(
            TitlePromptModal(prompt="Edit chat title:", default_title=current_title),
            callback=on_rename,
        )

    # --- Actions & Focus ---

    def action_rename_chat(self) -> None:
        """Edit the title of the current chat."""
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
        input_widget = self.query_one("#input", ExpandingInput)
        if feed.has_focus:
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
        """Opens a modal asking for a title, then creates the session."""
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

        self.current_chat_id = uuid4().hex[:8]
        self.current_chat_title = title
        self.history = []

        feed = self.query_one("#feed", FeedArea)
        feed.clear()
        self.query_one("#input").focus()

    def action_copy_last_response(self) -> None:
        """Yank the last model response directly to the OS clipboard."""
        for turn in reversed(self.history):
            if turn["role"] == "model":
                self.copy_to_clipboard(turn["text"])
                self.notify("Copied last Gemini response to clipboard!")
                return
        self.notify("No response to copy yet.", severity="warning")

    def action_open_in_editor(self) -> None:
        """Suspend Textual and open the current conversation in $EDITOR or $PAGER."""
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

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
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
        payload = [
            {"role": t["role"], "parts": [{"text": t["text"]}]}
            for t in self.history
        ]

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-3.8-flash",
                contents=payload,
            )
            reply = response.text or ""
        except Exception as e:
            self.notify(f"API Error: {e}", severity="error")
            return

        if self.current_chat_id == chat_id_snapshot:
            self.history.append({"role": "model", "text": reply})
            self.save_current_chat()
            await self.append_to_feed("Gemini", reply)


if __name__ == "__main__":
    ChatApp().run()
