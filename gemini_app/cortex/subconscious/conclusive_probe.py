"""
sandbox/mind_twin/core/subconscious/conclusive_probe.py

Conclusive API Reality Probe.
Acts as the intermediary reality-testing gate for candidate apophenic epiphanies
synthesized during subconscious background incubation.
Prevents ungrounded hallucinations from polluting conscious working memory.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RealityProbeResult:
    """The structured verdict of the reality-testing gate."""
    candidate_id: str
    is_feasible: bool
    confidence: float
    spark_name: str
    domain_bridge: List[str]
    technical_mechanism: str
    actionable_summary: str
    evaluation_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "is_feasible": self.is_feasible,
            "confidence": round(self.confidence, 3),
            "spark_name": self.spark_name,
            "domain_bridge": self.domain_bridge,
            "technical_mechanism": self.technical_mechanism,
            "actionable_summary": self.actionable_summary,
            "evaluation_latency_ms": round(self.evaluation_latency_ms, 2),
        }


class ConclusiveRealityProbe:
    """
    Evaluates candidate cross-domain epiphanies via reality testing.
    Can use a provided LLM completion function or fall back to an internal heuristic evaluator.
    """

    def __init__(
        self,
        confidence_gate: float = 0.78,
        llm_evaluator_fn: Optional[Callable[[str, str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.confidence_gate = confidence_gate
        self.llm_evaluator_fn = llm_evaluator_fn

    def evaluate_candidate(
        self,
        candidate_id: str,
        concept_a: str,
        concept_b: str,
        domain_a: str,
        domain_b: str,
        proposed_bridge: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> RealityProbeResult:
        """
        Executes a reality probe on a candidate connection between two domains.
        """
        t0 = time.perf_counter()

        # If custom LLM callable is attached:
        if self.llm_evaluator_fn is not None:
            try:
                raw_response = self.llm_evaluator_fn(
                    f"{concept_a} <-> {concept_b}",
                    proposed_bridge,
                    context or {},
                )
                latency = (time.perf_counter() - t0) * 1000.0
                return RealityProbeResult(
                    candidate_id=candidate_id,
                    is_feasible=bool(raw_response.get("is_feasible", False)),
                    confidence=float(raw_response.get("confidence", 0.0)),
                    spark_name=str(raw_response.get("spark_name", f"{concept_a} + {concept_b}")),
                    domain_bridge=[domain_a, domain_b],
                    technical_mechanism=str(raw_response.get("technical_mechanism", "")),
                    actionable_summary=str(raw_response.get("actionable_summary", proposed_bridge)),
                    evaluation_latency_ms=latency,
                )
            except Exception as ex:
                # LLM call failed or timed out: fail safe (not feasible)
                latency = (time.perf_counter() - t0) * 1000.0
                return RealityProbeResult(
                    candidate_id=candidate_id,
                    is_feasible=False,
                    confidence=0.0,
                    spark_name=f"{concept_a} + {concept_b}",
                    domain_bridge=[domain_a, domain_b],
                    technical_mechanism=f"Probe invocation error: {ex}",
                    actionable_summary="Rejected due to evaluation error.",
                    evaluation_latency_ms=latency,
                )

        # Built-in deterministic heuristic evaluator:
        # Measures whether the proposed bridge has mutual technical grounding
        # e.g., common data protocol, math representation, or pipeline bridge
        grounding_terms = {
            "socket", "json", "stream", "sensor", "mesh", "shader",
            "telemetry", "ipc", "pipe", "bridge", "vector", "transform",
            "quaternion", "gyro", "frame", "matrix", "vertex", "event",
        }
        words = set(proposed_bridge.lower().split())
        grounded_count = len(words.intersection(grounding_terms))

        # Check for nonsensical / impossible pairings (e.g. physical battery charging a 3D vertex)
        is_grounded = grounded_count >= 1
        confidence = min(0.95, 0.55 + 0.15 * grounded_count) if is_grounded else 0.35
        is_feasible = (confidence >= self.confidence_gate) and (domain_a != domain_b)

        latency = (time.perf_counter() - t0) * 1000.0
        spark_name = f"{concept_a.split(':')[0]} ⇄ {concept_b.split(':')[0]}"

        return RealityProbeResult(
            candidate_id=candidate_id,
            is_feasible=is_feasible,
            confidence=confidence,
            spark_name=spark_name,
            domain_bridge=[domain_a, domain_b],
            technical_mechanism=f"Grounded via {words.intersection(grounding_terms)}",
            actionable_summary=proposed_bridge,
            evaluation_latency_ms=latency,
        )
