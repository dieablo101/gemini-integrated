#!/usr/bin/env python3
"""
Substrate Live Sampler - Attaches to running Dieablo PID or launches it,
optimizes thread affinity (Core 1 clean room for render loop, Core 0 for background),
records 60 seconds of bilateral silicon telemetry, and generates the audit report.
"""

import os
import sys
import time
import json
import socket
import subprocess

TARGET_CORE = 1
DURATION_SECONDS = 60
OUTPUT_JSON = "/home/kidlucrid/Projects/dieablo/substrate_session_1min.json"
PHOTON_HOST = "127.0.0.1"
PHOTON_PORT = 9095

def get_cpu_freq_ghz(core_id=TARGET_CORE):
    freq_path = f"/sys/devices/system/cpu/cpu{core_id}/cpufreq/scaling_cur_freq"
    try:
        with open(freq_path, "r") as f:
            khz = float(f.read().strip())
            return khz / 1e6
    except Exception:
        return 0.0

def get_cpu_temp_c():
    temp_paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/thermal/thermal_zone1/temp"
    ]
    for p in temp_paths:
        try:
            with open(p, "r") as f:
                val = float(f.read().strip())
                return val / 1000.0 if val > 1000 else val
        except Exception:
            continue
    return 0.0

def get_proc_context_switches(pid):
    status_path = f"/proc/{pid}/status"
    vol = 0
    nonvol = 0
    try:
        with open(status_path, "r") as f:
            for line in f:
                if line.startswith("voluntary_ctxt_switches:"):
                    vol = int(line.split(":")[1].strip())
                elif line.startswith("nonvoluntary_ctxt_switches:"):
                    nonvol = int(line.split(":")[1].strip())
    except Exception:
        pass
    return vol, nonvol

def partition_thread_affinity(pid):
    """
    Substrate Clean Room Partitioning:
    - Main Engine & Render Loop (TID == PID) -> Physical Core 1 (CPU 1,3 clean room)
    - Worker pools, disk cache, audio, WSI swapchain -> Core 0 (CPU 0,2)
    """
    task_dir = f"/proc/{pid}/task"
    if not os.path.exists(task_dir):
        return
    for tid_str in os.listdir(task_dir):
        try:
            tid = int(tid_str)
            if tid == pid:
                subprocess.run(["taskset", "-cp", "1,3", str(tid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["taskset", "-cp", "0,2", str(tid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            continue

def get_godot_pid():
    try:
        out = subprocess.check_output(["pgrep", "-f", "godot.*dieablo"]).decode().strip()
        lines = out.split()
        if lines:
            return int(lines[0])
    except Exception:
        pass
    return None

def query_bridge_status():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect((PHOTON_HOST, PHOTON_PORT))
        s.recv(1024)
        s.sendall(json.dumps({"cmd": "status"}).encode("utf-8") + b"\n")
        resp = s.recv(2048).decode("utf-8")
        s.close()
        for line in resp.strip().split("\n"):
            if line:
                d = json.loads(line)
                if d.get("status") == "ok":
                    return d
    except Exception:
        pass
    return None

def sample_session(pid=None, duration=DURATION_SECONDS):
    if pid is None:
        pid = get_godot_pid()
    if not pid:
        print("[ERROR] No running Dieablo instance found.")
        return None

    # Perform initial thread partitioning
    partition_thread_affinity(pid)

    initial_vol, initial_nonvol = get_proc_context_switches(pid)
    initial_temp = get_cpu_temp_c()
    samples = []

    print(f"[SAMPLER] Attached to PID {pid}.")
    print(f"[SAMPLER] Clean Room Partition Active: Main Thread -> Core 1, Background Workers -> Core 0.")
    print(f"[SAMPLER] Recording 60s of active gameplay telemetry...")

    start_time = time.time()
    next_tick = start_time + 1.0
    tick_count = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break
        if not os.path.exists(f"/proc/{pid}"):
            print(f"\n[INFO] Game process {pid} exited.")
            break

        # Re-partition every 2 seconds to catch newly spawned threads
        tick_count += 1
        if tick_count % 2 == 0:
            partition_thread_affinity(pid)

        vol, nonvol = get_proc_context_switches(pid)
        freq = get_cpu_freq_ghz(TARGET_CORE)
        temp = get_cpu_temp_c()
        status = query_bridge_status()

        fps = status.get("fps", 0) if status else 0
        scene = status.get("scene", "N/A") if status else "N/A"

        sample = {
            "elapsed_s": round(elapsed, 2),
            "freq_ghz": round(freq, 3),
            "temp_c": round(temp, 1),
            "vol_switches": vol - initial_vol,
            "invol_switches": nonvol - initial_nonvol,
            "fps": fps,
            "scene": scene
        }
        samples.append(sample)

        sys.stdout.write(
            f"\r[{elapsed:4.1f}s / {duration}s] "
            f"Scene: {scene} | "
            f"FPS: {fps:2.0f} | "
            f"Freq: {freq:.2f}GHz | "
            f"Temp: {temp:.1f}°C | "
            f"Invol Switches: {sample['invol_switches']}"
        )
        sys.stdout.flush()

        sleep_needed = next_tick - time.time()
        if sleep_needed > 0:
            time.sleep(sleep_needed)
        next_tick += 1.0

    print("\n\n>>> 60-SECOND SAMPLING FINISHED! Compiling silicon report... <<<")
    final_vol, final_nonvol = get_proc_context_switches(pid)
    final_temp = get_cpu_temp_c()
    total_elapsed = time.time() - start_time

    total_invol = final_nonvol - initial_nonvol
    total_vol = final_vol - initial_vol
    valid_fps = [s["fps"] for s in samples if s["fps"] > 0]
    avg_fps = sum(valid_fps) / max(1, len(valid_fps))
    max_fps = max(valid_fps, default=0)
    avg_freq = sum(s["freq_ghz"] for s in samples) / max(1, len(samples))
    temp_delta = final_temp - initial_temp

    report = {
        "target_core": TARGET_CORE,
        "pid": pid,
        "duration_seconds": round(total_elapsed, 2),
        "total_samples": len(samples),
        "clean_room_purity": {
            "involuntary_context_switches": total_invol,
            "voluntary_yields": total_vol,
            "zero_preemption_verified": (total_invol == 0),
            "purity_percentage": round(100.0 * (1.0 - (total_invol / max(1, total_vol + total_invol))), 2)
        },
        "silicon_frequency": {
            "avg_ghz": round(avg_freq, 3),
            "max_measured_ghz": round(max((s["freq_ghz"] for s in samples), default=0), 3)
        },
        "thermal_profile": {
            "initial_celsius": round(initial_temp, 1),
            "final_celsius": round(final_temp, 1),
            "delta_celsius": round(temp_delta, 1)
        },
        "engine_performance": {
            "avg_fps": round(avg_fps, 1),
            "max_fps": max_fps
        },
        "samples": samples
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(report, f, indent=2)

    return report

if __name__ == "__main__":
    rep = sample_session()
    if rep:
        print(f"Results written to {OUTPUT_JSON}")
