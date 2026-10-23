"""
Node Capability Profile & Whole-System Topology Engine.
Models distributed fleet compute power, use cases, tooling, efficiency,
and power states across all active nodes (Toughbook hub, iPad edge, Android PNS).
"""

from __future__ import annotations

import os
import platform
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class NodeCapabilityProfile:
    """Complete capability profile of an individual node in the fleet."""
    node_id: str
    name: str
    role: str                       # 'hub_orchestrator', 'visual_edge', 'sensory_pns', 'compute_worker'
    status: str = "online"          # 'online', 'degraded', 'offline'
    last_seen_seconds_ago: float = 0.0

    # Compute Power
    arch: str = "x86_64"
    cpu_cores: int = 4
    ram_total_mb: int = 8192
    ram_avail_mb: int = 4096
    compute_tier: int = 8           # 1 (low) to 10 (high-performance workstation)
    estimated_gflops: float = 120.0

    # Usecases & Strengths
    usecases: List[str] = field(default_factory=list)

    # Tooling & Runtimes
    tooling: List[str] = field(default_factory=list)

    # Efficiency & Communication
    latency_ms: float = 0.2         # Roundtrip latency from hub
    bandwidth_mbps: float = 1000.0  # Network/bus throughput
    efficiency_score: float = 0.85  # Work-per-watt / thermal efficiency ratio (0.0 - 1.0)

    # Power Profile
    power_source: str = "ac_mains"  # 'ac_mains', 'battery', 'usb_tethered'
    battery_pct: Optional[float] = None
    charging: Optional[bool] = None
    thermal_state: str = "nominal"  # 'nominal', 'warm', 'throttling'

    # Telemetry Attributes
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "last_seen_seconds_ago": self.last_seen_seconds_ago,
            "compute": {
                "arch": self.arch,
                "cpu_cores": self.cpu_cores,
                "ram_total_mb": self.ram_total_mb,
                "ram_avail_mb": self.ram_avail_mb,
                "compute_tier": self.compute_tier,
                "estimated_gflops": self.estimated_gflops,
            },
            "usecases": list(self.usecases),
            "tooling": list(self.tooling),
            "efficiency": {
                "latency_ms": self.latency_ms,
                "bandwidth_mbps": self.bandwidth_mbps,
                "efficiency_score": self.efficiency_score,
            },
            "power": {
                "source": self.power_source,
                "battery_pct": self.battery_pct,
                "charging": self.charging,
                "thermal_state": self.thermal_state,
            },
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NodeCapabilityProfile:
        comp = data.get("compute", {})
        eff = data.get("efficiency", {})
        pwr = data.get("power", {})
        return cls(
            node_id=data.get("node_id", "unknown_node"),
            name=data.get("name", "Unknown Node"),
            role=data.get("role", "compute_worker"),
            status=data.get("status", "online"),
            last_seen_seconds_ago=float(data.get("last_seen_seconds_ago", 0.0)),
            arch=comp.get("arch", "x86_64"),
            cpu_cores=int(comp.get("cpu_cores", 4)),
            ram_total_mb=int(comp.get("ram_total_mb", 4096)),
            ram_avail_mb=int(comp.get("ram_avail_mb", 2048)),
            compute_tier=int(comp.get("compute_tier", 5)),
            estimated_gflops=float(comp.get("estimated_gflops", 50.0)),
            usecases=list(data.get("usecases", [])),
            tooling=list(data.get("tooling", [])),
            latency_ms=float(eff.get("latency_ms", 1.0)),
            bandwidth_mbps=float(eff.get("bandwidth_mbps", 100.0)),
            efficiency_score=float(eff.get("efficiency_score", 0.7)),
            power_source=pwr.get("source", "battery"),
            battery_pct=pwr.get("battery_pct"),
            charging=pwr.get("charging"),
            thermal_state=pwr.get("thermal_state", "nominal"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WholeSystemCapability:
    """Consolidated capability horizon across all active nodes in the cluster."""
    total_nodes: int
    online_nodes: int
    total_cpu_cores: int
    total_ram_mb: int
    total_avail_ram_mb: int
    total_estimated_gflops: float
    system_efficiency_index: float
    all_usecases: List[str]
    aggregate_tooling: List[str]
    power_profile_summary: str
    workload_routing_affinity: Dict[str, str]  # task_type -> node_id
    node_profiles: List[NodeCapabilityProfile]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "online_nodes": self.online_nodes,
            "total_cpu_cores": self.total_cpu_cores,
            "total_ram_mb": self.total_ram_mb,
            "total_avail_ram_mb": self.total_avail_ram_mb,
            "total_estimated_gflops": round(self.total_estimated_gflops, 1),
            "system_efficiency_index": round(self.system_efficiency_index, 2),
            "all_usecases": self.all_usecases,
            "aggregate_tooling": self.aggregate_tooling,
            "power_profile_summary": self.power_profile_summary,
            "workload_routing_affinity": self.workload_routing_affinity,
            "nodes": [n.to_dict() for n in self.node_profiles],
        }

    def get_summary_frame(self) -> str:
        """Compact 2-3 line cluster capability frame (<60 tokens)."""
        nodes_brief = []
        for n in self.node_profiles:
            if n.status != "online":
                continue
            pwr_str = f"{int(n.battery_pct)}%" if n.battery_pct is not None else "AC"
            if n.charging:
                pwr_str += "+Chg"
            nodes_brief.append(f"{n.name}({n.arch}/{n.cpu_cores}c/{pwr_str})")
        nodes_line = " | ".join(nodes_brief)

        return (
            f"Fleet Cluster [{self.online_nodes}/{self.total_nodes} Online | "
            f"Σ {self.total_cpu_cores} cores, {self.total_ram_mb // 1024}GB RAM | "
            f"Eff: {int(self.system_efficiency_index * 100)}%]\n"
            f"• Nodes: {nodes_line}\n"
            f"• Core Routing: Sketch->iPad | PNS->Phone | Host->Toughbook"
        )


class FleetTopologySynthesizer:
    """
    Introspects local host hardware and active remote satellite nodes,
    building an integrated system capability model.
    """

    @classmethod
    def inspect_local_host(cls) -> NodeCapabilityProfile:
        """Inspects Toughbook host vitals, cores, memory, and tooling."""
        cores = os.cpu_count() or 4
        arch = platform.machine() or "x86_64"
        ram_total = 8192
        ram_avail = 4096

        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_total = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        ram_avail = int(line.split()[1]) // 1024
        except Exception:
            pass

        # Detect available tools
        detected_tools = ["python3"]
        for tool_bin in ("git", "ssh", "curl", "sqlite3", "make", "blender", "godot"):
            if shutil.which(tool_bin):
                detected_tools.append(tool_bin)

        usecases = [
            "hub_orchestration",
            "full_compilation",
            "hypergraph_indexing",
            "git_vcs",
            "local_daemon_supervisor",
            "bilateral_terminal_ui",
            "unit_testing",
        ]
        if "blender" in detected_tools:
            usecases.append("headless_3d_modeling")
        if "godot" in detected_tools:
            usecases.append("game_engine_simulation")

        return NodeCapabilityProfile(
            node_id="toughbook-hub",
            name="Toughbook Host",
            role="hub_orchestrator",
            status="online",
            last_seen_seconds_ago=0.0,
            arch=arch,
            cpu_cores=cores,
            ram_total_mb=ram_total,
            ram_avail_mb=ram_avail,
            compute_tier=8,
            estimated_gflops=140.0,
            usecases=usecases,
            tooling=detected_tools,
            latency_ms=0.1,
            bandwidth_mbps=10000.0,
            efficiency_score=0.90,
            power_source="ac_mains",
            battery_pct=None,
            charging=True,
            thermal_state="nominal",
            metadata={"hostname": platform.node(), "system": platform.system()},
        )

    @classmethod
    def parse_satellite_node(cls, raw_node: Dict[str, Any]) -> NodeCapabilityProfile:
        """Parses a node from the fleet registry / active_nodes snapshot."""
        node_id = raw_node.get("node_id", "unknown_node")
        telem = raw_node.get("telemetry", {})
        live_info = raw_node.get("live_info", {})
        if not telem and "telemetry" in live_info:
            telem = live_info["telemetry"]

        last_seen = float(raw_node.get("last_seen_seconds_ago", 0.0))
        status = raw_node.get("status", "online")
        if last_seen > 60.0:
            status = "offline"

        is_termux = telem.get("is_termux", False) or "termux" in node_id.lower()
        is_ish = telem.get("is_ish", False) or "ipad" in node_id.lower() or "ish" in node_id.lower()

        # Defaults based on platform archetype
        if is_termux:
            name = "Android Phone (Termux)"
            role = "sensory_pns"
            arch = telem.get("machine", "aarch64")
            cores = 8
            ram_total = telem.get("mem_total_mb", 7204)
            ram_avail = telem.get("mem_avail_mb", 350)
            compute_tier = 6
            gflops = 65.0
            usecases = [
                "pns_sensory_streaming",
                "ambient_photodiode_lux",
                "accelerometer_motion",
                "audio_db_monitoring",
                "quick_voice_capture",
                "asynchronous_task_queuing",
            ]
            tooling = ["python3", "termux-sensor", "termux-api", "git", "ssh"]
            latency = 12.0
            bandwidth = 150.0
            eff = 0.88
            battery = telem.get("battery", {})
            bat_pct = battery.get("percentage", 50.0)
            chg = battery.get("charging", False)
            pwr_source = "usb_tethered" if chg else "battery"
        elif is_ish:
            name = "iPad Satellite (iSH Alpine)"
            role = "visual_edge"
            arch = telem.get("machine", "i686")  # iSH runs 32-bit x86 emulator on iOS
            cores = 2
            ram_total = telem.get("mem_total_mb", 11799)
            ram_avail = telem.get("mem_avail_mb", 1859)
            compute_tier = 4
            gflops = 25.0
            usecases = [
                "multimodal_sketch_ingest",
                "ios_files_mount",
                "secondary_hud_terminal",
                "lightweight_alpine_utilities",
                "mobile_review",
            ]
            tooling = ["python3", "apk", "git", "ssh", "ios_mount"]
            latency = 9.0
            bandwidth = 200.0
            eff = 0.75
            pwr_source = "battery"
            bat_pct = 75.0
            chg = False
        else:
            name = f"Node ({node_id})"
            role = "compute_worker"
            arch = telem.get("machine", "x86_64")
            cores = 4
            ram_total = telem.get("mem_total_mb", 4096)
            ram_avail = telem.get("mem_avail_mb", 2048)
            compute_tier = 5
            gflops = 45.0
            usecases = ["distributed_worker", "ssh_execution"]
            tooling = ["python3", "ssh"]
            latency = 20.0
            bandwidth = 100.0
            eff = 0.70
            pwr_source = "battery"
            bat_pct = None
            chg = None

        return NodeCapabilityProfile(
            node_id=node_id,
            name=name,
            role=role,
            status=status,
            last_seen_seconds_ago=last_seen,
            arch=arch,
            cpu_cores=cores,
            ram_total_mb=ram_total,
            ram_avail_mb=ram_avail,
            compute_tier=compute_tier,
            estimated_gflops=gflops,
            usecases=usecases,
            tooling=tooling,
            latency_ms=latency,
            bandwidth_mbps=bandwidth,
            efficiency_score=eff,
            power_source=pwr_source,
            battery_pct=bat_pct,
            charging=chg,
            thermal_state="nominal",
            metadata=telem,
        )

    @classmethod
    def synthesize_fleet(cls, raw_fleet_snapshot: Optional[Dict[str, Any]] = None) -> WholeSystemCapability:
        """
        Synthesizes Toughbook host + all fleet nodes into a unified WholeSystemCapability.
        """
        host_profile = cls.inspect_local_host()
        profiles: List[NodeCapabilityProfile] = [host_profile]

        if raw_fleet_snapshot:
            raw_nodes = raw_fleet_snapshot.get("nodes", [])
            for rn in raw_nodes:
                nid = rn.get("node_id", "")
                if nid in ("console-client", "toughbook-hub"):
                    # Local client already covered by host inspection
                    continue
                sat_profile = cls.parse_satellite_node(rn)
                profiles.append(sat_profile)

        online_profiles = [p for p in profiles if p.status == "online"]
        total_cores = sum(p.cpu_cores for p in online_profiles)
        total_ram = sum(p.ram_total_mb for p in online_profiles)
        total_avail_ram = sum(p.ram_avail_mb for p in online_profiles)
        total_gflops = sum(p.estimated_gflops for p in online_profiles)

        # Efficiency index: average efficiency weighted by online compute share
        eff_sum = sum(p.efficiency_score * p.estimated_gflops for p in online_profiles)
        avg_eff = (eff_sum / max(1.0, total_gflops)) if total_gflops > 0 else 0.8

        # Collect unique usecases & tooling
        all_usecases: Set[str] = set()
        aggregate_tooling: Set[str] = set()
        for p in online_profiles:
            all_usecases.update(p.usecases)
            aggregate_tooling.update(p.tooling)

        # Workload routing affinity matrix
        routing: Dict[str, str] = {
            "compilation": host_profile.node_id,
            "indexing": host_profile.node_id,
            "unit_testing": host_profile.node_id,
            "orchestration": host_profile.node_id,
        }
        for p in online_profiles:
            if p.role == "visual_edge" or "multimodal_sketch_ingest" in p.usecases:
                routing["sketch_ingest"] = p.node_id
                routing["mobile_hud"] = p.node_id
            if p.role == "sensory_pns" or "pns_sensory_streaming" in p.usecases:
                routing["pns_sensory"] = p.node_id
                routing["ambient_sensing"] = p.node_id
                routing["quick_capture"] = p.node_id

        # Power profile summary
        pwr_entries = []
        for p in online_profiles:
            if p.power_source == "ac_mains":
                pwr_entries.append(f"{p.name}: AC")
            elif p.battery_pct is not None:
                chg_str = "+Chg" if p.charging else ""
                pwr_entries.append(f"{p.name}: {int(p.battery_pct)}%{chg_str}")
        power_summary = " | ".join(pwr_entries)

        return WholeSystemCapability(
            total_nodes=len(profiles),
            online_nodes=len(online_profiles),
            total_cpu_cores=total_cores,
            total_ram_mb=total_ram,
            total_avail_ram_mb=total_avail_ram,
            total_estimated_gflops=total_gflops,
            system_efficiency_index=avg_eff,
            all_usecases=sorted(list(all_usecases)),
            aggregate_tooling=sorted(list(aggregate_tooling)),
            power_profile_summary=power_summary,
            workload_routing_affinity=routing,
            node_profiles=profiles,
        )
