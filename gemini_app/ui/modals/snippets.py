"""Code snippet and file modals: save snippets to disk, file insertion, git tree picker, and emacs frame select."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Callable

from rich.syntax import Syntax
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Input,
    Label,
    OptionList,
    RadioButton,
    RadioSet,
    Static,
    Tree,
)
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from gemini_app.helpers import get_git_files_catalog, write_code_to_disk
from gemini_app.ui.modals.base import ResponsiveModalScreen
from gemini_app.ui.modals.confirm import ConfirmModal
from gemini_app.ui.modals.inputs import DirectoryPathInput, FilePathInput

class WriteSnippetModal(ResponsiveModalScreen[dict | None]):
    DEFAULT_CSS = """
    WriteSnippetModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #save_dialog {
        padding: 1 2;
        width: 72;
        max-width: 90vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
    }
    #save_dialog Label {
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
        color: #ffffff;
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    #save_dialog Input {
        margin-bottom: 1;
        background: #000000;
        color: #ffffff;
    }
    #dialog_buttons {
        width: 100%;
        height: auto;
        align-horizontal: right;
        margin-top: 1;
    }
    #dialog_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    WriteSnippetModal.-mobile #save_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, snippet_content: str, initial_dir: str) -> None:
        super().__init__()
        self.snippet_content = snippet_content
        self.initial_dir = initial_dir

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="save_dialog"):
            yield Label("Working Directory (Tab: auto-complete, 2x Tab: navigate):")
            yield DirectoryPathInput(value=self.initial_dir, id="dir_input")
            yield Label("Filename to write:")
            yield Input(placeholder="e.g. main.py, server.go, script.sh", id="filename_input")
            with Horizontal(id="dialog_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Write to Disk", id="confirm_btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#filename_input", Input).focus()

    @on(Input.Submitted, "#dir_input")
    def on_dir_submitted(self) -> None:
        self.query_one("#filename_input", Input).focus()

    @on(Input.Submitted, "#filename_input")
    def on_filename_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#confirm_btn")
    def on_confirm_pressed(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        working_dir = self.query_one("#dir_input", DirectoryPathInput).value.strip()
        filename = self.query_one("#filename_input", Input).value.strip()

        if not filename:
            self.notify("Filename cannot be blank.", severity="error")
            self.query_one("#filename_input", Input).focus()
            return

        if not working_dir:
            working_dir = os.getcwd()

        self.dismiss({
            "working_dir": working_dir,
            "filename": filename,
            "content": self.snippet_content,
        })

class InsertFileModal(ResponsiveModalScreen[dict | None]):
    DEFAULT_CSS = """
    InsertFileModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #insert_file_dialog {
        padding: 1 2;
        width: 76;
        max-width: 90vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
        color: #ffffff;
    }
    #insert_file_dialog Label {
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
        color: #ffffff;
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    #insert_file_dialog Input {
        margin-bottom: 1;
        background: #000000;
        color: #ffffff;
    }
    #dialog_buttons {
        width: 100%;
        height: auto;
        align-horizontal: right;
        margin-top: 1;
    }
    #dialog_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    InsertFileModal.-mobile #insert_file_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, initial_dir: str) -> None:
        super().__init__()
        self.initial_dir = initial_dir

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="insert_file_dialog"):
            yield Label("Working Directory (Tab: auto-complete, 2x Tab: navigate):")
            yield DirectoryPathInput(value=self.initial_dir, id="dir_input")
            yield Label("File Path (Tab: auto-complete, 2x Tab: navigate):")
            yield FilePathInput(
                placeholder="e.g. src/main.py, config.json, README.md",
                id="file_input",
                base_dir_getter=self._get_working_dir,
            )
            with Horizontal(id="dialog_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Insert File", id="confirm_btn")

    def _get_working_dir(self) -> str:
        try:
            dir_val = self.query_one("#dir_input", DirectoryPathInput).value.strip()
            if dir_val:
                return os.path.expanduser(dir_val)
        except Exception:
            pass
        return os.getcwd()

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#file_input", FilePathInput).focus()

    @on(Input.Submitted, "#dir_input")
    def on_dir_submitted(self) -> None:
        self.query_one("#file_input", FilePathInput).focus()

    @on(Input.Submitted, "#file_input")
    def on_file_submitted(self) -> None:
        self._submit()

    @on(Button.Pressed, "#confirm_btn")
    def on_confirm_pressed(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        working_dir = self.query_one("#dir_input", DirectoryPathInput).value.strip()
        file_path_raw = self.query_one("#file_input", FilePathInput).value.strip()

        if not file_path_raw:
            self.notify("File path cannot be blank.", severity="error")
            self.query_one("#file_input", FilePathInput).focus()
            return

        if not working_dir:
            working_dir = os.getcwd()

        base = Path(os.path.expanduser(working_dir)).resolve()
        raw_path = Path(os.path.expanduser(file_path_raw))
        if raw_path.is_absolute():
            resolved_file = raw_path.resolve()
        else:
            resolved_file = (base / raw_path).resolve()

        if not resolved_file.exists():
            self.notify(f"File not found: {resolved_file}", severity="error")
            self.query_one("#file_input", FilePathInput).focus()
            return

        if not resolved_file.is_file():
            self.notify(f"Target is a directory: {resolved_file}", severity="error")
            self.query_one("#file_input", FilePathInput).focus()
            return

        self.dismiss({
            "working_dir": working_dir,
            "file_path": str(resolved_file),
            "rel_path": file_path_raw,
        })

class GitTreeModal(ResponsiveModalScreen[dict | None]):
    STACK_BREAKPOINT: int = 96

    DEFAULT_CSS = """
    GitTreeModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #git_dialog {
        padding: 1 2;
        width: 104;
        max-width: 95vw;
        height: auto;
        max-height: 94vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
    }
    #git_dialog Label {
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    #git_repo_row {
        height: auto;
        margin-bottom: 1;
    }
    #git_repo_row DirectoryPathInput {
        width: 1fr;
        background: #000000;
        color: #ffffff;
    }
    #git_repo_row Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    #dual_tree_row {
        height: auto;
        min-height: 12;
        margin-bottom: 1;
    }
    .tree_pane {
        width: 1fr;
        height: auto;
    }
    #pane_tracked {
        margin-right: 1;
    }
    .tree_pane Label {
        text-style: bold;
        height: auto;
        margin-bottom: 0;
        color: #ffffff;
        width: 100%;
        text-wrap: wrap;
    }
    .tree_pane Tree {
        height: 13;
        min-height: 5;
        background: #000000;
        color: #ffffff;
    }
    #tree_ignored {
        border: solid #555555;
    }
    #tree_options_row {
        height: auto;
        margin-bottom: 0;
        align-vertical: middle;
    }
    #tree_options_row RadioSet {
        layout: horizontal;
        height: auto;
        background: transparent;
        border: none;
    }
    #tree_options_row RadioButton {
        margin-right: 2;
        color: #ffffff;
    }
    #status_label {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
        width: 100%;
        text-wrap: wrap;
    }
    #git_buttons {
        height: auto;
        width: 100%;
        align-horizontal: right;
    }
    #git_buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    GitTreeModal.-stacked #dual_tree_row {
        layout: vertical;
        height: auto;
    }
    GitTreeModal.-stacked .tree_pane {
        width: 100%;
        height: auto;
    }
    GitTreeModal.-stacked #pane_tracked {
        margin-right: 0;
        margin-bottom: 1;
    }
    GitTreeModal.-stacked .tree_pane Tree {
        height: 9;
    }
    GitTreeModal.-mobile #git_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    GitTreeModal.-mobile .tree_pane Tree {
        height: 8;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, initial_dir: str) -> None:
        super().__init__()
        self.repo_dir = initial_dir
        self.tracked_files: list[str] = []
        self.ignored_files: list[str] = []
        self.selected_files: set[str] = set()

    def _update_screen_classes(self, width: int | None = None) -> None:
        super()._update_screen_classes(width)
        current_w = width if width is not None else (self.size.width or (self.app.size.width if self.app else 100))
        self.set_class(current_w <= self.STACK_BREAKPOINT, "-stacked")

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="git_dialog"):
            yield Label("Git Repository Path (Tab: auto-complete, 2x Tab: navigate):")
            with Horizontal(id="git_repo_row"):
                yield DirectoryPathInput(value=self.repo_dir, id="git_dir_input")
                yield Button("Scan Tree", id="scan_btn")

            with Horizontal(id="dual_tree_row"):
                with Vertical(classes="tree_pane", id="pane_tracked"):
                    yield Label("Tracked Files:", id="lbl_tracked")
                    yield Tree("Tracked Files", id="tree_tracked")
                with Vertical(classes="tree_pane", id="pane_ignored"):
                    yield Label(".gitignore Ignored Files:", id="lbl_ignored")
                    yield Tree("Ignored Files", id="tree_ignored")

            yield Label("Tree Structure in Prompt:")
            with Horizontal(id="tree_options_row"):
                with RadioSet(id="tree_mode_radios"):
                    yield RadioButton("Full Tree", value=True, id="radio_full")
                    yield RadioButton("Selected Files Only", id="radio_selected")
                    yield RadioButton("None", id="radio_none")

            yield Label("0 files selected. [Space]/Click to toggle file/folder, [a] all in tree", id="status_label")

            with Horizontal(id="git_buttons"):
                yield Button("Cancel", id="cancel_btn")
                yield Button("Insert Selected & Tree", id="insert_btn")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#tree_tracked", Tree).show_root = False
        self.query_one("#tree_ignored", Tree).show_root = False
        self._scan_and_populate()
        self.query_one("#tree_tracked").focus()

    def _scan_and_populate(self) -> None:
        raw_dir = self.query_one("#git_dir_input", DirectoryPathInput).value.strip()
        expanded = os.path.expanduser(raw_dir) if raw_dir else os.getcwd()
        self.repo_dir = expanded

        if hasattr(self.app, "set_working_dir"):
            self.app.set_working_dir(self.repo_dir)

        tree_tracked = self.query_one("#tree_tracked", Tree)
        tree_ignored = self.query_one("#tree_ignored", Tree)
        tree_tracked.clear()
        tree_ignored.clear()
        self.selected_files.clear()

        try:
            catalog = get_git_files_catalog(self.repo_dir)
            self.tracked_files = catalog["tracked"]
            self.ignored_files = catalog["ignored"]
        except Exception as e:
            self.notify(f"Git Scan Error: {e}", severity="error")
            self.tracked_files = []
            self.ignored_files = []
            self._update_status()
            return

        def populate_tree(tree_widget: Tree, file_list: list[str]) -> None:
            nodes: dict[str, TreeNode] = {"": tree_widget.root}
            for file_path in file_list:
                parts = Path(file_path).parts
                current_path = ""
                for i, part in enumerate(parts):
                    parent_path = current_path
                    current_path = str(Path(current_path) / part) if current_path else part
                    is_file = i == len(parts) - 1

                    if current_path not in nodes:
                        parent_node = nodes[parent_path]
                        if is_file:
                            label = f"[ ] {part}"
                            node = parent_node.add_leaf(label, data={"path": file_path, "name": part, "is_file": True})
                        else:
                            node = parent_node.add(f"[ ] 📁 {part}", data={"path": current_path, "name": part, "is_file": False})
                            node.expand()
                        nodes[current_path] = node
            tree_widget.root.expand()

        populate_tree(tree_tracked, self.tracked_files)
        populate_tree(tree_ignored, self.ignored_files)

        self.query_one("#lbl_tracked", Label).update(f"Tracked Files ({len(self.tracked_files)}):")
        self.query_one("#lbl_ignored", Label).update(f".gitignore Ignored Files ({len(self.ignored_files)}):")
        self._update_status()

    def _get_tree_of_node(self, node: TreeNode) -> Tree | None:
        curr = node
        while curr.parent:
            curr = curr.parent
        for t in (self.query_one("#tree_tracked", Tree), self.query_one("#tree_ignored", Tree)):
            if t.root is curr:
                return t
        return None

    def _refresh_tree_labels(self, root_node: TreeNode) -> tuple[int, int]:
        data = root_node.data or {}
        if data.get("is_file"):
            is_sel = data["path"] in self.selected_files
            part = data.get("name", Path(data["path"]).name)
            box = "✓" if is_sel else " "
            root_node.set_label(f"[{box}] {part}")
            return (1 if is_sel else 0, 1)

        sel_total = 0
        file_total = 0
        for child in root_node.children:
            s, f = self._refresh_tree_labels(child)
            sel_total += s
            file_total += f

        if root_node.parent is not None:
            part = data.get("name", "")
            if file_total > 0 and sel_total == file_total:
                root_node.set_label(f"[✓] 📁 {part}")
            elif sel_total > 0:
                root_node.set_label(f"[-] 📁 {part}")
            else:
                root_node.set_label(f"[ ] 📁 {part}")

        return (sel_total, file_total)

    def _update_status(self) -> None:
        total = len(self.tracked_files) + len(self.ignored_files)
        count = len(self.selected_files)
        lbl = self.query_one("#status_label", Label)
        lbl.update(f"{count} file(s) selected out of {total}. [Space]/Click to toggle file/folder, [a] all in tree")

    def _toggle_node(self, node: TreeNode) -> None:
        data = node.data or {}

        if data.get("is_file"):
            file_path = data["path"]
            if file_path in self.selected_files:
                self.selected_files.remove(file_path)
            else:
                self.selected_files.add(file_path)
        else:
            descendant_files: list[str] = []

            def collect_files(n: TreeNode) -> None:
                if n.data and n.data.get("is_file"):
                    descendant_files.append(n.data["path"])
                for c in n.children:
                    collect_files(c)

            collect_files(node)
            if not descendant_files:
                return

            all_selected = all(p in self.selected_files for p in descendant_files)
            for p in descendant_files:
                if all_selected:
                    self.selected_files.discard(p)
                else:
                    self.selected_files.add(p)

        tree = self._get_tree_of_node(node)
        if tree:
            self._refresh_tree_labels(tree.root)
        self._update_status()

    def _toggle_all_in_tree(self, tree_widget: Tree) -> None:
        contained_files: list[str] = []

        def walk(n: TreeNode):
            if n.data and n.data.get("is_file"):
                contained_files.append(n.data["path"])
            for c in n.children:
                walk(c)

        walk(tree_widget.root)
        if not contained_files:
            return

        all_selected = all(p in self.selected_files for p in contained_files)
        for file_path in contained_files:
            if all_selected:
                self.selected_files.discard(file_path)
            else:
                self.selected_files.add(file_path)

        self._refresh_tree_labels(tree_widget.root)
        self._update_status()

    @on(Tree.NodeSelected)
    def on_tree_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        self._toggle_node(event.node)

    @on(Tree.NodeCollapsed)
    def on_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        event.prevent_default()
        event.stop()
        event.node.expand()

    @on(Button.Pressed, "#scan_btn")
    def on_scan_pressed(self) -> None:
        self._scan_and_populate()

    @on(Input.Submitted, "#git_dir_input")
    def on_dir_submitted(self) -> None:
        self._scan_and_populate()

    @on(Button.Pressed, "#insert_btn")
    def on_confirm_pressed(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    def _on_key(self, event: events.Key) -> None:
        focused = self.focused
        if isinstance(focused, Tree):
            if event.key == "space":
                event.prevent_default()
                event.stop()
                if focused.cursor_node:
                    self._toggle_node(focused.cursor_node)
                return
            elif event.key == "a":
                event.prevent_default()
                event.stop()
                self._toggle_all_in_tree(focused)
                return

        super()._on_key(event)

    def _submit(self) -> None:
        radios = self.query_one("#tree_mode_radios", RadioSet)

        tree_mode = "full"
        if radios.pressed_button:
            if radios.pressed_button.id == "radio_selected":
                tree_mode = "selected"
            elif radios.pressed_button.id == "radio_none":
                tree_mode = "none"

        self.dismiss({
            "repo_dir": self.repo_dir,
            "selected_files": sorted(list(self.selected_files)),
            "tracked_files": self.tracked_files,
            "ignored_files": self.ignored_files,
            "tree_mode": tree_mode,
        })


class FrameSelectModal(ResponsiveModalScreen[dict | None]):
    DEFAULT_CSS = """
    FrameSelectModal {
        align: center middle;
        layer: overlay;
        background: rgba(0, 0, 0, 0.85);
    }
    #frame_dialog {
        padding: 1 2;
        width: 70;
        max-width: 90vw;
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #000000;
    }
    #frame_dialog Label {
        margin-bottom: 1;
        text-style: bold;
        color: #ffffff;
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    #frame_options {
        height: auto;
        max-height: 14;
        margin-bottom: 1;
        background: #000000;
        color: #ffffff;
    }
    #dialog-buttons {
        width: 100%;
        height: auto;
        align-horizontal: right;
    }
    #dialog-buttons Button {
        margin-left: 1;
        background: #000000;
        color: #ffffff;
        text-style: none;
    }
    FrameSelectModal.-mobile #frame_dialog {
        width: 100vw;
        height: 100vh;
        max-width: 100vw;
        max-height: 100vh;
        border: none;
        padding: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+g", "cancel", "Cancel"),
    ]

    def __init__(self, frame_data: list[dict], default_file: str = "") -> None:
        super().__init__()
        self.frame_data = frame_data
        self.default_file = default_file
        self.flat_targets: list[dict] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="frame_dialog"):
            yield Label("Multiple Emacs frames detected.\nSelect destination window:")
            yield OptionList(id="frame_options")
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        super().on_mount()
        opt_list = self.query_one("#frame_options", OptionList)
        self.flat_targets = []
        default_index = 0

        for f in self.frame_data:
            frame_num = f.get("frame_num", 1)
            windows = f.get("windows", [])
            summary_files = ", ".join(w["file_name"] for w in windows)

            if len(windows) > 1:
                header_text = f"Frame {frame_num} (windows: {summary_files})"
                opt_list.add_option(Option(prompt=f"▼ {header_text}", disabled=True))

                for w in windows:
                    self.flat_targets.append(w)
                    idx = len(self.flat_targets) - 1
                    opt_list.add_option(
                        Option(prompt=f"   └─ {w['file_name']}  ({w['buf_name']})", id=str(idx))
                    )
                    if self.default_file and w["file_name"] == self.default_file:
                        default_index = idx
            elif len(windows) == 1:
                w = windows[0]
                self.flat_targets.append(w)
                idx = len(self.flat_targets) - 1
                opt_list.add_option(
                    Option(prompt=f"Frame {frame_num}: {w['file_name']}  ({w['buf_name']})", id=str(idx))
                )
                if self.default_file and w["file_name"] == self.default_file:
                    default_index = idx

        if self.flat_targets:
            opt_list.highlighted = default_index
        opt_list.focus()

    @on(OptionList.OptionSelected, "#frame_options")
    def on_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option_id is not None:
            idx = int(event.option_id)
            self.dismiss(self.flat_targets[idx])

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

