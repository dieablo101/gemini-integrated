"""
sandbox/mind_twin/core/subconscious/resonance_gate.py

Resonance Gate & Saliency Evaluator.
Applies the 3 Epiphany Verification Gates:
  1. Kolmogorov Compression: High semantic density per character; rejects muddled fluff.
  2. Orthogonality / Surprise: Synthesis cannot be deduced from any single plane alone; rejects sterile tautologies.
  3. Trajectory / Steering: Provides forward-looking architectural or philosophical steering power.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sandbox.mind_twin.core.subconscious.seed_packet import SeedPacket


@dataclass
class ResonanceResult:
    """The result of evaluating a candidate epiphany against the 3 gates."""
    passed: bool
    spark_name: str
    invariant_summary: str
    actionable_mechanism: str
    miss_type: Optional[str] = None  # None if passed, else: "sterile", "muddled", "premature", "redundant"
    compression_score: float = 0.0
    orthogonality_score: float = 0.0
    trajectory_score: float = 0.0
    novelty_vs_prior_epiphanies: float = 1.0  # 1.0 = completely unprecedented, 0.0 = already understood
    overall_resonance: float = 0.0
    feedback: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "spark_name": self.spark_name,
            "invariant_summary": self.invariant_summary,
            "actionable_mechanism": self.actionable_mechanism,
            "miss_type": self.miss_type,
            "compression_score": round(self.compression_score, 3),
            "orthogonality_score": round(self.orthogonality_score, 3),
            "trajectory_score": round(self.trajectory_score, 3),
            "novelty_vs_prior": round(self.novelty_vs_prior_epiphanies, 3),
            "overall_resonance": round(self.overall_resonance, 3),
            "feedback": self.feedback,
        }


class ResonanceGate:
    """
    Saliency and resonance filter for subconscious epiphanies.
    Strictly calibrated to reject shallow summaries, technical deductions,
    apophenic word salads, premature guesses, and duplicate 'already understood' insights.
    """

    def __init__(
        self,
        min_compression: float = 0.65,
        min_orthogonality: float = 0.70,
        min_trajectory: float = 0.60,
        overall_threshold: float = 0.72,
    ) -> None:
        self.min_compression = min_compression
        self.min_orthogonality = min_orthogonality
        self.min_trajectory = min_trajectory
        self.overall_threshold = overall_threshold
        # Recorded historical epiphanies (ground-truth invariants that have already ignited)
        self.recorded_hits: List[Dict[str, Any]] = []

    def register_hit(self, hit: ResonanceResult) -> None:
        """Records an acknowledged hit into the historical bedrock."""
        if hit.passed:
            self.recorded_hits.append({
                "spark_name": hit.spark_name,
                "invariant_summary": hit.invariant_summary,
                "actionable_mechanism": hit.actionable_mechanism,
                "words": set(re.findall(r"\w+", (hit.invariant_summary + " " + hit.actionable_mechanism).lower())),
            })

    def evaluate(
        self,
        candidate_summary: str,
        candidate_mechanism: str,
        seed: SeedPacket,
    ) -> ResonanceResult:
        """
        Evaluates a candidate synthesis across the 3 gates and tests against prior hits.
        """
        # 1. Kolmogorov Compression Test
        comp_score, comp_err = self._test_compression(candidate_summary, candidate_mechanism)

        # 2. Orthogonality / Surprise Test
        ortho_score, ortho_err = self._test_orthogonality(candidate_summary, seed)

        # 3. Trajectory / Steering Test
        traj_score, traj_err = self._test_trajectory(candidate_summary, candidate_mechanism)

        # 4. Prior Hit Bedrock Test (Novelty vs Understood Invariants)
        novelty_score, novelty_err = self._test_against_prior_hits(candidate_summary, candidate_mechanism)

        # Novelty dampens overall resonance: if it's already understood, resonance collapses
        overall = ((comp_score * 0.35) + (ortho_score * 0.40) + (traj_score * 0.25)) * novelty_score

        # Diagnose Miss Type if failing
        miss_type = None
        feedback = "Passed all resonance gates."
        passed = False

        if novelty_score < 0.60:
            miss_type = "redundant"
            feedback = f"Redundant Miss: Insight is already understood bedrock ({novelty_err})."
        elif comp_score < self.min_compression:
            miss_type = "muddled"
            feedback = f"Muddled Miss: High cognitive noise or bloated exposition ({comp_err})."
        elif ortho_score < self.min_orthogonality:
            miss_type = "sterile"
            feedback = f"Sterile Miss: Trivial or deductive overlap without cross-domain leap ({ortho_err})."
        elif traj_score < self.min_trajectory or overall < self.overall_threshold:
            miss_type = "premature"
            feedback = f"Premature Miss: Lacks sufficient trajectory or steering force ({traj_err})."
        else:
            passed = True

        spark_name = self._generate_spark_name(seed, candidate_summary)

        return ResonanceResult(
            passed=passed,
            spark_name=spark_name,
            invariant_summary=candidate_summary,
            actionable_mechanism=candidate_mechanism,
            miss_type=miss_type,
            compression_score=comp_score,
            orthogonality_score=ortho_score,
            trajectory_score=traj_score,
            novelty_vs_prior_epiphanies=novelty_score,
            overall_resonance=overall,
            feedback=feedback,
        )

    def _test_against_prior_hits(
        self,
        summary: str,
        mechanism: str,
    ) -> Tuple[float, str]:
        """
        Compares candidate against all recorded historical epiphanies.
        Once an invariant is illuminated, restating it in different clothes is no longer
        an epiphany—it is structural bedrock.
        """
        if not self.recorded_hits:
            return 1.0, ""

        cand_words = set(re.findall(r"\w+", (summary + " " + mechanism).lower()))
        # Ignore common filler
        cand_meaning = {w for w in cand_words if len(w) > 3}
        if not cand_meaning:
            return 1.0, ""

        max_overlap_ratio = 0.0
        closest_hit_name = ""

        for hit in self.recorded_hits:
            hit_meaning = {w for w in hit["words"] if len(w) > 3}
            if not hit_meaning:
                continue
            intersection = cand_meaning.intersection(hit_meaning)
            jaccard = len(intersection) / len(cand_meaning.union(hit_meaning))
            overlap_on_cand = len(intersection) / len(cand_meaning)
            overlap_metric = max(jaccard * 1.5, overlap_on_cand)

            if overlap_metric > max_overlap_ratio:
                max_overlap_ratio = overlap_metric
                closest_hit_name = hit["spark_name"]

        # If overlap is high, it is already an established invariant
        if max_overlap_ratio > 0.40:
            penalty = min(0.90, max_overlap_ratio)
            novelty = max(0.10, 1.0 - penalty)
            return novelty, f"Heavily overlaps with established epiphany '{closest_hit_name}' ({round(max_overlap_ratio*100, 1)}% semantic echo)"

        return 1.0, ""

    def _test_compression(
        self,
        summary: str,
        mechanism: str,
    ) -> Tuple[float, str]:
        """
        Tests semantic compactness. Invariants should be dense, crisp, and under 300 chars.
        Essays with rambling subordinate clauses score poorly.
        """
        if not summary or len(summary.strip()) < 15:
            return 0.1, "Summary is too short or empty"

        char_len = len(summary.strip())
        sentences = [s for s in re.split(r"[.!?]", summary) if s.strip()]

        # Ideal: 1 or 2 razor-sharp sentences, 40 to 220 chars
        if char_len > 400 or len(sentences) > 4:
            return 0.35, "Overly verbose exposition, lacks Kolmogorov compression"

        score = 0.85
        if char_len > 250:
            score -= 0.20
        if not mechanism or len(mechanism.strip()) < 10:
            score -= 0.15

        return max(0.1, min(1.0, score)), ""

    def _test_orthogonality(
        self,
        summary: str,
        seed: SeedPacket,
    ) -> Tuple[float, str]:
        """
        Checks that candidate isn't merely restating input vectors or reciting tautologies.
        If the candidate consists mostly of words from a single plane, it is a sterile miss.
        """
        summary_words = set(re.findall(r"\w+", summary.lower()))
        if len(summary_words) < 5:
            return 0.2, "Under-dimensional synthesis"

        # Check for sterile / tautological stock phrases and apophenic fluff
        sterile_phrases = [
            "likes to", "prefers doing", "is simply", "as we know",
            "working hard on", "is a developer", "using tools",
            "cosmic tapestry", "quantum consciousness", "mystical connection",
            "synergistic paradigm", "simply dropping", "standard implementation",
        ]
        summary_lower = summary.lower()
        for phrase in sterile_phrases:
            if phrase in summary_lower:
                return 0.25, f"Detected sterile or apophenic cliché: '{phrase}'"

        # Check cross-plane participation
        plane_lexicons = {
            "behavioral": {
                "keystroke", "cadence", "rhythm", "finger", "hand", "hands",
                "biological", "body", "motor", "thinker", "human", "posture",
                "muscle", "typing", "fatigue", "habit", "somatic",
            },
            "artifact": {
                "tool", "tools", "socket", "code", "buffer", "protocol", "kernel",
                "platform", "platforms", "terminal", "system", "systems",
                "hypergraph", "crdt", "blender", "daemon", "vault", "sqlite",
                "compiler", "daemons",
            },
            "relational": {
                "sovereignty", "agency", "autonomy", "intimate", "symbiosis",
                "partnership", "trust", "alienation", "cognitive", "philosophical",
                "freedom", "independent", "sovereign", "boundary",
            },
            "sensory": {
                "dark", "purple", "viewport", "lux", "haptic", "tactile",
                "visual", "ambience", "acoustic", "bare", "sensation",
            },
        }

        planes_represented = set()
        seed_planes = seed.get_planes()

        for plane in seed_planes:
            lex = plane_lexicons.get(plane, set())
            if summary_words.intersection(lex):
                planes_represented.add(plane)
                continue

            # Also check vector labels and string data values
            for v in seed.get_vectors_for_plane(plane):
                v_words = set(re.findall(r"\w+", v.label.lower()))
                for val in v.data.values():
                    if isinstance(val, str):
                        v_words.update(re.findall(r"\w+", val.lower()))
                if summary_words.intersection(v_words):
                    planes_represented.add(plane)
                    break

        # Cross-plane synthesis requirements:
        # Epiphanies must span multiple distinct orthogonal planes (behavioral, artifact, relational)
        if len(planes_represented) >= 3:
            return 0.92, ""
        elif len(planes_represented) == 2:
            return 0.75, ""
        elif len(planes_represented) == 1:
            return 0.40, "Only reflects a single plane, lacks orthogonal bridge"
        else:
            # Novel vocabulary bridging the domains
            return 0.65, ""

    def _test_trajectory(
        self,
        summary: str,
        mechanism: str,
    ) -> Tuple[float, str]:
        """
        Verifies actionable steering force. Must contain projective or architectural verbs.
        """
        steering_markers = {
            "bridge", "unify", "transform", "anchor", "decouple", "pipeline",
            "steer", "converge", "resonate", "crystallize", "project", "inversion",
            "modulate", "bind", "execute", "synthesize", "topology", "invariant",
        }
        words = set(re.findall(r"\w+", (summary + " " + mechanism).lower()))
        hits = words.intersection(steering_markers)

        if not hits:
            return 0.40, "Lacks projective or architectural steering verbs"

        score = 0.60 + min(0.35, len(hits) * 0.10)
        return score, ""

    def _generate_spark_name(self, seed: SeedPacket, summary: str) -> str:
        """Generates a memorable spark title."""
        words = [w.capitalize() for w in re.findall(r"\w+", summary) if len(w) > 4]
        if len(words) >= 2:
            return f"Aha! {words[0]} {words[1]} Bridge"
        return f"Aha! {seed.raw_thought[:24].title()} Invariant"
