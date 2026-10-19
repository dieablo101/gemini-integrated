"""Tool registry packaging callable functions for the Google GenAI SDK."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from gemini_app.storage.memory_index import MemoryIndex
from gemini_app.tools.execution import execute_shell as _execute_shell
from gemini_app.tools.mind_tools import (
    expand_mind as _expand_mind,
    recall_memory as _recall_memory,
)
from gemini_app.tools.snapshots import review_held_snapshots as _review_held_snapshots
from gemini_app.tools.workspace import (
    apply_patch as _apply_patch,
    scan_workspace_tree as _scan_workspace_tree,
    search_codebase as _search_codebase,
    write_file as _write_file,
)


class ToolRegistry:
    """Binds environment context to tool functions and creates SDK-ready callbacks."""

    def __init__(
        self,
        working_dir: Union[str, Path],
        history: List[Dict[str, Any]],
        phase_callback: Optional[Callable[..., None]] = None,
        reboot_callback: Optional[Callable[..., Dict[str, Any]]] = None,
        snapshot_callback: Optional[Callable[[str], Dict[str, Any]]] = None,
        memory_index: Optional[MemoryIndex] = None,
        notes_callback: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> None:
        self.working_dir = working_dir
        self.history = history
        self.phase_callback = phase_callback
        self.reboot_callback = reboot_callback
        self.snapshot_callback = snapshot_callback
        self.memory_index = memory_index or MemoryIndex()
        self.notes_callback = notes_callback

    def _notify_phase(self, phase: str, details: str = "") -> None:
        if self.phase_callback:
            try:
                self.phase_callback(phase, details)
            except TypeError:
                self.phase_callback(phase)

    def get_tool_callables(self) -> Tuple[List[Callable], Dict[str, Callable]]:
        """Returns SDK-compatible function callables and a lookup dictionary."""

        def scan_workspace_tree(include_ignored: bool = True, max_depth: Optional[int] = None) -> str:
            """Scans the working directory git tree, returning tracked and .gitignore files."""
            self._notify_phase("scanning", "scanning workspace tree")
            return _scan_workspace_tree(self.working_dir, include_ignored=include_ignored, max_depth=max_depth)

        def expand_mind(
            turn_numbers: List[int] = [],
            file_paths: List[str] = [],
            turn_ids: List[str] = [],
        ) -> Dict[str, Any]:
            """Fetches up to 50 items (historical chat turns and local files/slices/outlines)."""
            if file_paths:
                display_f = file_paths[0] if len(file_paths) == 1 else f"{file_paths[0]} (+{len(file_paths)-1})"
                self._notify_phase("reading", f"reading file ({display_f})")
            elif turn_numbers or turn_ids:
                turns_label = f"{len(turn_numbers or turn_ids)} turn(s)"
                self._notify_phase("expanding", f"expanding mind (recalling {turns_label})")
            else:
                self._notify_phase("probing", "expanding mind (seeking context & tools)")
            return _expand_mind(
                self.working_dir,
                self.history,
                turn_numbers=turn_numbers,
                file_paths=file_paths,
                turn_ids=turn_ids,
                memory_index=self.memory_index,
            )

        def recall_memory(query: str, max_results: int = 10) -> Dict[str, Any]:
            """Fast indexed retrieval across entire conversational history, archived projects, and past discussions."""
            self._notify_phase("recalling", f"recalling indexed memory ({query})")
            return _recall_memory(
                query=query,
                max_results=max_results,
                memory_index=self.memory_index,
            )

        def write_file(path: str, content: str) -> Dict[str, Any]:
            """Writes or overwrites a file on disk relative to the working directory."""
            self._notify_phase("writing", f"writing code in file ({path})")
            return _write_file(self.working_dir, path=path, content=content)

        def apply_patch(path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
            """Applies a surgical find-and-replace patch to a file. The search_block must appear exactly once."""
            self._notify_phase("patching", f"patching code in file ({path})")
            return _apply_patch(
                self.working_dir,
                path=path,
                search_block=search_block,
                replace_block=replace_block,
            )

        def search_codebase(query: str, path_pattern: str = "*", max_matches: int = 50) -> Dict[str, Any]:
            """Searches workspace files for a text pattern or regex query, returning matching lines."""
            self._notify_phase("searching", f"searching codebase ({query})")
            return _search_codebase(
                self.working_dir,
                query=query,
                path_pattern=path_pattern,
                max_matches=max_matches,
            )

        def execute_shell(command: str, timeout_seconds: int = 60) -> Dict[str, Any]:
            """Executes a shell command inside the working directory and returns stdout, stderr, and exit_code."""
            cmd_snippet = command.strip().replace("\n", " ")
            if len(cmd_snippet) > 35:
                cmd_snippet = cmd_snippet[:32] + "..."
            self._notify_phase("executing", f"executing terminal line command ({cmd_snippet})")
            return _execute_shell(self.working_dir, command=command, timeout_seconds=timeout_seconds)

        def reboot_console(delay_seconds: float = 1.5, status_report: str = "") -> Dict[str, Any]:
            """Reboots/restarts the bilateral terminal console in place, preserving chat and terminal session."""
            self._notify_phase("rebooting", "preparing console reboot")
            if self.reboot_callback:
                try:
                    return self.reboot_callback(delay_seconds, status_report)
                except TypeError:
                    return self.reboot_callback(delay_seconds)
            return {"status": "error", "message": "Reboot capability not available in this context."}

        def take_snapshot(label: str = "") -> Dict[str, Any]:
            """Captures a UI snapshot of the console application on Gemini's end, indexed and held."""
            self._notify_phase("snapshotting", f"capturing UI snapshot ({label or 'live'})")
            if self.snapshot_callback:
                return self.snapshot_callback(label)
            return {"status": "error", "message": "Snapshot capture callback unavailable in this context."}

        def review_snapshots(snapshot_ids: List[str] = [], only_held: bool = True, count: int = 5) -> Dict[str, Any]:
            """Reviews UI snapshots taken by the user or Gemini, returning reconstructed screen text and metadata."""
            self._notify_phase("reviewing", "reviewing held UI snapshots")
            return _review_held_snapshots(
                snapshot_ids=snapshot_ids,
                only_held=only_held,
                count=count,
            )

        def manage_notes(
            action: str = "get",
            topic: str = "",
            content: str = "",
            status: str = "active",
            turn_id: str = "",
            mode: str = "gemini",
        ) -> Dict[str, Any]:
            """Reads or updates Gemini-managed topical notes, records topic associations, and manages revisit queues."""
            self._notify_phase("notes", f"syncing notes ({action})")
            if self.notes_callback:
                return self.notes_callback(
                    action=action,
                    topic=topic,
                    content=content,
                    status=status,
                    turn_id=turn_id,
                    mode=mode,
                )
            return {"status": "error", "message": "Notes management callback unavailable in this context."}

        tools_list = [
            scan_workspace_tree,
            expand_mind,
            recall_memory,
            write_file,
            apply_patch,
            search_codebase,
            execute_shell,
            reboot_console,
            take_snapshot,
            review_snapshots,
            manage_notes,
        ]

        tools_dict = {
            "scan_workspace_tree": scan_workspace_tree,
            "expand_mind": expand_mind,
            "recall_memory": recall_memory,
            "write_file": write_file,
            "apply_patch": apply_patch,
            "search_codebase": search_codebase,
            "execute_shell": execute_shell,
            "reboot_console": reboot_console,
            "take_snapshot": take_snapshot,
            "review_snapshots": review_snapshots,
            "manage_notes": manage_notes,
        }

        return tools_list, tools_dict
