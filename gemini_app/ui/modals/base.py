"""Base responsive modal screen automatically applying mobile breakpoints and theme classes."""

from __future__ import annotations

from typing import Generic, TypeVar

from textual import events
from textual.screen import ModalScreen

from gemini_app.config import MOBILE_BREAKPOINT

ModalResultType = TypeVar("ModalResultType")


class ResponsiveModalScreen(ModalScreen[ModalResultType], Generic[ModalResultType]):
    """Base class for all modal screens with automatic palette themes and mobile responsive sizing."""

    def _update_screen_classes(self, width: int | None = None) -> None:
        current_w = width if width is not None else (self.size.width or (self.app.size.width if self.app else 100))
        self.set_class(current_w <= MOBILE_BREAKPOINT, "-mobile")

    def on_mount(self) -> None:
        if hasattr(self.app, "clear_toasts"):
            self.app.clear_toasts()
        if hasattr(self.app, "active_palette_name"):
            self.add_class(f"theme-{getattr(self.app, 'active_palette_name')}")
        self._update_screen_classes()

    def on_resize(self, event: events.Resize) -> None:
        self._update_screen_classes(event.size.width)

    def dismiss(self, result: ModalResultType | None = None) -> None:
        """Safely dismisses the modal, guarding against ScreenStackError if not top screen or stack <= 1."""
        try:
            if not getattr(self, "is_mounted", False):
                return
            app = getattr(self, "app", None)
            if not app:
                return
            screen_stack = getattr(app, "_screen_stack", [])
            if len(screen_stack) <= 1:
                return
            super().dismiss(result)
        except Exception:
            pass
