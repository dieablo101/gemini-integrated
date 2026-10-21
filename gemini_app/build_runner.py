"""Autonomous System Build & Task Runner.

Provides a general-purpose execution engine for long-running system tasks,
compilation harnesses, git operations, and package installations.

Features:
- CPU and I/O nice throttling to protect interactive responsiveness.
- Line-by-line output logging to persistent log files.
- Periodic status updates, animated toasts, and navbar pulses sent to the live Gemini console.
- Automatic conversational chat feed completion reports.
- Synchronous or detached background execution.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Union

from gemini_app.config import GEMINI_HOME
from gemini_app.task_runner import clear_status, notify_chat, update_status

DEFAULT_LOG_DIR = GEMINI_HOME / "logs" / "builds"


class SystemRunner:
    """Orchestrates system builds and long-running shell processes."""

    def __init__(
        self,
        task_name: str = "system_task",
        log_path: Optional[Union[str, Path]] = None,
        nice_level: int = 15,
        monitor_interval: float = 30.0,
        enable_notifications: bool = True,
    ) -> None:
        self.task_name = task_name
        self.nice_level = nice_level
        self.monitor_interval = monitor_interval
        self.enable_notifications = enable_notifications

        if log_path:
            self.log_path = Path(log_path).expanduser().resolve()
        else:
            DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.log_path = DEFAULT_LOG_DIR / f"{task_name}_{timestamp}.log"

        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        """Appends a timestamped line to the runner log."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

    def notify(
        self,
        text: str,
        toast: Optional[str] = None,
        title: str = "",
        severity: str = "information",
        pulse: bool = False,
        color: str = "cyan",
        duration: float = 3.5,
    ) -> None:
        """Emits console status and toast notification if enabled."""
        self.log(f"STATUS: {text} | TOAST: {toast}")
        if self.enable_notifications:
            update_status(
                text=text,
                toast=toast,
                title=title or self.task_name,
                severity=severity,
                pulse_nav=pulse,
                color=color,
                duration=duration,
            )

    def finish_chat(
        self,
        summary: str,
        toast: Optional[str] = None,
        title: str = "Build Complete",
        pulse: bool = True,
    ) -> None:
        """Injects a completion summary card into the chat feed."""
        self.log(f"CHAT FEED CARD: {summary[:100]}...")
        if self.enable_notifications:
            notify_chat(
                text=summary,
                toast=toast,
                title=title,
                pulse_nav=pulse,
            )

    def run_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[Union[str, Path]] = None,
        stage_name: str = "",
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        on_line: Optional[Callable[[str], None]] = None,
    ) -> subprocess.CompletedProcess:
        """Executes a command with CPU throttling and live monitoring."""
        if isinstance(cmd, str):
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = list(cmd)

        working_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        working_dir.mkdir(parents=True, exist_ok=True)

        # Apply nice command prefix if nice executable is present
        exec_cmd = cmd_list
        nice_bin = shutil.which("nice")
        if nice_bin and self.nice_level != 0:
            exec_cmd = [nice_bin, "-n", str(self.nice_level)] + cmd_list

        self.log(f"Running: {' '.join(shlex.quote(c) for c in exec_cmd)} in {working_dir}")

        start_time = time.monotonic()
        last_monitor = start_time

        active_env = os.environ.copy()
        if env:
            active_env.update(env)

        proc = subprocess.Popen(
            exec_cmd,
            cwd=str(working_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=active_env,
        )

        output_lines: List[str] = []

        try:
            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if line:
                    output_lines.append(line)
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(line)
                    if on_line:
                        try:
                            on_line(line)
                        except Exception:
                            pass

                ret = proc.poll()
                if ret is not None:
                    # Drain remaining output
                    if proc.stdout:
                        for remaining in proc.stdout.readlines():
                            output_lines.append(remaining)
                            with open(self.log_path, "a", encoding="utf-8") as f:
                                f.write(remaining)
                    break

                now = time.monotonic()
                if timeout and (now - start_time) > timeout:
                    proc.kill()
                    self.log(f"Command timed out after {timeout} seconds.")
                    raise subprocess.TimeoutExpired(cmd_list, timeout, "".join(output_lines))

                if now - last_monitor >= self.monitor_interval:
                    last_monitor = now
                    elapsed_min = int((now - start_time) // 60)
                    elapsed_sec = int((now - start_time) % 60)
                    time_str = f"{elapsed_min}m {elapsed_sec:02d}s"
                    display_stage = stage_name or self.task_name
                    self.notify(
                        text=f"⚡ {display_stage} — active ({time_str} elapsed)...",
                        toast=f"{display_stage} in progress ({time_str})" if elapsed_min > 0 and elapsed_min % 10 == 0 else None,
                        title=self.task_name,
                        pulse=False,
                    )

                time.sleep(0.05)

        except Exception as e:
            if proc.poll() is None:
                proc.kill()
            self.log(f"Execution error: {e}")
            raise
        finally:
            if proc.stdout:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

        if proc.returncode != 0:
            err_msg = f"Command failed with exit code {proc.returncode}"
            self.log(err_msg)
            raise RuntimeError(f"{err_msg}: {' '.join(cmd_list)}")

        return subprocess.CompletedProcess(cmd_list, proc.returncode, "".join(output_lines), "")

    def run_pipeline(
        self,
        stages: List[Dict[str, Any]],
        chat_report: bool = True,
    ) -> bool:
        """Runs a sequential pipeline of stages."""
        total_stages = len(stages)
        self.log(f"Starting pipeline '{self.task_name}' with {total_stages} stages.")

        start_time = time.monotonic()
        for idx, stage in enumerate(stages, 1):
            name = stage.get("name", f"Stage {idx}")
            cmd = stage.get("cmd")
            cwd = stage.get("cwd")
            timeout = stage.get("timeout")
            color = stage.get("color", "cyan")

            self.notify(
                text=f"⚡ [{idx}/{total_stages}] {name}...",
                toast=f"Starting: {name}",
                title=self.task_name,
                pulse=True,
                color=color,
            )

            try:
                self.run_command(cmd, cwd=cwd, stage_name=name, timeout=timeout)
                self.notify(
                    text=f"✓ [{idx}/{total_stages}] {name} complete.",
                    toast=f"Finished: {name}",
                    title=self.task_name,
                    pulse=False,
                    color="green",
                )
            except Exception as e:
                self.notify(
                    text=f"❌ [{idx}/{total_stages}] {name} failed: {e}",
                    toast=f"Error in {name}",
                    title="Build Failed",
                    severity="error",
                    pulse=True,
                    color="red",
                )
                if chat_report:
                    self.finish_chat(
                        summary=f"❌ **Pipeline '{self.task_name}' Failed at Stage {idx} ({name})**\n\nError: `{e}`\nLog: `{self.log_path}`",
                        toast="Task encountered an error",
                        title="Pipeline Failed",
                    )
                return False

        elapsed = int(time.monotonic() - start_time)
        elapsed_min = elapsed // 60
        elapsed_sec = elapsed % 60
        time_display = f"{elapsed_min}m {elapsed_sec:02d}s" if elapsed_min > 0 else f"{elapsed_sec}s"

        self.notify(
            text=f"✓ Pipeline '{self.task_name}' finished successfully ({time_display}).",
            toast="All stages finished successfully!",
            title=self.task_name,
            pulse=True,
            color="green",
        )

        if chat_report:
            self.finish_chat(
                summary=f"🎉 **Pipeline '{self.task_name}' Completed Successfully!**\n\n• **Stages Completed**: {total_stages}/{total_stages}\n• **Total Time**: {time_display}\n• **Build Log**: `{self.log_path}`",
                toast=f"Pipeline {self.task_name} complete!",
                title="Task Finished",
            )

        time.sleep(2)
        clear_status()
        return True


def run_detached_runner(
    cmd: str,
    task_name: str = "build",
    cwd: Optional[str] = None,
    chat_on_finish: bool = True,
    nice: int = 15,
) -> int:
    """Spawns an independent background runner process and returns its PID."""
    args = [
        sys.executable,
        "-m",
        "gemini_app.build_runner",
        cmd,
        "--name",
        task_name,
        "--nice",
        str(nice),
    ]
    if cwd:
        args.extend(["--cwd", str(cwd)])
    if chat_on_finish:
        args.append("--chat-finish")

    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid


def cli_main(argv: Optional[List[str]] = None) -> int:
    """CLI interface for gemini-runner."""
    parser = argparse.ArgumentParser(
        prog="gemini-runner",
        description="Autonomous Throttled Background Task & Build Runner for Gemini Console",
    )
    parser.add_argument("command", help="Shell command to execute")
    parser.add_argument("--name", "-n", default="task", help="Name of the build or task")
    parser.add_argument("--cwd", default=None, help="Working directory for command")
    parser.add_argument("--nice", type=int, default=15, help="Process nice priority (default 15)")
    parser.add_argument("--log", default=None, help="Custom log file destination")
    parser.add_argument("--chat-finish", action="store_true", help="Post completion summary to chat feed")
    parser.add_argument("--timeout", type=float, default=None, help="Maximum execution timeout in seconds")
    parser.add_argument("--no-notify", action="store_true", help="Disable console notifications")

    args = parser.parse_args(argv)

    runner = SystemRunner(
        task_name=args.name,
        log_path=args.log,
        nice_level=args.nice,
        enable_notifications=not args.no_notify,
    )

    runner.notify(
        text=f"⚡ Starting task '{args.name}'...",
        toast=f"Task '{args.name}' started",
        title=args.name,
        pulse=True,
        color="cyan",
    )

    start_time = time.monotonic()
    try:
        runner.run_command(
            cmd=args.command,
            cwd=args.cwd,
            stage_name=args.name,
            timeout=args.timeout,
        )
        elapsed = int(time.monotonic() - start_time)
        time_display = f"{elapsed // 60}m {elapsed % 60:02d}s" if elapsed >= 60 else f"{elapsed}s"

        runner.notify(
            text=f"✓ Task '{args.name}' finished successfully ({time_display}).",
            toast=f"Task '{args.name}' complete!",
            title=args.name,
            pulse=True,
            color="green",
        )

        if args.chat_finish:
            runner.finish_chat(
                summary=f"🎉 **Task '{args.name}' Finished Successfully!**\n\n• **Command**: `{args.command}`\n• **Duration**: {time_display}\n• **Log**: `{runner.log_path}`",
                toast=f"Task '{args.name}' complete!",
                title="Task Finished",
            )
        time.sleep(1.5)
        clear_status()
        return 0
    except Exception as e:
        runner.notify(
            text=f"❌ Task '{args.name}' failed: {e}",
            toast=f"Task failed: {e}",
            title="Task Error",
            severity="error",
            pulse=True,
            color="red",
        )
        if args.chat_finish:
            runner.finish_chat(
                summary=f"❌ **Task '{args.name}' Failed**\n\n• **Command**: `{args.command}`\n• **Error**: `{e}`\n• **Log**: `{runner.log_path}`",
                toast=f"Task '{args.name}' failed",
                title="Task Failed",
            )
        return 1


if __name__ == "__main__":
    sys.exit(cli_main())
