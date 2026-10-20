"""Host telemetry collection for Mothership and Satellite nodes.

Provides robust, zero-dependency metrics collection across Linux, macOS,
and constrained mobile environments (Alpine iSH, Android Termux).
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional


# Module-level cache for instantaneous /proc/stat CPU calculation
_LAST_CPU_STAT = {"idle": 0.0, "total": 0.0, "time": 0.0}


def get_cpu_and_mem_vitals() -> Dict[str, Any]:
    """Collects CPU and Memory metrics using /proc or standard library fallbacks."""
    global _LAST_CPU_STAT
    cpu_pct = 0.0
    mem_total_mb = 0.0
    mem_used_mb = 0.0
    mem_pct = 0.0

    # 1. Memory via /proc/meminfo if on Linux
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            mem_data: Dict[str, float] = {}
            for line in meminfo_path.read_text().splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    k = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    if val.isdigit():
                        mem_data[k] = float(val) / 1024.0  # MB
            if "MemTotal" in mem_data and "MemAvailable" in mem_data:
                mem_total_mb = round(mem_data["MemTotal"], 1)
                mem_avail = mem_data["MemAvailable"]
                mem_used_mb = round(mem_total_mb - mem_avail, 1)
                if mem_total_mb > 0:
                    mem_pct = round((mem_used_mb / mem_total_mb) * 100.0, 1)
        except Exception:
            pass

    # 2. CPU load average
    load_avg = [0.0, 0.0, 0.0]
    if hasattr(os, "getloadavg"):
        try:
            load = os.getloadavg()
            load_avg = [round(x, 2) for x in load]
        except Exception:
            pass

    # 3. Instantaneous CPU percentage via /proc/stat delta tracking
    proc_stat = Path("/proc/stat")
    calculated_proc_cpu = False
    if proc_stat.exists():
        try:
            first_line = proc_stat.read_text().splitlines()[0]
            if first_line.startswith("cpu "):
                fields = [float(x) for x in first_line.split()[1:]]
                idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0)
                total = sum(fields)
                last_idle = _LAST_CPU_STAT["idle"]
                last_total = _LAST_CPU_STAT["total"]
                if last_total > 0 and total > last_total:
                    idle_delta = idle - last_idle
                    total_delta = total - last_total
                    if total_delta > 0:
                        raw_pct = (1.0 - (idle_delta / total_delta)) * 100.0
                        cpu_pct = round(max(0.0, min(100.0, raw_pct)), 1)
                        calculated_proc_cpu = True
                _LAST_CPU_STAT["idle"] = idle
                _LAST_CPU_STAT["total"] = total
                _LAST_CPU_STAT["time"] = time.time()
        except Exception:
            pass

    # Fallback to load average if /proc/stat delta wasn't available
    if not calculated_proc_cpu and load_avg[0] > 0:
        cpu_count = os.cpu_count() or 1
        cpu_pct = min(100.0, round((load_avg[0] / cpu_count) * 100.0, 1))

    # 4. Disk usage
    total_b, used_b, free_b = shutil.disk_usage("/")
    disk_total_gb = round(total_b / (1024 ** 3), 1)
    disk_free_gb = round(free_b / (1024 ** 3), 1)
    disk_pct = round(((total_b - free_b) / total_b) * 100.0, 1) if total_b > 0 else 0.0

    return {
        "cpu_pct": cpu_pct,
        "load_avg": load_avg,
        "mem_total_mb": mem_total_mb,
        "mem_used_mb": mem_used_mb,
        "mem_pct": mem_pct,
        "disk_free_gb": disk_free_gb,
        "disk_total_gb": disk_total_gb,
        "disk_pct": disk_pct,
    }


def get_git_vitals(repo_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Retrieves current Git status, branch, commit, and recent history."""
    working_dir = repo_dir or Path.cwd()
    commit_sha = "unknown"
    branch = "unknown"
    commit_msg = ""
    is_clean = True
    recent_commits: List[Dict[str, str]] = []

    try:
        # Branch
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            branch = res.stdout.strip()

        # Short Commit
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            commit_sha = res.stdout.strip()

        # Latest commit subject
        res = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            commit_msg = res.stdout.strip()

        # Dirty check
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            is_clean = len(res.stdout.strip()) == 0

        # Recent 3 commits
        res = subprocess.run(
            ["git", "log", "-3", "--format=%h %s"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().splitlines():
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    recent_commits.append({"sha": parts[0], "message": parts[1]})
                elif len(parts) == 1:
                    recent_commits.append({"sha": parts[0], "message": ""})
    except Exception:
        pass

    return {
        "branch": branch,
        "commit": commit_sha,
        "commit_msg": commit_msg,
        "is_clean": is_clean,
        "recent_commits": recent_commits,
    }


def collect_mothership_telemetry(
    cognitive_override: Optional[Dict[str, Any]] = None,
    satellites_info: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Assembles a full telemetry payload for Mothership broadcasting."""
    vitals = get_cpu_and_mem_vitals()
    git_info = get_git_vitals()

    # Cognitive state defaults
    cognitive = {
        "state_desc": "Mothership Active | Telemetry Service",
        "task": "Distributed Node Telemetry & Auto-Update HUD",
        "topic": "fleet & satellite nodes",
        "thought": "Streaming real-time telemetry and cognitive state to connected nodes...",
        "tool": "none",
        "turn_number": 19,
    }
    if cognitive_override:
        cognitive.update(cognitive_override)

    return {
        "host": socket.gethostname(),
        "platform": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "timestamp": time.time(),
        "time_str": time.strftime("%H:%M:%S"),
        "vitals": vitals,
        "git": git_info,
        "cognitive": cognitive,
        "satellites_count": len(satellites_info) if satellites_info else 0,
        "satellites": satellites_info or [],
    }
