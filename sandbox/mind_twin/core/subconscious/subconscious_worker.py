"""
sandbox/mind_twin/core/subconscious/subconscious_worker.py

Forked Subconscious Incubation Worker.
Executes background stochastic graph diffusion and cross-domain apophenic collision
scanning across latent, non-conscious hypergraph concepts.
Gated by NoveltyDetector and verified by ConclusiveRealityProbe.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex
from sandbox.mind_twin.core.subconscious.conclusive_probe import ConclusiveRealityProbe, RealityProbeResult
from sandbox.mind_twin.core.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from sandbox.mind_twin.core.subconscious.novelty_detector import NoveltyDetector, NoveltyEvaluation


@dataclass
class IncubationCluster:
    """A candidate apophenic bridge between disparate domains."""
    cluster_id: str
    vertex_a: Vertex
    vertex_b: Vertex
    domain_a: str
    domain_b: str
    resonance_score: float
    hypothesis_summary: str


class SubconsciousWorker:
    """
    Subconscious incubation engine.
    - Evaluates task novelty: stays dormant on familiar routine tasks.
    - Runs stochastic graph walks over latent vertices when novel problems are detected.
    - Probes reality testing via ConclusiveRealityProbe.
    - Emits verified epiphanies into EpiphanyChannel.
    """

    def __init__(
        self,
        graph: Hypergraph,
        novelty_detector: Optional[NoveltyDetector] = None,
        reality_probe: Optional[ConclusiveRealityProbe] = None,
        epiphany_channel: Optional[EpiphanyChannel] = None,
        target_core_id: int = 1,
    ) -> None:
        self.graph = graph
        self.novelty_detector = novelty_detector or NoveltyDetector()
        self.reality_probe = reality_probe or ConclusiveRealityProbe()
        self.channel = epiphany_channel or EpiphanyChannel()
        self.target_core_id = target_core_id
        self.is_incubating: bool = False
        self.cycle_count: int = 0
        self.total_epiphanies_found: int = 0

    def pin_to_core(self) -> bool:
        """
        Attempts to pin background worker to Core 1 (or configured CPU core).
        Gracefully handles environments without sched_setaffinity.
        """
        if hasattr(os, "sched_setaffinity"):
            try:
                os.sched_setaffinity(0, {self.target_core_id})
                return True
            except Exception:
                return False
        return False

    def check_and_ignite(
        self,
        task_prompt: str,
        active_topic: str = "",
        context_keywords: Optional[List[str]] = None,
    ) -> Tuple[bool, NoveltyEvaluation]:
        """
        Gating check: Checks novelty. If novel, ignites incubation; otherwise idles.
        """
        eval_result = self.novelty_detector.evaluate(
            task_prompt=task_prompt,
            active_topic=active_topic,
            context_keywords=context_keywords,
        )
        self.is_incubating = eval_result.should_fire_incubation
        return self.is_incubating, eval_result

    def run_incubation_cycle(
        self,
        t_now: Optional[float] = None,
    ) -> Optional[EpiphanyPacket]:
        """
        Executes one step of subconscious incubation:
        1. Checks if worker is active.
        2. Selects latent vertices from disparate domains.
        3. Scans for structural resonance or apophenic analogies.
        4. Runs reality probe.
        5. Pushes to channel if approved.
        """
        if not self.is_incubating:
            return None

        self.cycle_count += 1
        now = t_now or time.time()

        # Gather vertices grouped by domain/vtype
        domain_buckets: Dict[str, List[Vertex]] = {}
        for vid, v in self.graph.vertices.items():
            dom = v.attributes.get("topic") or v.vtype
            domain_buckets.setdefault(dom, []).append(v)

        # We need at least two distinct domains to collide
        distinct_domains = list(domain_buckets.keys())
        if len(distinct_domains) < 2:
            return None

        # Sample two distinct domains
        dom_a, dom_b = random.sample(distinct_domains, 2)
        node_a = random.choice(domain_buckets[dom_a])
        node_b = random.choice(domain_buckets[dom_b])

        # Evaluate cross-domain collision hypothesis
        cluster = self._synthesize_bridge(node_a, node_b, dom_a, dom_b)
        if not cluster:
            return None

        # Reality test via probe
        probe_res: RealityProbeResult = self.reality_probe.evaluate_candidate(
            candidate_id=cluster.cluster_id,
            concept_a=node_a.label,
            concept_b=node_b.label,
            domain_a=dom_a,
            domain_b=dom_b,
            proposed_bridge=cluster.hypothesis_summary,
        )

        if probe_res.is_feasible and probe_res.confidence >= self.reality_probe.confidence_gate:
            packet = EpiphanyPacket(
                packet_id=cluster.cluster_id,
                spark_name=probe_res.spark_name,
                domain_bridge=[dom_a, dom_b],
                feasibility_score=probe_res.confidence,
                summary=probe_res.actionable_summary,
                mechanism=probe_res.technical_mechanism,
                created_at=now,
            )
            self.channel.push(packet)
            self.total_epiphanies_found += 1
            return packet

        return None

    def _synthesize_bridge(
        self,
        node_a: Vertex,
        node_b: Vertex,
        dom_a: str,
        dom_b: str,
    ) -> Optional[IncubationCluster]:
        """
        Computes resonance between two candidate vertices across domains.
        """
        text_a = f"{node_a.label} {node_a.attributes.get('full_content', '')}".lower()
        text_b = f"{node_b.label} {node_b.attributes.get('full_content', '')}".lower()

        # Look for complementary concepts:
        # e.g., A provides stream/telemetry/data, B consumes physics/geometry/motion
        stream_terms = {"telemetry", "lux", "gyro", "motion", "stream", "sensor", "socket", "sound"}
        engine_terms = {"mesh", "armature", "rigging", "godot", "blender", "shader", "render", "game"}

        words_a = set(text_a.split())
        words_b = set(text_b.split())

        has_stream_a = bool(words_a.intersection(stream_terms))
        has_engine_b = bool(words_b.intersection(engine_terms))

        has_stream_b = bool(words_b.intersection(stream_terms))
        has_engine_a = bool(words_a.intersection(engine_terms))

        if (has_stream_a and has_engine_b) or (has_stream_b and has_engine_a):
            # High resonance bridge!
            cid = f"cluster_{self.cycle_count}_{int(time.time() * 1000) % 10000}"
            hypothesis = (
                f"Bridge {node_a.label} with {node_b.label} via real-time sensory stream "
                f"into transform matrix pipeline."
            )
            return IncubationCluster(
                cluster_id=cid,
                vertex_a=node_a,
                vertex_b=node_b,
                domain_a=dom_a,
                domain_b=dom_b,
                resonance_score=0.88,
                hypothesis_summary=hypothesis,
            )

        # General structural analogy: attribute key overlap
        shared_keys = set(node_a.attributes.keys()).intersection(node_b.attributes.keys())
        if len(shared_keys) >= 2:
            cid = f"cluster_{self.cycle_count}_{int(time.time() * 1000) % 10000}"
            hypothesis = f"Analogous state representation across {dom_a} and {dom_b} via attributes {shared_keys}."
            return IncubationCluster(
                cluster_id=cid,
                vertex_a=node_a,
                vertex_b=node_b,
                domain_a=dom_a,
                domain_b=dom_b,
                resonance_score=0.72,
                hypothesis_summary=hypothesis,
            )

        return None
