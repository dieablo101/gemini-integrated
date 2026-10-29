#!/usr/bin/env python3
"""
Substrate Dieablo Runner - 60-Second Silicon Telemetry Harness
Project Photon Engine & Substrate Architecture

Launches dieablo Godot runtime with Substrate Clean Room Partitioning:
- Main Engine & Render Loop -> Physical Core 1 (CPU 1,3 clean room)
- Worker pools, disk cache, audio, WSI swapchain -> Physical Core 0 (CPU 0,2)
samples PhotonBridge IPC and kernel rusage telemetry, and generates a
complete 1-minute live silicon audit.
"""

import os
import sys
import time
import json
import socket
import subprocess
import signal

GODOT_BIN = "/home/kidlucrid/.local/bin/godot"
PROJECT_DIR = "/home/kidlucrid/Projects/dieablo"
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

class PhotonBridgeClient:
    def __init__(self, host=PHOTON_HOST, port=PHOTON_PORT):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self, timeout=0.5):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            # Read handshake
            try:
                self.sock.recv(1024)
            except Exception:
                pass
            return True
        except Exception:
            self.sock = None
            return False

    def query_status(self):
        if not self.sock:
            return None
        try:
            cmd = json.dumps({"cmd": "status"}) + "\n"
            self.sock.sendall(cmd.encode("utf-8"))
            resp = self.sock.recv(2048).decode("utf-8")
            for line in resp.strip().split("\n"):
                if line:
                    data = json.loads(line)
                    if data.get("status") == "ok":
                        return data
        except Exception:
            pass
        return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

def run_session():
    print("================================================================================")
    print("       PHOTON SUBSTRATE TIMING HARNESS: DIEABLO 1-MINUTE LIVE AUDIT             ")
    print("================================================================================")
    print(f" Target Game        : {PROJECT_DIR}")
    print(f" Godot Binary       : {GODOT_BIN}")
    print(f" Substrate Affinity : Main Thread -> Core 1 (1,3), Background Workers -> Core 0 (0,2)")
    print(f" Sample Window      : {DURATION_SECONDS} seconds")
    print(f" IPC Telemetry      : {PHOTON_HOST}:{PHOTON_PORT} (PhotonBridge)")
    print("================================================================================")

    # Launch Godot pinned to Core 1 initially
    env = os.environ.copy()
    if "DISPLAY" not in env or not env["DISPLAY"]:
        env["DISPLAY"] = ":0.0"

    cmd = [GODOT_BIN, "--path", PROJECT_DIR]
    print(f"[LAUNCH] Executing: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid = proc.pid
    print(f"[LAUNCH] Dieablo running with PID {pid}.")

    # Apply Clean Room Partitioning immediately
    time.sleep(0.3)
    partition_thread_affinity(pid)
    print(f"[SUBSTRATE] Clean Room Partition Applied: Main Thread -> Core 1, Workers -> Core 0.")

    # Establish IPC Bridge connection
    bridge = PhotonBridgeClient()
    print("[IPC] Waiting for PhotonBridge handshake...")
    connected = False
    for _ in range(20):
        if proc.poll() is not None:
            print("[ERROR] Game exited prematurely before bridge connection.")
            return
        if bridge.connect():
            connected = True
            print("[IPC] PhotonBridge connected successfully!")
            break
        time.sleep(0.5)

    if not connected:
        print("[WARN] PhotonBridge did not respond; proceeding with kernel silicon telemetry only.")

    initial_vol, initial_nonvol = get_proc_context_switches(pid)
    initial_temp = get_cpu_temp_c()
    samples = []

    print("\n>>> ACTIVE 1-MINUTE GAMEPLAY BENCHMARK STARTED. PLAY DIEABLO NOW! <<<\n")
    start_time = time.time()
    next_tick = start_time + 1.0
    tick_count = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= DURATION_SECONDS:
            break
        if proc.poll() is not None:
            print(f"\n[INFO] Dieablo closed by user after {elapsed:.1f}s.")
            break

        # Re-partition every 2 seconds to catch newly spawned threads
        tick_count += 1
        if tick_count % 2 == 0:
            partition_thread_affinity(pid)

        # Collect telemetry
        vol, nonvol = get_proc_context_switches(pid)
        freq = get_cpu_freq_ghz(TARGET_CORE)
        temp = get_cpu_temp_c()
        status = bridge.query_status() if connected else None

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

        # Print live tick
        sys.stdout.write(
            f"\r[{elapsed:4.1f}s / {DURATION_SECONDS}s] "
            f"FPS: {fps:3d} | "
            f"Freq: {freq:.2f} GHz | "
            f"Temp: {temp:.1f}°C | "
            f"Involuntary Switches: {sample['invol_switches']:3d} | "
            f"Yields: {sample['vol_switches']:4d}"
        )
        sys.stdout.flush()

        sleep_needed = next_tick - time.time()
        if sleep_needed > 0:
            time.sleep(sleep_needed)
        next_tick += 1.0

    print("\n\n>>> 1-MINUTE TEST SESSION COMPLETE! GATHERING FINAL SILICON AUDIT <<<\n")
    final_vol, final_nonvol = get_proc_context_switches(pid)
    final_temp = get_cpu_temp_c()
    total_elapsed = time.time() - start_time

    # Clean up bridge
    bridge.close()

    # Calculate audit metrics
    total_invol = final_nonvol - initial_nonvol
    total_vol = final_vol - initial_vol
    valid_fps = [s["fps"] for s in samples if s["fps"] > 0]
    avg_fps = sum(valid_fps) / max(1, len(valid_fps))
    max_fps = max(valid_fps, default=0)
    avg_freq = sum(s["freq_ghz"] for s in samples) / max(1, len(samples))
    temp_delta = final_temp - initial_temp

    audit_report = {
        "target_core": TARGET_CORE,
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
            "target_floor_ghz": 3.0,
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
        json.dump(audit_report, f, indent=2)

    # Format audit banner
    print("================================================================================")
    print("                    SUBSTRATE SILICON TELEMETRY AUDIT REPORT                    ")
    print("================================================================================")
    print(f" Duration Monitored   : {total_elapsed:.2f} seconds ({len(samples)} temporal slices)")
    print(f" Partition Affinity   : Main Thread -> Core 1 | Workers -> Core 0")
    purity_str = "\033[1;32m100.0% PURE (ZERO INVOLUNTARY PREEMPTION)\033[0m" if total_invol == 0 else f"\033[1;33m{audit_report['clean_room_purity']['purity_percentage']}% PURE ({total_invol} involuntary preemptions)\033[0m"
    print(f" Clean Room Integrity : {purity_str}")
    print(f" Involuntary Switches : {total_invol}")
    print(f" Voluntary Yields     : {total_vol}")
    print(f" Core Clock (Avg/Max) : {avg_freq:.3f} GHz / {audit_report['silicon_frequency']['max_measured_ghz']:.3f} GHz")
    print(f" Thermal Gradient     : {initial_temp:.1f}°C -> {final_temp:.1f}°C (Delta: {temp_delta:+.1f}°C)")
    print(f" Render Framerate     : Avg {avg_fps:.1f} FPS (Peak: {max_fps} FPS)")
    print(f" Telemetry JSON Saved : {OUTPUT_JSON}")
    print("================================================================================\n")

    if proc.poll() is None:
        print("[STATUS] Dieablo is still running in the background. You can keep playing or close it.")
    else:
        print("[STATUS] Dieablo closed cleanly.")

if __name__ == "__main__":
    run_session()
