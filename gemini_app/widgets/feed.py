"""Feed Markdown viewer with snippet navigation and selection."""

from rich.syntax import Syntax
from textual import events, on
from textual.widgets import Markdown
from textual.widgets.markdown import MarkdownFence


class FeedArea(Markdown):
    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._raw_markdown = ""
        self.selected_snippet_index: int = -1

    def clear(self) -> None:
        self._raw_markdown = ""
        self.selected_snippet_index = -1
        self.update("")

    def _scroll_to_bottom(self) -> None:
        self.scroll_end(animate=False)

    async def set_messages(self, messages: list[dict]) -> None:
        blocks = []
        for turn in messages:
            label = "You" if turn["role"] == "user" else "Gemini"
            blocks.append(f"### {label}\n\n{turn['text']}")
        self._raw_markdown = "\n\n---\n\n".join(blocks)
        self.selected_snippet_index = -1
        await self.update(self._raw_markdown)
        self.call_after_refresh(self._scroll_to_bottom)

    async def append_message(self, sender: str, text: str) -> None:
        prefix = "\n\n---\n\n" if self._raw_markdown else ""
        header = f"### {sender}\n\n"
        self._raw_markdown += f"{prefix}{header}{text}"
        await self.update(self._raw_markdown)
        self.call_after_refresh(self._scroll_to_bottom)

    def _get_fences(self) -> list[MarkdownFence]:
        return list(self.query(MarkdownFence))

    def _extract_code_from_fence(self, fence: MarkdownFence) -> str:
        if hasattr(fence, "text") and fence.text:
            return fence.text
        if hasattr(fence, "code") and fence.code:
            return fence.code
        if hasattr(fence, "renderable") and isinstance(fence.renderable, Syntax):
            return fence.renderable.code
        for child in fence.walk_children():
            if hasattr(child, "renderable") and isinstance(child.renderable, Syntax):
                return child.renderable.code
        return str(getattr(fence, "renderable", ""))

    def select_snippet(self, index: int, scroll: bool = True) -> None:
        fences = self._get_fences()
        if not (0 <= index < len(fences)):
            return

        self.selected_snippet_index = index

        for idx, f in enumerate(fences):
            if idx == self.selected_snippet_index:
                f.add_class("active-snippet")
                if scroll:
                    f.scroll_visible(animate=True)
                f.refresh()
            else:
                f.remove_class("active-snippet")
                f.refresh()

    def navigate_snippet(self, delta: int) -> None:
        fences = self._get_fences()
        if not fences:
            return

        total = len(fences)
        if self.selected_snippet_index == -1:
            new_idx = 0 if delta > 0 else total - 1
        else:
            new_idx = (self.selected_snippet_index + delta) % total

        self.select_snippet(new_idx, scroll=True)

    def get_active_snippet(self) -> str | None:
        fences = self._get_fences()
        if 0 <= self.selected_snippet_index < len(fences):
            return self._extract_code_from_fence(fences[self.selected_snippet_index])
        return None

    @on(events.Click)
    def _on_feed_click(self, event: events.Click) -> None:
        curr = event.widget
        while curr and curr is not self:
            if isinstance(curr, MarkdownFence):
                fences = self._get_fences()
                if curr in fences:
                    self.select_snippet(fences.index(curr), scroll=False)
                    self.focus()
                    event.stop()
                    return
            curr = curr.parent

    def _on_key(self, event: events.Key) -> None:
        if self.app.handle_c_c_prefix(event):
            return

        if event.key == "ctrl+c":
            event.prevent_default(); event.stop()
            self.app.set_c_c_prefix()
            return

        if event.key in ("escape", "i", "ctrl+o"):
            event.prevent_default(); event.stop()
            from gemini_app.widgets.input_area import ExpandingInput
            self.app.query_one("#input", ExpandingInput).focus()
            return

        elif event.key in ("alt+n", "alt+down"):
            event.prevent_default(); event.stop()
            self.navigate_snippet(1)
        elif event.key in ("alt+p", "alt+up"):
            event.prevent_default(); event.stop()
            self.navigate_snippet(-1)

        elif event.key in ("down", "j"):
            event.prevent_default(); event.stop()
            self.scroll_down()
        elif event.key in ("up", "k"):
            event.prevent_default(); event.stop()
            self.scroll_up()
        elif event.key in ("pageup",):
            event.prevent_default(); event.stop()
            self.scroll_page_up()
        elif event.key in ("pagedown",):
            event.prevent_default(); event.stop()
            self.scroll_page_down()
        elif event.key in ("home",):
            event.prevent_default(); event.stop()
            self.scroll_home()
        elif event.key in ("end",):
            event.prevent_default(); event.stop()
            self.scroll_end()
        else:
            super()._on_key(event)
