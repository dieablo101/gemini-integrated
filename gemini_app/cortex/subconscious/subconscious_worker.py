"""
sandbox/mind_twin/core/subconscious/subconscious_worker.py

Forked Subconscious Incubation Worker.
Executes background stochastic graph diffusion and cross-domain apophenic collision
scanning across latent, non-conscious hypergraph concepts.
Gated by NoveltyDetector and verified by ConclusiveRealityProbe.
Enhanced with AccretionHearth, Invariant Collision Lens, Resonance Gate,
Thermodynamic Annealing, and Stillness Gate for authentic epiphany emergence.
Hardened against race conditions, empty buckets, and thread faults.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from gemini_app.cortex.hypergraph import Hypergraph, Vertex
from gemini_app.cortex.subconscious.accretion_hearth import AccretionHearth, LatentSoilVault
from gemini_app.cortex.subconscious.annealing_engine import AnnealingDecision, AnnealingEngine
from gemini_app.cortex.subconscious.collision_lens import CollisionLens, CollisionMatrix
from gemini_app.cortex.subconscious.conclusive_probe import ConclusiveRealityProbe, RealityProbeResult
from gemini_app.cortex.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from gemini_app.cortex.subconscious.novelty_detector import NoveltyDetector, NoveltyEvaluation
from gemini_app.cortex.subconscious.resonance_gate import ResonanceGate, ResonanceResult
from gemini_app.cortex.subconscious.seed_packet import ObservationVector, SeedPacket
from gemini_app.cortex.subconscious.stillness_gate import ReceptivityStatus, StillnessGate


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
    - Accretes multi-plane observation vectors in the Accretion Hearth.
    - Projects knots through the Invariant Collision Lens.
    - Filters breakthrough candidates through the 3-stage Resonance Gate.
    - Governs retries, perturbation micro-shifts, and dormancy via AnnealingEngine.
    - Holds delivery until StillnessGate detects cognitive stillness.
    """

    def __init__(
        self,
        graph: Hypergraph,
        novelty_detector: Optional[NoveltyDetector] = None,
        reality_probe: Optional[ConclusiveRealityProbe] = None,
        epiphany_channel: Optional[EpiphanyChannel] = None,
        hearth: Optional[AccretionHearth] = None,
        collision_lens: Optional[CollisionLens] = None,
        resonance_gate: Optional[ResonanceGate] = None,
        annealing_engine: Optional[AnnealingEngine] = None,
        stillness_gate: Optional[StillnessGate] = None,
        target_core_id: int = 1,
    ) -> None:
        self.graph = graph
        self.novelty_detector = novelty_detector if novelty_detector is not None else NoveltyDetector()
        self.reality_probe = reality_probe if reality_probe is not None else ConclusiveRealityProbe()
        self.channel = epiphany_channel if epiphany_channel is not None else EpiphanyChannel()

        # Epiphany Subconscious Upgrades
        self.hearth = hearth if hearth is not None else AccretionHearth()
        self.collision_lens = collision_lens if collision_lens is not None else CollisionLens()
        self.resonance_gate = resonance_gate if resonance_gate is not None else ResonanceGate()
        self.annealing = (
            annealing_engine
            if annealing_engine is not None
            else AnnealingEngine(hearth=self.hearth)
        )
        self.stillness_gate = stillness_gate if stillness_gate is not None else StillnessGate()

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

    def drop_seed(
        self,
        raw_thought: str,
        conscious_context: str = "",
        domain_hints: Optional[List[str]] = None,
    ) -> SeedPacket:
        """
        Conscious Drop exit hatch: hands off an unresolved thought in < 1ms.
        """
        seed = self.hearth.drop_seed(
            raw_thought=raw_thought,
            conscious_context=conscious_context,
            domain_hints=domain_hints,
        )
        self.is_incubating = True
        return seed

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

    def incubate_step(self, t_now: Optional[float] = None) -> Optional[EpiphanyPacket]:
        """Runs a single incubation step across hearth seeds and hypergraph collisions."""
        self.is_incubating = True
        ep = self.run_hearth_incubation_cycle(t_now=t_now)
        if ep:
            return ep
        return self.run_incubation_cycle(t_now=t_now)

    def run_incubation_cycle(
        self,
        t_now: Optional[float] = None,
    ) -> Optional[EpiphanyPacket]:
        """
        Executes one step of subconscious incubation across hypergraph concepts.
        """
        if not self.is_incubating:
            return None

        try:
            self.cycle_count += 1
            now = t_now or time.time()

            # Gather vertices grouped by domain/vtype safely under graph lock
            domain_buckets: Dict[str, List[Vertex]] = {}
            vertices_snapshot = list(self.graph.get_vertices_snapshot().values())

            for v in vertices_snapshot:
                dom = v.attributes.get("topic") or v.vtype
                domain_buckets.setdefault(dom, []).append(v)

            # We need at least two distinct non-empty domains to collide
            valid_domains = [d for d, nodes in domain_buckets.items() if len(nodes) > 0]
            if len(valid_domains) < 2:
                return None

            # Sample two distinct domains
            dom_a, dom_b = random.sample(valid_domains, 2)
            nodes_a = domain_buckets.get(dom_a, [])
            nodes_b = domain_buckets.get(dom_b, [])
            if not nodes_a or not nodes_b:
                return None

            node_a = random.choice(nodes_a)
            node_b = random.choice(nodes_b)

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
        except Exception:
            return None

    def run_hearth_incubation_cycle(
        self,
        t_now: Optional[float] = None,
    ) -> Optional[EpiphanyPacket]:
        """
        Executes one thermodynamic incubation step on dropped seeds in the Accretion Hearth:
        1. Checks for seeds with critical mass (vector count & age).
        2. Projects candidate through Invariant Collision Lens.
        3. Evaluates synthesis via Resonance Gate.
        4. Applies AnnealingEngine decisions (ignite, micro-shift perturbation, or latent soil).
        5. Emits verified epiphany into channel upon ignition.
        """
        now = t_now or time.time()
        ready_seeds = self.hearth.get_ready_seeds(t_now=now)
        if not ready_seeds:
            return None

        seed = ready_seeds[0]
        matrix: CollisionMatrix = self.collision_lens.project(seed)

        # Synthesize candidate hypothesis across planes
        candidate_summary, candidate_mechanism = self._synthesize_hearth_hypothesis(seed, matrix)

        # Evaluate through 3-stage Resonance Gate
        res_result: ResonanceResult = self.resonance_gate.evaluate(
            candidate_summary=candidate_summary,
            candidate_mechanism=candidate_mechanism,
            seed=seed,
        )

        decision: AnnealingDecision = self.annealing.handle_attempt_result(
            seed=seed,
            resonance=res_result,
            t_now=now,
        )

        if decision.action == "ignite":
            packet = EpiphanyPacket(
                packet_id=f"hearth_{seed.seed_id}_{int(now)}",
                spark_name=res_result.spark_name,
                domain_bridge=matrix.planes_collided,
                feasibility_score=res_result.overall_resonance,
                summary=res_result.invariant_summary,
                mechanism=res_result.actionable_mechanism,
                created_at=now,
            )
            self.channel.push(packet)
            self.total_epiphanies_found += 1
            # Remove from hearth upon successful emergence
            with self.hearth._lock:
                self.hearth._hearth.pop(seed.seed_id, None)
            return packet

        return None

    def check_emergence_delivery(
        self,
        event_marker: Optional[str] = None,
        override_idle_seconds: Optional[float] = None,
    ) -> Optional[EpiphanyPacket]:
        """
        Checks StillnessGate: if the cognitive space is receptive and an epiphany is waiting,
        pops and delivers it to consciousness.
        """
        receptivity: ReceptivityStatus = self.stillness_gate.evaluate_receptivity(
            event_marker=event_marker,
            override_idle_seconds=override_idle_seconds,
        )

        if receptivity.is_receptive and not self.channel.is_empty():
            return self.channel.pop()

        return None

    def _synthesize_hearth_hypothesis(
        self,
        seed: SeedPacket,
        matrix: CollisionMatrix,
    ) -> Tuple[str, str]:
        """
        Synthesizes an invariant hypothesis across the collided planes.
        """
        behavioral_labels = [b.label for b in matrix.behavioral_plane]
        artifact_labels = [a.label for a in matrix.artifact_plane]
        relational_labels = [r.label for r in matrix.relational_plane]

        planes_labels = [p[0] for p in [behavioral_labels, artifact_labels, relational_labels] if p]
        if len(planes_labels) >= 2:
            plane_phrase = " and ".join(planes_labels)
        else:
            plane_phrase = "Artifact and Intent"

        summary = (
            f"The invariant coupling {plane_phrase} "
            f"converges the tension in {seed.raw_thought[:32]}."
        )
        mechanism = (
            f"Bind and pipeline {plane_phrase} state changes directly into "
            f"system topology to guarantee system autonomy."
        )
        return summary, mechanism

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
        stream_terms = {"telemetry", "lux", "gyro", "motion", "stream", "sensor", "socket", "sound"}
        engine_terms = {"mesh", "armature", "rigging", "godot", "blender", "shader", "render", "game"}

        words_a = set(text_a.split())
        words_b = set(text_b.split())

        has_stream_a = bool(words_a.intersection(stream_terms))
        has_engine_b = bool(words_b.intersection(engine_terms))

        has_stream_b = bool(words_b.intersection(stream_terms))
        has_engine_a = bool(words_a.intersection(engine_terms))

        if (has_stream_a and has_engine_b) or (has_stream_b and has_engine_a):
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
