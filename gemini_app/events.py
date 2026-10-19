"""Textual custom messages, events, and application-level lock controllers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.message import Message

if TYPE_CHECKING:
    from textual.app import App


class RemoteInsert(Message):
    """Fired to insert text or code snippets into the input area or note editor."""

    def __init__(
        self,
        text: str,
        lang: str = "",
        file: str = "",
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> None:
        super().__init__()
        self.text = text
        self.lang = lang
        self.file = file
        self.start_line = start_line
        self.end_line = end_line


class RequestPhaseUpdate(Message):
    """Fired when Gemini generation changes phase (e.g. connecting, waiting, probing, writing, reading, executing)."""

    def __init__(self, phase: str, details: str = "") -> None:
        super().__init__()
        self.phase = phase
        self.details = details


class RequestFinished(Message):
    """Fired when Gemini generation successfully finishes."""

    def __init__(self, full_text: str, elapsed: float, words: int) -> None:
        super().__init__()
        self.full_text = full_text
        self.elapsed = elapsed
        self.words = words


class RequestFailed(Message):
    """Fired when Gemini generation encounters an error."""

    def __init__(self, error_message: str) -> None:
        super().__init__()
        self.error_message = error_message


class MindMapRecalibrated(Message):
    """Fired when a model response or user steering recalibrates the cognitive mind map."""

    def __init__(self, gemini_state: str, user_state: str, tree_content: str, tree_state: list) -> None:
        super().__init__()
        self.gemini_state = gemini_state
        self.user_state = user_state
        self.tree_content = tree_content
        self.tree_state = tree_state


class AppLockEngaged(Message):
    """Fired when a modal or lock reason locks navigation and normal keybindings."""

    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason


class AppLockReleased(Message):
    """Fired when a modal or lock reason is cleared."""

    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason


class AppLockController:
    """Manages active lock reasons preventing conflicting UI input."""

    def __init__(self, app: App) -> None:
        self.app = app
        self._active_reasons: set[str] = set()

    @property
    def is_locked(self) -> bool:
        return len(self._active_reasons) > 0

    def has_reason(self, reason: str) -> bool:
        return reason in self._active_reasons

    def acquire(self, reason: str) -> None:
        was_locked = self.is_locked
        self._active_reasons.add(reason)
        if not was_locked:
            self.app.post_message(AppLockEngaged(reason))

    def release(self, reason: str) -> None:
        if reason in self._active_reasons:
            self._active_reasons.remove(reason)
            if not self.is_locked:
                self.app.post_message(AppLockReleased(reason))
