"""Dynamic MarkdownFence Hook for Accurate Line Numbers in the Feed."""

import re

from rich.console import RenderableType
from rich.syntax import Syntax
from textual.widgets.markdown import MarkdownFence

_orig_markdown_fence_render = MarkdownFence.render

def _enhanced_markdown_fence_render(self: MarkdownFence) -> RenderableType:
    renderable = _orig_markdown_fence_render(self)
    if isinstance(renderable, Syntax):
        renderable.word_wrap = True
        renderable.padding = 0
        renderable.line_numbers = True

        # Scan previous siblings for snippet line metadata: (Lines 123-145)
        start_line = 1
        if self.parent:
            siblings = list(self.parent.children)
            if self in siblings:
                idx = siblings.index(self)
                for s in reversed(siblings[:idx]):
                    s_text = getattr(s, "_text", "") or ""
                    if hasattr(s, "walk_children"):
                        for child in s.walk_children():
                            if hasattr(child, "text"):
                                s_text += " " + str(child.text)
                    m = re.search(r"\(Lines?\s+(\d+)", s_text)
                    if m:
                        start_line = int(m.group(1))
                        break
                    if isinstance(s, MarkdownFence):
                        break

        renderable.start_line = start_line
    return renderable

MarkdownFence.render = _enhanced_markdown_fence_render
