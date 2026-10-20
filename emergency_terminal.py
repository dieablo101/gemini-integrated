#!/usr/bin/env python3
"""
emergency_terminal.py - Standalone Monolithic CLI Recovery Terminal.

Completely decoupled from the Textual UI layer and application event loop.
Zero external UI dependencies — uses only Python standard library + google.genai.
Provides out-of-band triage, diagnostics, repair, and direct communication
with Gemini when the primary bilateral console is broken, freezing, or offline.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
import re
import readline
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Autonomous Environment Trampoline
# -----------------------------------------------------------------------------

def _is_constrained_platform() -> bool:
    """Detects constrained 32-bit/iSH/musl platform where Rust pip builds fail."""
    if sys.maxsize <= 2**32:
        return True
    if os.path.exists("/proc/ish"):
        return True
    try:
        import platform
        u = platform.uname()
        if "ish" in u.release.lower() or "ish" in u.version.lower():
            return True
    except Exception:
        pass
    if Path("/mnt/ipad").exists():
        return True
    return False


def _ensure_runtime_environment() -> None:
    """Ensures google.genai is importable.
    
    If the current Python interpreter lacks google.genai (e.g. system python
    invoked from an un-activated shell), searches candidate virtual environments
    and re-executes itself transparently. If none exist, auto-bootstraps
    a minimal isolated environment in ~/.gemini/venv.
    """
    try:
        import google.genai
        return  # Current interpreter is fully equipped!
    except ImportError:
        pass

    # If running on a constrained platform (e.g. iPad iSH), do not attempt source pip builds
    if _is_constrained_platform():
        return

    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / ".venv" / "bin" / "python3",
        script_dir / "venv" / "bin" / "python3",
        Path.home() / ".gemini" / "venv" / "bin" / "python3",
        Path("/opt/gemini/.venv/bin/python3"),
    ]

    for py in candidates:
        if py.exists() and os.access(str(py), os.X_OK):
            try:
                res = subprocess.run(
                    [str(py), "-c", "import google.genai"],
                    capture_output=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    os.execv(str(py), [str(py), str(Path(__file__).resolve())] + sys.argv[1:])
            except Exception:
                continue

    # If no virtualenv has google.genai, attempt fallback bootstrap into ~/.gemini/venv
    gemini_venv = Path.home() / ".gemini" / "venv"
    gemini_python = gemini_venv / "bin" / "python3"
    try:
        sys.stdout.write("⚡ Emergency Terminal: Bootstrapping google-genai dependency in ~/.gemini/venv...\n")
        import venv
        gemini_venv.parent.mkdir(parents=True, exist_ok=True)
        venv.create(str(gemini_venv), with_pip=True, clear=False)
        subprocess.run(
            [str(gemini_python), "-m", "pip", "install", "-q", "google-genai>=1.0.0"],
            check=True,
            timeout=120,
        )
        os.execv(str(gemini_python), [str(gemini_python), str(Path(__file__).resolve())] + sys.argv[1:])
    except Exception:
        pass


# Run trampoline check before any external package imports
_ensure_runtime_environment()

# Try to import google.genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None  # type: ignore
    types = None  # type: ignore

# -----------------------------------------------------------------------------
# Configuration & ANSI Theme (Purple & Violet Aesthetic)
# -----------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-3.8-flash"

# Truecolor ANSI sequences
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"

# Purple / Violet palette
CLR_PRIMARY = "\033[38;2;168;85;247m"     # #a855f7 - Bright Purple
CLR_LAVENDER = "\033[38;2;216;180;254m"   # #d8b4fe - Soft Lavender
CLR_DARK_PURPLE = "\033[38;2;126;34;206m" # #7e22ce - Deep Purple
CLR_MUTED = "\033[38;2;140;130;160m"      # Muted slate/purple
CLR_WHITE = "\033[38;2;245;245;250m"      # Bright text
CLR_GREEN = "\033[38;2;74;222;128m"       # #4ade80 - Emerald
CLR_AMBER = "\033[38;2;251;191;36m"       # #fbbf24 - Warning Amber
CLR_RED = "\033[38;2;248;113;113m"        # #f87171 - Error Red
CLR_BG_PURPLE = "\033[48;2;88;28;135m"    # Background deep violet

# GNU Readline non-printing escape wrappers (prevents cursor jumping & walking over prompts)
RL_START = "\001"
RL_END = "\002"

def rl_esc(ansi_seq: str) -> str:
    """Wraps ANSI escape sequences with readline ignore markers so prompt length is exact."""
    return f"{RL_START}{ansi_seq}{RL_END}"


# -----------------------------------------------------------------------------
# Live Terminal Status & Spinner Engine
# -----------------------------------------------------------------------------

class LiveStatus:
    """Threaded terminal spinner with elapsed timer and violet animated pulses.
    
    Guarantees the user knows Gemini and commands are actively processing,
    never appearing frozen or unresponsive.
    """

    def __init__(self, message: str = "Working..."):
        self.message = message
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._start_time = 0.0

    def start(self, message: Optional[str] = None) -> "LiveStatus":
        if self._thread and self._thread.is_alive():
            if message:
                self.message = message
            return self
        if message:
            self.message = message
        self._stop_event.clear()
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def update(self, message: str) -> None:
        self.message = message

    def stop(self, final_text: str = "") -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        self._thread = None
        # Cleanly erase the spinner line
        sys.stdout.write("\r\033[K")
        if final_text:
            sys.stdout.write(final_text + "\n")
        sys.stdout.flush()

    def _spin(self) -> None:
        idx = 0
        while not self._stop_event.is_set():
            frame = self._frames[idx % len(self._frames)]
            elapsed = time.time() - self._start_time
            line = f"\r  {CLR_PRIMARY}{frame}{C_RESET} {CLR_LAVENDER}{self.message}{C_RESET} {CLR_MUTED}({elapsed:.1f}s){C_RESET}"
            sys.stdout.write(line)
            sys.stdout.flush()
            idx += 1
            time.sleep(0.08)

    def __enter__(self) -> "LiveStatus":
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

# -----------------------------------------------------------------------------
# Environment & Key Discovery (No reliance on internal app modules)
# -----------------------------------------------------------------------------

def find_gemini_api_key() -> str:
    """Finds the GEMINI_API_KEY from environment, .env files, config.json, or state.json."""
    # 1. Direct environment variable
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(var, "").strip()
        if val:
            return val

    gemini_home = Path.home() / ".gemini"

    # 2. Check ~/.gemini/.env and ./.env
    for env_path in (gemini_home / ".env", Path(".env"), Path("/opt/gemini/.env")):
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                            cleaned = v.strip().strip("'\"")
                            if cleaned:
                                return cleaned
            except Exception:
                pass

    # 3. Check ~/.gemini/config.json
    cfg_file = gemini_home / "config.json"
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            k = data.get("GEMINI_API_KEY") or data.get("gemini_api_key")
            if k and isinstance(k, str) and k.strip():
                return k.strip()
        except Exception:
            pass

    # 4. Check ~/.gemini/state.json
    st_file = gemini_home / "state.json"
    if st_file.exists():
        try:
            data = json.loads(st_file.read_text(encoding="utf-8"))
            k = data.get("gemini_api_key") or data.get("GEMINI_API_KEY")
            if k and isinstance(k, str) and k.strip():
                return k.strip()
        except Exception:
            pass

    return ""


def get_git_status_summary(cwd: Path) -> str:
    """Returns a short git status and last commit summary for diagnosis context."""
    try:
        res = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        changes = res.stdout.strip()
        res_log = subprocess.run(
            ["git", "log", "-n", "1", "--oneline"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        last_commit = res_log.stdout.strip()
        return f"Last Commit: {last_commit}\nUnstaged/Staged Changes:\n{changes if changes else 'Clean working tree'}"
    except Exception as e:
        return f"Git status unavailable: {e}"


def get_latest_crash_log() -> str:
    """Finds the most recent crash dump in ~/.gemini/logs or logs/."""
    log_dirs = [Path.home() / ".gemini" / "logs", Path("logs"), Path("/opt/gemini/logs")]
    candidates: List[Path] = []
    for ld in log_dirs:
        if ld.exists():
            candidates.extend(ld.glob("*.log"))
            candidates.extend(ld.glob("*.txt"))

    if not candidates:
        return "No recent crash logs found."

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = candidates[0]
    try:
        content = latest.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        tail = "\n".join(lines[-30:]) if len(lines) > 30 else content
        return f"Latest Log ({latest.name}):\n{tail}"
    except Exception as e:
        return f"Failed to read {latest.name}: {e}"


# -----------------------------------------------------------------------------
# Emergency Session & Continuity Tracker
# -----------------------------------------------------------------------------

class EmergencySessionTracker:
    """Persists session runs, continuity transcripts, and tool history to ~/.gemini/emergency_state.json."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or (Path.home() / ".gemini" / "emergency_state.json")
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.data: Dict[str, Any] = self._load()
        self.current_session: Dict[str, Any] = {}

    def _load(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"total_runs": 0, "last_session": None, "sessions": []}

    def _save(self) -> None:
        try:
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            tmp.replace(self.state_file)
        except Exception:
            pass

    def start_session(self) -> int:
        self.data["total_runs"] = self.data.get("total_runs", 0) + 1
        run_number = self.data["total_runs"]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.previous_session = self.data.get("last_session")
        self.current_session = {
            "session_id": f"emg-{int(time.time())}",
            "run_number": run_number,
            "started_at": now,
            "ended_at": None,
            "duration_seconds": 0.0,
            "turns_count": 0,
            "tools_invoked": [],
            "status": "in_progress",
            "conversation_snippets": [],
        }
        self.data["active_session"] = self.current_session
        self.data["last_session"] = self.current_session
        self._save()
        return run_number

    def record_turn(self, user_msg: str, assistant_reply: str, tools_used: List[str]) -> None:
        if not self.current_session:
            return
        self.current_session["turns_count"] = self.current_session.get("turns_count", 0) + 1
        if tools_used:
            invoked = self.current_session.setdefault("tools_invoked", [])
            for t in tools_used:
                if t not in invoked:
                    invoked.append(t)

        snippet = {
            "turn": self.current_session["turns_count"],
            "user": user_msg[:250] + ("..." if len(user_msg) > 250 else ""),
            "assistant": assistant_reply[:250] + ("..." if len(assistant_reply) > 250 else ""),
            "tools": list(tools_used),
        }
        snippets = self.current_session.setdefault("conversation_snippets", [])
        snippets.append(snippet)
        self.data["last_session"] = self.current_session
        self._save()

    def end_session(self, status: str = "completed") -> None:
        if not self.current_session:
            return
        now_ts = time.time()
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts))
        self.current_session["ended_at"] = now_str
        self.current_session["status"] = status
        try:
            started_raw = self.current_session.get("started_at")
            if started_raw:
                started_ts = time.mktime(time.strptime(started_raw, "%Y-%m-%dT%H:%M:%SZ"))
                self.current_session["duration_seconds"] = round(max(0.0, now_ts - started_ts), 1)
        except Exception:
            pass

        sessions = self.data.setdefault("sessions", [])
        sessions.append(dict(self.current_session))
        # Keep last 50 session records for continuity
        self.data["sessions"] = sessions[-50:]
        self.data["last_session"] = self.current_session
        self._save()

    def get_continuity_summary(self) -> str:
        runs = self.data.get("total_runs", 0)
        sessions = self.data.get("sessions", [])
        last = sessions[-1] if sessions else getattr(self, "previous_session", None)
        if runs <= 1 or not last:
            return "This is the first time the emergency recovery terminal is being launched."
        tools = ", ".join(last.get("tools_invoked", [])) or "None"
        return (
            f"PREVIOUS EMERGENCY TERMINAL HISTORY:\n"
            f"- Total Runs Executed: {runs - 1}\n"
            f"- Last Session: #{last.get('run_number')} started at {last.get('started_at')} (Status: {last.get('status')})\n"
            f"- Turns Exchanged in Last Session: {last.get('turns_count', 0)}\n"
            f"- Tools Used in Last Session: {tools}"
        )


def get_cognitive_continuity_snapshot() -> str:
    """Reads persistent cognitive mind map, task, and working notes from ~/.gemini."""
    gemini_home = Path.home() / ".gemini"
    lines = ["COGNITIVE & MEMORY STATE CONTINUITY:"]

    # 1. Inspect live cognitive_state.json
    cog_file = gemini_home / "cognitive_state.json"
    if cog_file.exists():
        try:
            cog_data = json.loads(cog_file.read_text(encoding="utf-8"))
            task = cog_data.get("task")
            topic = cog_data.get("topic")
            thought = cog_data.get("thought")
            if task:
                lines.append(f"• Active Task: {task}")
            if topic:
                lines.append(f"• Active Topic: {topic}")
            if thought:
                lines.append(f"• Last Thought State: {thought}")
        except Exception:
            pass

    # 2. Inspect active chat from state.json
    state_file = gemini_home / "state.json"
    active_chat_id = None
    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text(encoding="utf-8"))
            active_chat_id = state_data.get("active_chat")
        except Exception:
            pass

    if active_chat_id:
        chat_dir = gemini_home / "chats" / active_chat_id
        meta_file = chat_dir / "meta.json"
        if not meta_file.exists():
            legacy_file = gemini_home / "chats" / f"{active_chat_id}.json"
            if legacy_file.exists():
                meta_file = legacy_file

        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                mind_map = meta.get("mind_map") or {}
                if mind_map.get("gemini_state"):
                    lines.append(f"• Gemini Mind State: {mind_map.get('gemini_state')}")
                if mind_map.get("user_state"):
                    lines.append(f"• User Mind State: {mind_map.get('user_state')}")
                if mind_map.get("tree_state"):
                    lines.append(f"• Tree Anchors: {mind_map.get('tree_state')}")
                if mind_map.get("tree_content"):
                    lines.append(f"• Visual Relation Tree:\n{mind_map.get('tree_content')}")

                notes_data = meta.get("notes") or ""
                if isinstance(notes_data, dict):
                    w_notes = notes_data.get("working_notes") or notes_data.get("gemini_notes") or ""
                    if w_notes:
                        lines.append(f"• Active Working Notes: {w_notes[:500]}")
                elif isinstance(notes_data, str) and notes_data.strip():
                    lines.append(f"• Active Working Notes: {notes_data[:500]}")
            except Exception:
                pass

    if len(lines) == 1:
        return "COGNITIVE & MEMORY STATE CONTINUITY: None found (Cold Boot)"
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Monolithic Autonomous Tools (Stand-alone implementations)
# -----------------------------------------------------------------------------

class EmergencyToolbox:
    """Completely decoupled execution tools that don't depend on gemini_app."""

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir.resolve()

    def print_tool_badge(self, action: str, detail: str) -> None:
        """Prints a stylish violet tool execution badge in terminal."""
        sys.stdout.write("\r\033[K")
        print(f"\n  {CLR_BG_PURPLE}{C_BOLD} TOOL {C_RESET} {CLR_PRIMARY}{action}{C_RESET} {CLR_MUTED}{detail}{C_RESET}")
        sys.stdout.flush()

    def execute_shell(self, command: str, timeout_seconds: int = 60) -> Dict[str, Any]:
        """Executes a shell command inside the working directory and returns output."""
        self.print_tool_badge("execute_shell", command[:80] + ("..." if len(command) > 80 else ""))
        short_cmd = command[:50] + ("..." if len(command) > 50 else "")
        status = LiveStatus(f"Executing: {short_cmd}")
        status.start()
        try:
            env = os.environ.copy()
            # Detect virtual environment if present
            venv_bin = self.working_dir / ".venv" / "bin"
            if venv_bin.exists():
                env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
                env["VIRTUAL_ENV"] = str(venv_bin.parent)

            res = subprocess.run(
                command,
                shell=True,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
            status.stop()
            return {
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
        except subprocess.TimeoutExpired:
            status.stop()
            return {"status": "error", "message": f"Command timed out after {timeout_seconds}s"}
        except Exception as e:
            status.stop()
            return {"status": "error", "message": str(e)}

    def read_file(self, path: str, start_line: int = 1, line_count: int = 200) -> Dict[str, Any]:
        """Reads a section or whole file with line numbers."""
        self.print_tool_badge("read_file", f"{path} (lines {start_line}-{start_line + line_count})")
        try:
            target = (self.working_dir / path).resolve()
            if not target.exists():
                return {"status": "error", "message": f"File '{path}' does not exist."}
            lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
            total_lines = len(lines)
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, start_idx + line_count)
            numbered = [f"{i + 1:4d} | {lines[i]}" for i in range(start_idx, end_idx)]
            return {
                "status": "success",
                "path": str(target),
                "total_lines": total_lines,
                "lines_shown": f"{start_idx + 1} to {end_idx}",
                "content": "\n".join(numbered),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Writes or overwrites a file on disk."""
        self.print_tool_badge("write_file", path)
        try:
            target = (self.working_dir / path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {
                "status": "success",
                "path": str(target),
                "bytes_written": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def apply_patch(self, path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
        """Applies a surgical find-and-replace patch to a file."""
        self.print_tool_badge("apply_patch", path)
        try:
            target = (self.working_dir / path).resolve()
            if not target.exists():
                return {"status": "error", "message": f"File '{path}' does not exist."}

            content = target.read_text(encoding="utf-8")
            occurrences = content.count(search_block)
            if occurrences == 0:
                return {
                    "status": "error",
                    "message": f"search_block not found in '{path}'. Context must match exactly.",
                }
            if occurrences > 1:
                return {
                    "status": "error",
                    "message": f"search_block matched {occurrences} times in '{path}'. Provide unique context.",
                }

            new_content = content.replace(search_block, replace_block, 1)
            target.write_text(new_content, encoding="utf-8")
            return {
                "status": "success",
                "path": str(target),
                "lines_delta": len(replace_block.splitlines()) - len(search_block.splitlines()),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_codebase(self, query: str, path_pattern: str = "*", max_matches: int = 50) -> Dict[str, Any]:
        """Searches workspace files for a text pattern or regex query."""
        self.print_tool_badge("search_codebase", f"query: '{query}' pattern: {path_pattern}")
        try:
            try:
                compiled_re = re.compile(query, re.IGNORECASE)
            except re.error:
                compiled_re = re.compile(re.escape(query), re.IGNORECASE)

            matches: List[str] = []
            ignored = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}

            for root, dirs, files in os.walk(self.working_dir):
                dirs[:] = [d for d in dirs if d not in ignored and not d.startswith(".")]
                for f in files:
                    if f.startswith("."):
                        continue
                    file_path = Path(root) / f
                    rel_path = file_path.relative_to(self.working_dir)
                    rel_str = str(rel_path)

                    if path_pattern and path_pattern != "*":
                        pattern_clean = path_pattern.rstrip("/*")
                        if not (
                            fnmatch.fnmatch(rel_str, path_pattern)
                            or fnmatch.fnmatch(f, path_pattern)
                            or fnmatch.fnmatch(rel_str, f"{pattern_clean}/*")
                            or fnmatch.fnmatch(rel_str, f"*{path_pattern}*")
                        ):
                            continue

                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                            for line_no, line in enumerate(fh, 1):
                                if compiled_re.search(line):
                                    matches.append(f"{rel_str}:{line_no}: {line.rstrip()}")
                                    if len(matches) >= max_matches:
                                        break
                    except Exception:
                        pass
                if len(matches) >= max_matches:
                    break

            return {
                "matches": matches,
                "status": "success",
                "total_matches": len(matches),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run_tests(self, test_target: str = "gemini_app/tests") -> Dict[str, Any]:
        """Runs python unittest suite to verify repairs."""
        self.print_tool_badge("run_tests", test_target)
        cmd = f"python3 -m unittest discover -s {test_target}"
        return self.execute_shell(cmd, timeout_seconds=120)

    def git_repair(self, action: str, commit_msg: str = "") -> Dict[str, Any]:
        """Performs safe git operations (status, diff, stash, revert, commit)."""
        self.print_tool_badge("git_repair", action)
        if action == "status":
            return self.execute_shell("git status --short")
        elif action == "diff":
            return self.execute_shell("git diff")
        elif action == "stash":
            return self.execute_shell("git stash save 'emergency_backup'")
        elif action == "rollback_last":
            return self.execute_shell("git reset --hard HEAD~1")
        elif action == "commit_fix":
            msg = commit_msg or "Emergency repair applied via emergency_terminal"
            return self.execute_shell(f'git add -A && git commit -m "{msg}"')
        else:
            return {"status": "error", "message": f"Unknown git action '{action}'"}

# -----------------------------------------------------------------------------
# Terminal UI & ASCII Aesthetics
# -----------------------------------------------------------------------------

def print_banner() -> None:
    """Renders the purple ASCII block logo and system status."""
    banner = f"""
{CLR_PRIMARY}██████╗ ███████╗███╗   ███╗██╗███╗   ██╗██╗
██╔════╝ ██╔════╝████╗ ████║██║████╗  ██║██║  {CLR_LAVENDER}{C_BOLD}[ EMERGENCY RECOVERY TERMINAL ]{C_RESET}
{CLR_PRIMARY}██║  ███╗█████╗  ██╔████╔██║██║██╔██╗ ██║██║  {CLR_MUTED}Mode:{C_RESET} Standalone Out-Of-Band Bridge
{CLR_PRIMARY}██║   ██║██╔══╝  ██║╚██╔╝██║██║██║╚██╗██║██║  {CLR_MUTED}Theme:{C_RESET} Violet / Purple
{CLR_PRIMARY}╚██████╔╝███████╗██║ ╚═╝ ██║██║██║ ╚████║██║  {CLR_MUTED}Status:{C_RESET} {CLR_GREEN}ACTIVE & ARMED{C_RESET}
{CLR_MUTED}─────────────────────────────────────────────────────────────────────────────{C_RESET}
"""
    print(banner)


def print_system_info(cwd: Path, key_present: bool, run_number: int = 1, total_runs: int = 1) -> None:
    """Prints a fast diagnosis panel."""
    print(f" {CLR_DARK_PURPLE}◈{C_RESET} {CLR_LAVENDER}Workspace:{C_RESET} {cwd}")
    key_status = f"{CLR_GREEN}Found & Configured{C_RESET}" if key_present else f"{CLR_RED}NOT FOUND (run with --key or export GEMINI_API_KEY){C_RESET}"
    print(f" {CLR_DARK_PURPLE}◈{C_RESET} {CLR_LAVENDER}API Key:{C_RESET}   {key_status}")
    print(f" {CLR_DARK_PURPLE}◈{C_RESET} {CLR_LAVENDER}Safety:{C_RESET}    Triage First | Non-destructive Verification | Rollback Ready")
    print(f" {CLR_DARK_PURPLE}◈{C_RESET} {CLR_LAVENDER}Session:{C_RESET}   Run #{run_number} (Total Recorded: {total_runs})")
    print(f"{CLR_MUTED}─────────────────────────────────────────────────────────────────────────────{C_RESET}\n")

# -----------------------------------------------------------------------------
# Core Conversation & Triage Engine
# -----------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are Gemini running inside the Standalone Emergency Recovery Terminal.
You have been summoned because the primary bilateral console or UI application encountered a failure, lockup, or runaway state, or the user needs an out-of-band safe line to repair the system.

SAFETY & TRIAGE PROTOCOL:
1. LISTEN FIRST: When starting or greeting the user, do NOT immediately execute modifications or destructive file writes. First ask what symptoms they are seeing and check git status or crash logs.
2. DISCUSS & CONFIRM: Explain your diagnosis clearly in plain terms. Before making wide refactors, outline the targeted surgical fix.
3. SURGICAL FIXES ONLY: Prefer `apply_patch` or minimal `write_file` over massive rewrites.
4. TEST BEFORE PROCEEDING: Always invoke `run_tests` or check syntax with `execute_shell` after applying a patch.
5. ASK USER TO TEST: After verifying tests pass, invite the user to verify the app on their end or test the CLI.
6. PURPLE / VIOLET DEMEANOR: Be calm, reassuring, highly technical, and direct. You are their emergency co-pilot.
"""

def run_emergency_session(api_key: str, working_dir: Path) -> None:
    """Main interactive recovery REPL loop."""
    tracker = EmergencySessionTracker()
    run_number = tracker.start_session()
    total_runs = tracker.data.get("total_runs", run_number)

    print_banner()
    print_system_info(working_dir, bool(api_key), run_number=run_number, total_runs=total_runs)

    if not GENAI_AVAILABLE:
        print(f"\n{CLR_RED}Error: 'google.genai' is not installed in this Python environment.{C_RESET}")
        print(f"{CLR_MUTED}Try running with: /opt/gemini/.venv/bin/python emergency_terminal.py{C_RESET}\n")
        tracker.end_session("missing_dependency")
        sys.exit(1)

    if not api_key:
        print(f"\n{CLR_RED}Error: GEMINI_API_KEY could not be located.{C_RESET}")
        print(f"Please enter your key or run: export GEMINI_API_KEY='your_key'")
        try:
            api_key = input(f"{rl_esc(CLR_LAVENDER)}Enter Gemini API Key: {rl_esc(C_RESET)}").strip()
            if not api_key:
                print("No key entered. Exiting.")
                tracker.end_session("missing_api_key")
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            tracker.end_session("aborted")
            sys.exit(0)

    # Initialize Client & Toolbox
    os.environ["GEMINI_API_KEY"] = api_key
    client = genai.Client(api_key=api_key)
    toolbox = EmergencyToolbox(working_dir)

    tools_list = [
        toolbox.execute_shell,
        toolbox.read_file,
        toolbox.write_file,
        toolbox.apply_patch,
        toolbox.search_codebase,
        toolbox.run_tests,
        toolbox.git_repair,
    ]
    tool_map = {fn.__name__: fn for fn in tools_list}

    # Gather initial environment snapshot for prompt
    git_snap = get_git_status_summary(working_dir)
    crash_snap = get_latest_crash_log()
    continuity_snap = tracker.get_continuity_summary()
    cognitive_snap = get_cognitive_continuity_snapshot()
    initial_context = (
        f"INITIAL SYSTEM DIAGNOSIS SNAPSHOT:\n"
        f"Working Directory: {working_dir}\n"
        f"Current Emergency Run: #{run_number} (Total Runs: {total_runs})\n"
        f"{continuity_snap}\n\n"
        f"{cognitive_snap}\n\n"
        f"{git_snap}\n\n"
        f"{crash_snap}\n"
    )

    # Setup chat session with system instruction and tools
    try:
        chat = client.chats.create(
            model=DEFAULT_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION + "\n\n" + initial_context,
                tools=tools_list,
                temperature=0.2,
            ),
        )
    except Exception as e:
        print(f"\n{CLR_RED}Failed to initialize Gemini recovery session: {e}{C_RESET}")
        tracker.end_session("init_failed")
        sys.exit(1)

    # Setup Readline history in ~/.gemini
    hist_file = Path.home() / ".gemini" / "emergency_history.txt"
    try:
        hist_file.parent.mkdir(parents=True, exist_ok=True)
        if hist_file.exists():
            readline.read_history_file(str(hist_file))
    except Exception:
        pass

    def dispatch_turn(user_msg: str) -> None:
        """Sends user message, executes tool calls iteratively, and prints streaming/final reply."""
        nonlocal chat
        current_input = user_msg

        max_iterations = 10
        iteration = 0
        turn_tools: List[str] = []
        status = LiveStatus()

        while iteration < max_iterations:
            iteration += 1
            if iteration == 1:
                status.start("Thinking & consulting Gemini recovery co-pilot...")
            else:
                status.start("Synthesizing diagnosis & follow-up...")

            try:
                response = chat.send_message(current_input)
            except Exception as net_err:
                status.stop()
                print(f"\n{CLR_RED}[API Error] {net_err}{C_RESET}")
                return

            status.stop()

            # Check for function calls
            has_fc = False
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                if part.function_call:
                    has_fc = True
                    fn_name = part.function_call.name
                    fn_args = dict(part.function_call.args) if part.function_call.args else {}
                    if fn_name not in turn_tools:
                        turn_tools.append(fn_name)

                    # Execute local tool
                    if fn_name in tool_map:
                        try:
                            fn_result = tool_map[fn_name](**fn_args)
                        except Exception as tool_err:
                            fn_result = {"status": "error", "message": str(tool_err)}
                    else:
                        fn_result = {"status": "error", "message": f"Tool '{fn_name}' not recognized."}

                    # Feed result back to Gemini
                    current_input = types.Part.from_function_response(
                        name=fn_name,
                        response={"result": fn_result},
                    )

            if not has_fc:
                # Output text reply
                status.stop()
                reply_text = response.text or ""
                # Strip mind map footer if present
                clean_reply = re.sub(r"```json:mind_map[\s\S]*?```", "", reply_text).strip()
                print(f"\n{CLR_PRIMARY}{C_BOLD}Gemini Recovery:{C_RESET}\n{clean_reply}\n")
                tracker.record_turn(user_msg, clean_reply, turn_tools)
                break

    # First turn: Gemini initiates triage greeting
    print(f"{CLR_MUTED}Initializing recovery handshake...{C_RESET}")
    dispatch_turn("Hello. The emergency terminal has just booted up. Please introduce yourself, review the initial system diagnosis snapshot, and ask me what happened so we can triage.")

    # Interactive REPL loop (Prompt escape codes wrapped with rl_esc to prevent cursor walking)
    prompt_str = f"{rl_esc(CLR_LAVENDER + C_BOLD)}emergency {rl_esc(CLR_PRIMARY)}❯{rl_esc(C_RESET)} "
    while True:
        try:
            line = input(prompt_str).strip()
            if not line:
                continue

            if line.lower() in ("exit", "quit", "q", "/exit"):
                tracker.end_session("completed")
                print(f"\n{CLR_MUTED}Closing emergency recovery terminal. Stay safe!{C_RESET}")
                break

            if line.lower() in ("help", "/help"):
                print(f"\n{CLR_LAVENDER}Emergency Commands:{C_RESET}")
                print(f"  {CLR_PRIMARY}exit, quit{C_RESET}      - Exit to system shell")
                print(f"  {CLR_PRIMARY}tests{C_RESET}           - Manually run project test suite")
                print(f"  {CLR_PRIMARY}git status{C_RESET}      - Inspect repo status")
                print(f"  {CLR_PRIMARY}git diff{C_RESET}        - Inspect changes")
                print(f"  {CLR_PRIMARY}clear{C_RESET}           - Clear screen\n")
                continue

            if line.lower() == "clear":
                os.system("clear")
                print_banner()
                continue

            if line.lower() == "tests":
                cmd_status = LiveStatus("Running project test suite...")
                cmd_status.start()
                res = toolbox.run_tests()
                cmd_status.stop()
                out = res.get("stdout", "") or res.get("stderr", "")
                print(f"\n{out}\n")
                continue

            if line.lower() == "git status":
                cmd_status = LiveStatus("Checking git status...")
                cmd_status.start()
                res = toolbox.git_repair("status")
                cmd_status.stop()
                print(f"\n{res.get('stdout', '')}\n")
                continue

            if line.lower() == "git diff":
                cmd_status = LiveStatus("Fetching git diff...")
                cmd_status.start()
                res = toolbox.git_repair("diff")
                cmd_status.stop()
                print(f"\n{res.get('stdout', '')}\n")
                continue

            dispatch_turn(line)

        except KeyboardInterrupt:
            tracker.end_session("interrupted")
            print(f"\n{CLR_AMBER}[Interrupted] Press Ctrl+D or type 'exit' to quit.{C_RESET}")
        except EOFError:
            tracker.end_session("completed")
            print(f"\n{CLR_MUTED}Session closed.{C_RESET}")
            break

    tracker.end_session("completed")

    # Save history on clean exit
    try:
        readline.write_history_file(str(hist_file))
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Entry Point & CLI Arguments
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Emergency Recovery Terminal for Gemini Integrated")
    parser.add_argument("--key", default="", help="Provide Gemini API key directly")
    parser.add_argument("--dir", default=".", help="Target workspace directory (default: current directory)")
    parser.add_argument("--check", action="store_true", help="Perform sanity check and test API connectivity, then exit")

    args = parser.parse_args()
    target_dir = Path(args.dir).resolve()

    api_key = args.key or find_gemini_api_key()

    if args.check:
        print_banner()
        print(f"{CLR_LAVENDER}Running Emergency Terminal Pre-Flight Sanity Check:{C_RESET}")
        print(f"  1. Python Version:      {sys.version.split()[0]} ({CLR_GREEN}PASS{C_RESET})")
        print(f"  2. google.genai module: {'FOUND (' + CLR_GREEN + 'PASS' + C_RESET + ')' if GENAI_AVAILABLE else CLR_RED + 'MISSING' + C_RESET}")
        print(f"  3. API Key Discovery:   {'FOUND (' + CLR_GREEN + 'PASS' + C_RESET + ')' if api_key else CLR_AMBER + 'NOT FOUND' + C_RESET}")
        print(f"  4. Workspace:           {target_dir} ({CLR_GREEN}PASS{C_RESET})")
        
        if GENAI_AVAILABLE and api_key:
            try:
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model=DEFAULT_MODEL,
                    contents="respond with 'OK' only",
                )
                txt = resp.text.strip() if resp.text else ""
                print(f"  5. Live API Ping:       {CLR_GREEN}CONNECTED ({txt}){C_RESET}")
            except Exception as e:
                print(f"  5. Live API Ping:       {CLR_RED}FAILED ({e}){C_RESET}")
        print(f"\n{CLR_GREEN}Pre-flight check completed.{C_RESET}\n")
        return

    run_emergency_session(api_key, target_dir)


if __name__ == "__main__":
    main()
