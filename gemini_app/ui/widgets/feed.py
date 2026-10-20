"""FeedArea scrolling feed and lockstep navigation view."""

from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import TYPE_CHECKING
from uuid import uuid4

import pyperclip
from rich.cells import cell_len
from textual import events, on, work
import asyncio
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Markdown
from textual.widgets.markdown import MarkdownFence

from gemini_app.config import CENTER_SCREEN_MODE, DEFAULT_WINDOW_CAPACITY, CURRENT_USER
from gemini_app.helpers import cast_ray_from_center
from gemini_app.ui.widgets.turn_card import TurnCard

if TYPE_CHECKING:
    from gemini_app.ui.app import ChatApp

class FeedArea(VerticalScroll):
    can_focus = False
    auto_scroll = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.can_focus = False
        self.active_turn_index: int = 0

        self.fork_ui_active: bool = False
        self._fork_selected_indices: set[int] = set()

        self._all_messages: list[dict] = []
        self._win_start: int = 0
        self._win_end: int = 0

        self._header_map: dict[int, tuple[int, str]] = {}
        self._last_wall_step_time: float = 0.0

    def compose(self) -> ComposeResult:
        yield Vertical(id="turns_container")

    def get_tier_config(self) -> int:
        return DEFAULT_WINDOW_CAPACITY

    def is_locked(self) -> bool:
        return self.app.lock.is_locked

    def scroll_to_widget(self, widget: Widget, *args, **kwargs) -> None:
        pass

    def clear(self) -> None:
        self.fork_ui_active = False
        self.remove_class("fork-ui-active")
        self._fork_selected_indices.clear()
        self._header_map.clear()
        if hasattr(self.app, "hide_status"):
            self.app.hide_status()

        self.set_messages([])

    def _sync_header_map(self) -> None:
        self._header_map.clear()
        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and getattr(child, "virtual_region", None):
                self._header_map[int(child.virtual_region.y)] = (child.turn_index, child.turn_id)

    def _get_center_raycast_target(self, current_y: int | None = None) -> tuple[int, str, int] | None:
        if not self._header_map or not self._all_messages:
            return None

        y = int(self.scroll_y) if current_y is None else int(current_y)
        view_h = self.container_size.height or 24

        if CENTER_SCREEN_MODE:
            center_y = y + (view_h // 2)
            return cast_ray_from_center(center_y, self._header_map)
        else:
            for line_y in sorted(self._header_map.keys()):
                if line_y >= y:
                    t_idx, t_id = self._header_map[line_y]
                    return t_idx, t_id, 0
            closest_line = min(self._header_map.keys(), key=lambda ly: abs(ly - y))
            t_idx, t_id = self._header_map[closest_line]
            return t_idx, t_id, 0

    def _execute_1d_raycast(self, current_y: int | None = None) -> None:
        if self.is_locked() or not self._header_map or not self._all_messages:
            return

        target = self._get_center_raycast_target(current_y)
        if not target:
            return
        t_idx, t_id, delta = target

        prev_target = self.active_turn_index
        self.active_turn_index = t_idx

        if hasattr(self.app, "current_chat_last_index"):
            self.app.current_chat_last_index = t_idx
            if CENTER_SCREEN_MODE:
                sign = f"+{delta}" if delta > 0 else str(delta)
                self.app.current_chat_center_marker = f"{t_id}:{sign}" if delta != 0 else f"{t_id}:0"
            else:
                self.app.current_chat_center_marker = t_id

        if self.active_turn_index != prev_target and not self.is_locked():
            self.highlight_card(self.active_turn_index, scroll=False)

    def request_wall_shift(self, anchor_turn_idx: int, discrete_dock: bool = False, moving_up: bool = False) -> None:
        now = time.monotonic()
        if now - self._last_wall_step_time < 0.15 or self.is_locked():
            return
        self._last_wall_step_time = now

        self.app.lock.acquire("dom_load")
        self.app.show_loader_banner()
        self._sync_runway_to_target(anchor_turn_idx, discrete_dock=discrete_dock, moving_up=moving_up)

    @work(exclusive=True)
    async def _sync_runway_to_target(
        self,
        target_idx: int,
        prev_idx: int | None = None,
        discrete_dock: bool = False,
        moving_up: bool = False,
    ) -> None:
        try:
            total = len(self._all_messages)
            if total <= DEFAULT_WINDOW_CAPACITY:
                if discrete_dock:
                    target_card = self._get_target_widget(target_idx)
                    if target_card:
                        self._scroll_to_turn_widget(target_card, center=False)
                return

            if moving_up:
                preferred_above = 5
                preferred_below = 4
            else:
                preferred_above = 4
                preferred_below = 5

            cards_above = min(target_idx, preferred_above)
            cards_below = min(total - 1 - target_idx, preferred_below)
            rem = DEFAULT_WINDOW_CAPACITY - (1 + cards_above + cards_below)
            if target_idx - cards_above == 0:
                cards_below = min(total - 1 - target_idx, cards_below + rem)
            elif target_idx + cards_below == total - 1:
                cards_above = min(target_idx, cards_above + rem)

            ideal_start = max(0, target_idx - cards_above)
            ideal_end = min(total, target_idx + cards_below + 1)

            if self._win_start == ideal_start and self._win_end == ideal_end:
                if discrete_dock:
                    target_card = self._get_target_widget(target_idx)
                    if target_card:
                        self._scroll_to_turn_widget(target_card, center=False)
                return

            anchor_card = self._get_target_widget(self.active_turn_index)
            signed_delta = 0
            view_h = self.container_size.height or 24
            if anchor_card and anchor_card.virtual_region:
                center_y = int(self.scroll_y) + (view_h // 2)
                signed_delta = center_y - int(anchor_card.virtual_region.y)

            container = self.query_one("#turns_container", Vertical)
            await container.remove_children()

            new_cards = [
                card for idx in range(ideal_start, ideal_end)
                if (card := self._create_turn_widget(idx)) is not None
            ]
            if new_cards:
                await container.mount_all(new_cards)

            self._win_start = ideal_start
            self._win_end = ideal_end

            settle_event = asyncio.Event()

            def _on_runway_settle() -> None:
                try:
                    self._sync_header_map()
                    if discrete_dock:
                        target_card = self._get_target_widget(target_idx)
                        if target_card:
                            self.highlight_card(target_idx, scroll=False)
                            self._scroll_to_turn_widget(target_card, center=False)
                    else:
                        ref_card = self._get_target_widget(self.active_turn_index)
                        if ref_card and ref_card.virtual_region:
                            new_header_y = int(ref_card.virtual_region.y)
                            new_center_y = new_header_y + signed_delta
                            target_scroll_y = max(0, new_center_y - (view_h // 2))
                            max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - view_h))
                            self.scroll_y = min(max_scroll, target_scroll_y)
                        self.highlight_card(self.active_turn_index, scroll=False)
                finally:
                    settle_event.set()

            self.call_after_refresh(_on_runway_settle)
            try:
                await asyncio.wait_for(settle_event.wait(), timeout=0.6)
            except asyncio.TimeoutError:
                self._sync_header_map()

        finally:
            self.app.hide_loader_banner()
            self.app.lock.release("dom_load")

    def _create_turn_widget(self, idx: int) -> TurnCard | None:
        if not (0 <= idx < len(self._all_messages)):
            return None

        turn = self._all_messages[idx]
        turn_id = turn.get("turn_id")
        if not turn_id:
            turn_id = f"turn_{uuid4().hex[:8]}"
            turn["turn_id"] = turn_id

        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and child.turn_index == idx:
                return None

        sender = CURRENT_USER if turn["role"] == "user" else "gemini"
        is_sel = idx in self._fork_selected_indices

        card = TurnCard(
            index=idx,
            sender=sender,
            text=turn["text"],
            turn_id=turn_id,
            is_selected=is_sel,
        )

        if idx == self.active_turn_index:
            card.add_class("card-active")

        return card

    def set_messages(self, messages: list[dict], initial_target_marker: str | int | None = None) -> None:
        self.fork_ui_active = False
        self.remove_class("fork-ui-active")
        self._fork_selected_indices.clear()
        if hasattr(self.app, "hide_status"):
            self.app.hide_status()

        self._run_target_mutation("reset_chat", new_messages=messages, target_marker=initial_target_marker)

    def _get_target_widget(self, idx: int) -> TurnCard | None:
        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and child.turn_index == idx:
                return child
        return None

    def _get_target_widget_by_id(self, turn_id: str) -> TurnCard | None:
        if not turn_id:
            return None
        container = self.query_one("#turns_container", Vertical)
        for child in container.children:
            if isinstance(child, TurnCard) and child.turn_id == turn_id:
                return child
        return None

    def _scroll_to_turn_widget(
        self,
        target_w: TurnCard,
        center: bool = False,
        line_offset: int | None = None,
    ) -> None:
        view_h = self.container_size.height or 24
        header_y = int(target_w.virtual_region.y)
        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - view_h))

        if not center:
            self.scroll_y = max(0, min(max_scroll, header_y))
            return

        offset = line_offset if line_offset is not None else 0
        target_y = (header_y + offset) - (view_h // 2)
        self.scroll_y = max(0, min(max_scroll, target_y))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if self.is_locked():
            event.stop()
            return
        self.app.trigger_nav_indicator("scroll_down")

        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - self.container_size.height))
        if (self.active_turn_index >= (self._win_end - 1) or self.scroll_y >= max_scroll) and self._win_end < len(self._all_messages):
            self.request_wall_shift(self.active_turn_index, discrete_dock=False, moving_up=False)
            return

        self.scroll_down(animate=False)
        self._execute_1d_raycast()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if self.is_locked():
            event.stop()
            return
        self.app.trigger_nav_indicator("scroll_up")

        if (self.active_turn_index <= self._win_start or self.scroll_y <= 0) and self._win_start > 0:
            self.request_wall_shift(self.active_turn_index, discrete_dock=False, moving_up=True)
            return

        self.scroll_up(animate=False)
        self._execute_1d_raycast()

    @work(exclusive=True)
    async def _run_target_mutation(
        self,
        action: str,
        new_messages: list[dict] | None = None,
        target_index: int | None = None,
        target_marker: str | int | None = None,
    ) -> None:
        self.app.lock.acquire("dom_load")
        self.app.show_loader_banner()
        container = self.query_one("#turns_container", Vertical)
        capacity = self.get_tier_config()

        try:
            if action == "reset_chat":
                self._all_messages = list(new_messages or [])
                total = len(self._all_messages)

                await container.remove_children()

                if total == 0:
                    self._win_start = 0
                    self._win_end = 0
                    self.active_turn_index = 0
                    self._header_map.clear()
                    self.scroll_y = 0
                    return

                if target_marker == "end":
                    self._win_start = max(0, total - capacity)
                    self._win_end = total
                    widgets_to_mount = [
                        w for idx in range(self._win_start, self._win_end)
                        if (w := self._create_turn_widget(idx)) is not None
                    ]
                    if widgets_to_mount:
                        await container.mount_all(widgets_to_mount)

                    settle_event = asyncio.Event()

                    def _on_end_reset_settle() -> None:
                        try:
                            self._sync_header_map()
                            self.active_turn_index = total - 1
                            self.highlight_card(total - 1, scroll=False)
                            target_w = self._get_target_widget(total - 1)
                            if target_w:
                                self._scroll_to_turn_widget(target_w, center=False)
                            else:
                                self.scroll_end(animate=False)
                        finally:
                            settle_event.set()

                    self.call_after_refresh(_on_end_reset_settle)
                    try:
                        await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                    except asyncio.TimeoutError:
                        pass
                    return

                req_idx = 0
                line_offset: int | None = None

                if target_marker is not None:
                    marker_str = str(target_marker).strip()
                    if ":" in marker_str:
                        tid, offset_str = marker_str.split(":", 1)
                        if CENTER_SCREEN_MODE:
                            try:
                                line_offset = int(offset_str)
                            except Exception:
                                line_offset = None
                        else:
                            line_offset = None
                    else:
                        tid = marker_str

                    matched_idx = next((i for i, m in enumerate(self._all_messages) if m.get("turn_id") == tid), None)
                    if matched_idx is not None:
                        req_idx = matched_idx
                    else:
                        try:
                            req_idx = max(0, min(total - 1, int(target_marker)))
                        except Exception:
                            req_idx = max(0, total - 1)
                elif target_index is not None and 0 <= target_index < total:
                    req_idx = target_index
                else:
                    req_idx = max(0, total - 1)

                cards_above = min(req_idx, 4)
                cards_below = min(total - 1 - req_idx, 5)
                rem = capacity - (1 + cards_above + cards_below)
                if req_idx - cards_above == 0:
                    cards_below = min(total - 1 - req_idx, cards_below + rem)
                elif req_idx + cards_below == total - 1:
                    cards_above = min(req_idx, cards_above + rem)

                self._win_start = max(0, req_idx - cards_above)
                self._win_end = min(total, req_idx + cards_below + 1)

                widgets_to_mount = [
                    w for idx in range(self._win_start, self._win_end)
                    if (w := self._create_turn_widget(idx)) is not None
                ]
                if widgets_to_mount:
                    await container.mount_all(widgets_to_mount)

                settle_event = asyncio.Event()

                def _on_initial_settle() -> None:
                    try:
                        self._sync_header_map()
                        self.active_turn_index = req_idx
                        target_w = self._get_target_widget(req_idx)
                        if target_w:
                            should_center = CENTER_SCREEN_MODE and (line_offset is not None)
                            self._scroll_to_turn_widget(
                                target_w,
                                center=should_center,
                                line_offset=line_offset,
                            )
                        else:
                            self.scroll_end(animate=False)
                        self.highlight_card(req_idx, scroll=False)
                    finally:
                        settle_event.set()

                self.call_after_refresh(_on_initial_settle)
                try:
                    await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                except asyncio.TimeoutError:
                    pass

            elif action == "jump_home":
                total = len(self._all_messages)
                if total == 0:
                    self.scroll_home(animate=False)
                    return

                self._win_start = 0
                self._win_end = min(capacity, total)

                await container.remove_children()
                home_widgets = [
                    w for idx in range(self._win_start, self._win_end)
                    if (w := self._create_turn_widget(idx)) is not None
                ]
                if home_widgets:
                    await container.mount_all(home_widgets)

                self.active_turn_index = 0
                settle_event = asyncio.Event()

                def _on_home_settle() -> None:
                    try:
                        self._sync_header_map()
                        self.scroll_y = 0
                        self.highlight_card(0, scroll=False)
                    finally:
                        settle_event.set()

                self.call_after_refresh(_on_home_settle)
                try:
                    await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                except asyncio.TimeoutError:
                    pass

            elif action == "jump_end":
                total = len(self._all_messages)
                if total == 0:
                    self.scroll_end(animate=False)
                    return

                self._win_start = max(0, total - capacity)
                self._win_end = total

                await container.remove_children()
                end_widgets = [
                    w for idx in range(self._win_start, self._win_end)
                    if (w := self._create_turn_widget(idx)) is not None
                ]
                if end_widgets:
                    await container.mount_all(end_widgets)

                self.active_turn_index = total - 1
                settle_event = asyncio.Event()

                def _on_end_settle() -> None:
                    try:
                        self._sync_header_map()
                        self.highlight_card(self.active_turn_index, scroll=False)
                        target_w = self._get_target_widget(self.active_turn_index)
                        if target_w:
                            self._scroll_to_turn_widget(target_w, center=False)
                        else:
                            self.scroll_end(animate=False)
                    finally:
                        settle_event.set()

                self.call_after_refresh(_on_end_settle)
                try:
                    await asyncio.wait_for(settle_event.wait(), timeout=0.6)
                except asyncio.TimeoutError:
                    pass

        finally:
            self.app.hide_loader_banner()
            self.app.lock.release("dom_load")

    def step_card(self, delta: int) -> None:
        total = len(self._all_messages)
        if not total or self.is_locked():
            return

        if hasattr(self.app, "trigger_nav_indicator"):
            self.app.trigger_nav_indicator("cards")

        target_idx = max(0, min(total - 1, self.active_turn_index + delta))
        if target_idx == self.active_turn_index:
            return

        if delta > 0 and target_idx >= self._win_end and self._win_end < total:
            self.request_wall_shift(target_idx, discrete_dock=True, moving_up=False)
            return
        elif delta < 0 and target_idx < self._win_start and self._win_start > 0:
            self.request_wall_shift(target_idx, discrete_dock=True, moving_up=True)
            return

        existing_card = self._get_target_widget(target_idx)
        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - self.container_size.height))

        if (delta > 0 and self.scroll_y >= max_scroll) or (delta < 0 and self.scroll_y <= 0):
            self.active_turn_index = target_idx
            if hasattr(self.app, "current_chat_last_index"):
                self.app.current_chat_last_index = target_idx
                self.app.current_chat_center_marker = self._all_messages[target_idx].get("turn_id", "")
            self.highlight_card(target_idx, scroll=False)
            return

        if isinstance(existing_card, TurnCard):
            self.active_turn_index = target_idx
            if hasattr(self.app, "current_chat_last_index"):
                self.app.current_chat_last_index = target_idx
                self.app.current_chat_center_marker = self._all_messages[target_idx].get("turn_id", "")
            self.highlight_card(target_idx, scroll=False)
            self._scroll_to_turn_widget(existing_card, center=False)

    def viewport_page_navigate(self, direction: int) -> None:
        if self.is_locked():
            return

        if direction < 0:
            self.app.trigger_nav_indicator("page_up")
        else:
            self.app.trigger_nav_indicator("page_down")

        page_step = max(self.container_size.height - 3, 5)
        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - self.container_size.height))

        if direction < 0:
            if (self.active_turn_index <= self._win_start or self.scroll_y <= 0) and self._win_start > 0:
                self.request_wall_shift(self.active_turn_index, discrete_dock=False, moving_up=True)
                return
            target_y = max(0, self.scroll_y - page_step)
            self.scroll_to(y=target_y, animate=False)
        else:
            if (self.active_turn_index >= (self._win_end - 1) or self.scroll_y >= max_scroll) and self._win_end < len(self._all_messages):
                self.request_wall_shift(self.active_turn_index, discrete_dock=False, moving_up=False)
                return
            target_y = min(max_scroll, self.scroll_y + page_step)
            self.scroll_to(y=target_y, animate=False)

        self._execute_1d_raycast(target_y)

    def arrow_navigate(self, direction: int) -> None:
        if self.is_locked() or not self._all_messages:
            return

        if direction < 0:
            self.app.trigger_nav_indicator("scroll_up")
        else:
            self.app.trigger_nav_indicator("scroll_down")

        line_step = 2
        max_scroll = getattr(self, "max_scroll_y", max(0, self.virtual_size.height - self.container_size.height))
        total = len(self._all_messages)

        center_target = self._get_center_raycast_target()
        raycast_idx = center_target[0] if center_target else self.active_turn_index

        if direction > 0:
            if (self.active_turn_index >= (self._win_end - 1) or self.scroll_y >= max_scroll) and self._win_end < total:
                self.request_wall_shift(self.active_turn_index, discrete_dock=False, moving_up=False)
                return

            if self.active_turn_index < raycast_idx:
                new_idx = self.active_turn_index + 1
                self.active_turn_index = new_idx
                turn_id = self._all_messages[new_idx].get("turn_id", f"turn_{new_idx}")
                if hasattr(self.app, "current_chat_last_index"):
                    self.app.current_chat_last_index = new_idx
                    self.app.current_chat_center_marker = turn_id
                self.highlight_card(new_idx, scroll=False)
                return

            if self.scroll_y >= max_scroll:
                if self.active_turn_index < total - 1:
                    new_idx = self.active_turn_index + 1
                    self.active_turn_index = new_idx
                    turn_id = self._all_messages[new_idx].get("turn_id", f"turn_{new_idx}")
                    if hasattr(self.app, "current_chat_last_index"):
                        self.app.current_chat_last_index = new_idx
                        self.app.current_chat_center_marker = turn_id
                    self.highlight_card(new_idx, scroll=False)
                return

            target_y = min(max_scroll, self.scroll_y + line_step)
            self.scroll_y = target_y
            self._execute_1d_raycast(target_y)

        else:
            if (self.active_turn_index <= self._win_start or self.scroll_y <= 0) and self._win_start > 0:
                self.request_wall_shift(self.active_turn_index, discrete_dock=False, moving_up=True)
                return

            if self.active_turn_index > raycast_idx:
                new_idx = self.active_turn_index - 1
                self.active_turn_index = new_idx
                turn_id = self._all_messages[new_idx].get("turn_id", f"turn_{new_idx}")
                if hasattr(self.app, "current_chat_last_index"):
                    self.app.current_chat_last_index = new_idx
                    self.app.current_chat_center_marker = turn_id
                self.highlight_card(new_idx, scroll=False)
                return

            if self.scroll_y <= 0:
                if self.active_turn_index > 0:
                    new_idx = self.active_turn_index - 1
                    self.active_turn_index = new_idx
                    turn_id = self._all_messages[new_idx].get("turn_id", f"turn_{new_idx}")
                    if hasattr(self.app, "current_chat_last_index"):
                        self.app.current_chat_last_index = new_idx
                        self.app.current_chat_center_marker = turn_id
                    self.highlight_card(new_idx, scroll=False)
                return

            target_y = max(0, self.scroll_y - line_step)
            self.scroll_y = target_y
            self._execute_1d_raycast(target_y)

    def jump_to_home(self) -> None:
        if self.is_locked():
            return
        self.highlight_card(0, scroll=False)
        self._run_target_mutation("jump_home")
        if hasattr(self.app, "trigger_nav_indicator"):
            self.app.trigger_nav_indicator(
                "edge_home", toast_message="▲ Jumped to top of stream (Home)", duration=1.5
            )

    def jump_to_end(self) -> None:
        if self.is_locked():
            return
        last_idx = max(0, len(self._all_messages) - 1)
        self.highlight_card(last_idx, scroll=False)
        self._run_target_mutation("jump_end")
        if hasattr(self.app, "trigger_nav_indicator"):
            self.app.trigger_nav_indicator(
                "edge_end", toast_message="▼ Jumped to bottom of stream (End)", duration=1.5
            )

    def jump_to_turn(self, turn_idx: int) -> None:
        """Navigates the 10-card slider directly to the specified turn index."""
        total = len(self._all_messages)
        if not (0 <= turn_idx < total) or self.is_locked():
            return
        if self._win_start <= turn_idx < self._win_end:
            card = self._get_target_widget(turn_idx)
            if card:
                self.highlight_card(turn_idx, scroll=False)
                self._scroll_to_turn_widget(card, center=CENTER_SCREEN_MODE)
        else:
            self.request_wall_shift(turn_idx, discrete_dock=True)

    async def append_message(self, sender: str, text: str, jump_to_start: bool = False) -> None:
        safe_text = text if (text and text.strip()) else "✓ Action completed."
        new_idx = len(self._all_messages)
        turn_data = {
            "turn_id": f"turn_{uuid4().hex[:8]}",
            "role": "user" if sender == CURRENT_USER else "model",
            "text": safe_text,
        }
        self._all_messages.append(turn_data)

        container = self.query_one("#turns_container", Vertical)
        capacity = self.get_tier_config()

        if self._win_end == new_idx:
            new_widget = self._create_turn_widget(new_idx)
            if new_widget is not None:
                await container.mount(new_widget)
                self._win_end += 1

                while (self._win_end - self._win_start) > capacity and len(container.children) > 0:
                    top_child = container.children[0]
                    await top_child.remove()
                    self._win_start += 1

                self.active_turn_index = new_idx

                def _on_append_settle() -> None:
                    self._sync_header_map()
                    if jump_to_start:
                        self._scroll_to_turn_widget(new_widget, center=False)
                    else:
                        self.scroll_end(animate=False)

                self.call_after_refresh(_on_append_settle)
        else:
            self.jump_to_end()

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

    def _get_visible_fences(self) -> list[MarkdownFence]:
        feed_reg = self.region
        if not feed_reg or feed_reg.height <= 0:
            return []

        feed_top = feed_reg.y
        feed_bottom = feed_reg.y + feed_reg.height

        visible: list[MarkdownFence] = []
        for fence in self.query(MarkdownFence):
            reg = fence.region
            if not reg or reg.height <= 0:
                continue

            f_top = reg.y
            f_bottom = reg.y + reg.height

            if f_top < feed_bottom and f_bottom > feed_top:
                visible.append(fence)

        return visible

    def navigate_snippet(self, delta: int) -> None:
        if hasattr(self.app, "trigger_nav_indicator"):
            self.app.trigger_nav_indicator("snippets")
        visible = self._get_visible_fences()
        if not visible:
            self.app.notify("No selectable snippet on screen", timeout=1.5)
            return

        total_visible = len(visible)

        curr_idx = -1
        for idx, fence in enumerate(visible):
            if "active-snippet" in fence.classes:
                curr_idx = idx
                break

        if curr_idx == -1:
            target_idx = 0 if delta > 0 else (total_visible - 1)
        else:
            target_idx = (curr_idx + delta) % total_visible

        for fence in self.query(MarkdownFence):
            if "active-snippet" in fence.classes:
                fence.remove_class("active-snippet")
                fence.refresh()

        chosen = visible[target_idx]
        chosen.add_class("active-snippet")
        chosen.refresh()

    def select_snippet_by_widget(self, target_fence: MarkdownFence) -> None:
        for fence in self.query(MarkdownFence):
            if fence is target_fence:
                fence.add_class("active-snippet")
                fence.refresh()
            elif "active-snippet" in fence.classes:
                fence.remove_class("active-snippet")
                fence.refresh()

    def get_active_snippet(self) -> str | None:
        for fence in self.query(MarkdownFence):
            if "active-snippet" in fence.classes:
                return self._extract_code_from_fence(fence)
        return None

    def toggle_fork_ui(self) -> None:
        self.fork_ui_active = not self.fork_ui_active
        if hasattr(self.app, "trigger_nav_indicator"):
            self.app.trigger_nav_indicator("fork")
        if self.fork_ui_active:
            self.add_class("fork-ui-active")
        else:
            self.remove_class("fork-ui-active")
        self._refresh_all_fork_card_checkboxes()

    def highlight_card(self, turn_idx: int, scroll: bool = True) -> None:
        prev_idx = self.active_turn_index
        self.active_turn_index = turn_idx
        container = self.query_one("#turns_container", Vertical)

        for card in container.query(TurnCard):
            if card.turn_index == turn_idx:
                card.add_class("card-active")
                card.update_display()
                if scroll:
                    self._scroll_to_turn_widget(card, center=False)
            else:
                card.remove_class("card-active")
                if card.turn_index == prev_idx:
                    card.update_display()

        if 0 <= turn_idx < len(self._all_messages):
            turn_msg = self._all_messages[turn_idx]
            turn_id = turn_msg.get("turn_id", f"turn_{turn_idx}")
            sender = CURRENT_USER if turn_msg.get("role") == "user" else "gemini"
            if hasattr(self.app, "on_feed_turn_focused"):
                self.app.on_feed_turn_focused(turn_idx, turn_id, sender)

    def toggle_current_card_selection(self) -> None:
        target_card = self._get_target_widget(self.active_turn_index)
        if isinstance(target_card, TurnCard):
            target_card.toggle()

    def toggle_all_fork_checkboxes(self) -> None:
        total = len(self._all_messages)
        if not total:
            return

        all_selected = (len(self._fork_selected_indices) == total)
        if all_selected:
            self._fork_selected_indices.clear()
        else:
            self._fork_selected_indices = set(range(total))

        self._refresh_all_fork_card_checkboxes()
        state_msg = "Selected all turns" if not all_selected else "Deselected all turns"
        self.app.notify(state_msg, timeout=2.0)

    def _refresh_all_fork_card_checkboxes(self) -> None:
        container = self.query_one("#turns_container", Vertical)
        for card in container.query(TurnCard):
            card.update_selected(card.turn_index in self._fork_selected_indices)

    def get_selected_fork_indices(self) -> list[int]:
        return sorted(list(self._fork_selected_indices))

    @on(events.Click)
    def _on_feed_click(self, event: events.Click) -> None:
        if self.is_locked() or self.fork_ui_active:
            return

        curr = event.widget
        while curr and curr is not self:
            if isinstance(curr, MarkdownFence):
                self.select_snippet_by_widget(curr)
                event.stop()
                return
            curr = curr.parent

