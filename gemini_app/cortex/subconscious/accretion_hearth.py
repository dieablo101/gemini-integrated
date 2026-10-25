"""
sandbox/mind_twin/core/subconscious/accretion_hearth.py

Accretion Hearth & Latent Soil Vault.
Core 1 multi-vector accretion hearth that holds dropped seeds, monitors the bilateral
environment, and accretes observation vectors until critical mass is reached.
Seeds that exhaust active retries without resonance are placed in the Latent Soil Vault,
consuming zero CPU and awaiting future real-world catalysts.
"""

from __future__ import annotations

import collections
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from gemini_app.cortex.subconscious.seed_packet import ObservationVector, SeedPacket


class LatentSoilVault:
    """
    Underground dormant vault for seeds that did not ignite during active annealing.
    Zero token cost, zero CPU cycles. Indexed by semantic tokens and plane signatures
    for catalyst-triggered re-awakening.
    """

    def __init__(self) -> None:
        self._dormant_seeds: Dict[str, SeedPacket] = {}
        self._token_index: Dict[str, Set[str]] = collections.defaultdict(set)
        self._lock = threading.Lock()

    def deposit(self, seed: SeedPacket) -> None:
        """Deposits a seed into dormant soil."""
        with self._lock:
            seed.status = "dormant"
            seed.dormant_at = time.time()
            self._dormant_seeds[seed.seed_id] = seed

            # Index keywords for catalyst matching
            tokens = self._extract_tokens(seed.raw_thought)
            for v in seed.vectors:
                tokens.update(self._extract_tokens(v.label))
            for tok in tokens:
                self._token_index[tok.lower()].add(seed.seed_id)

    def probe_catalyst(
        self,
        stimulus_text: str,
        threshold_match: int = 2,
    ) -> List[SeedPacket]:
        """
        Scans dormant seeds against a fresh real-world stimulus (e.g. commit message, C function, offhand note).
        If matching tokens meet threshold, awakens the candidate seed.
        """
        stimulus_tokens = self._extract_tokens(stimulus_text)
        awakened: List[SeedPacket] = []

        with self._lock:
            hit_counts: Dict[str, int] = collections.defaultdict(int)
            for tok in stimulus_tokens:
                lower = tok.lower()
                if lower in self._token_index:
                    for sid in self._token_index[lower]:
                        hit_counts[sid] += 1

            for sid, count in hit_counts.items():
                if count >= threshold_match and sid in self._dormant_seeds:
                    seed = self._dormant_seeds[sid]
                    awakened.append(seed)

        return awakened

    def awaken(self, seed_id: str) -> Optional[SeedPacket]:
        """Removes a seed from latent soil to be re-ignited in the hearth."""
        with self._lock:
            seed = self._dormant_seeds.pop(seed_id, None)
            if not seed:
                return None
            # Clean up index
            for tok_set in self._token_index.values():
                tok_set.discard(seed_id)
            seed.status = "incubating"
            seed.dormant_at = None
            seed.attempts = 1  # Reset attempts with fresh catalyst
            return seed

    def size(self) -> int:
        with self._lock:
            return len(self._dormant_seeds)

    def list_dormant(self) -> List[SeedPacket]:
        with self._lock:
            return list(self._dormant_seeds.values())

    @staticmethod
    def _extract_tokens(text: str) -> Set[str]:
        words = text.replace("_", " ").replace("-", " ").replace(".", " ").split()
        return {w.strip().lower() for w in words if len(w.strip()) > 3}


class AccretionHearth:
    """
    Subconscious mass accretion hearth.
    - Receives drops from conscious mind in < 1ms.
    - Collects passive environmental vectors across planes.
    - Evaluates mass readiness (vector count >= 3, incubation duration >= threshold).
    - Transfers over-annealed seeds to LatentSoilVault.
    """

    def __init__(
        self,
        soil_vault: Optional[LatentSoilVault] = None,
        min_vectors_to_ignite: int = 3,
        min_incubation_seconds: float = 0.0,  # 0 for testing, configurable for prod
    ) -> None:
        self.soil_vault = soil_vault if soil_vault is not None else LatentSoilVault()
        self.min_vectors_to_ignite = min_vectors_to_ignite
        self.min_incubation_seconds = min_incubation_seconds
        self._hearth: Dict[str, SeedPacket] = {}
        self._lock = threading.Lock()
        self.total_dropped: int = 0
        self.total_ignited: int = 0

    def drop_seed(
        self,
        raw_thought: str,
        conscious_context: str = "",
        domain_hints: Optional[List[str]] = None,
    ) -> SeedPacket:
        """
        Asynchronous drop hatch: hands off a thought into the hearth instantaneously.
        """
        seed = SeedPacket.create(
            raw_thought=raw_thought,
            conscious_context=conscious_context,
            domain_hints=domain_hints,
        )
        seed.status = "incubating"
        with self._lock:
            self._hearth[seed.seed_id] = seed
            self.total_dropped += 1
        return seed

    def attach_vector(self, seed_id: str, vector: ObservationVector) -> bool:
        """Attaches an observation vector to an incubating seed."""
        with self._lock:
            seed = self._hearth.get(seed_id)
            if not seed:
                return False
            seed.attach_vector(vector)
            return True

    def accrete_environmental_telemetry(
        self,
        cadence_wpm: float = 0.0,
        idle_duration: float = 0.0,
        active_branch: str = "",
        recent_commit: str = "",
    ) -> int:
        """
        Passively accretes telemetry observation fibers to all incubating seeds in the hearth.
        """
        with self._lock:
            attached_count = 0
            now = time.time()
            for seed in self._hearth.values():
                if seed.status != "incubating":
                    continue

                if cadence_wpm > 0 or idle_duration > 0:
                    vec = ObservationVector(
                        vector_id=f"vec_cadence_{uuid.uuid4().hex[:6]}",
                        plane="behavioral",
                        label="Somatic Typing Rhythm",
                        data={"wpm": cadence_wpm, "idle_sec": idle_duration},
                        weight=0.8,
                        timestamp=now,
                    )
                    seed.attach_vector(vec)
                    attached_count += 1

                if active_branch or recent_commit:
                    vec = ObservationVector(
                        vector_id=f"vec_git_{uuid.uuid4().hex[:6]}",
                        plane="artifact",
                        label="Codebase Artifact State",
                        data={"branch": active_branch, "commit": recent_commit},
                        weight=0.9,
                        timestamp=now,
                    )
                    seed.attach_vector(vec)
                    attached_count += 1

            return attached_count

    def get_ready_seeds(self, t_now: Optional[float] = None) -> List[SeedPacket]:
        """
        Returns seeds that have accreted enough distinct observation vectors and age.
        """
        now = t_now or time.time()
        ready = []
        with self._lock:
            for seed in self._hearth.values():
                if seed.status != "incubating":
                    continue
                age = now - seed.created_at
                planes = seed.get_planes()
                if len(seed.vectors) >= self.min_vectors_to_ignite and age >= self.min_incubation_seconds:
                    # Require at least 2 distinct planes for true cross-domain collision
                    if len(planes) >= 2 or len(seed.domain_hints) >= 2:
                        ready.append(seed)
        return ready

    def move_to_soil(self, seed_id: str) -> bool:
        """Moves a seed that exhausted retries from active hearth to latent soil."""
        with self._lock:
            seed = self._hearth.pop(seed_id, None)
            if not seed:
                return False
            self.soil_vault.deposit(seed)
            return True

    def check_catalyst_awakening(self, stimulus_text: str) -> List[SeedPacket]:
        """
        Probes latent soil with a fresh stimulus; if awakened, re-enters active hearth.
        """
        awakened_seeds = self.soil_vault.probe_catalyst(stimulus_text)
        re_added: List[SeedPacket] = []
        for seed in awakened_seeds:
            restored = self.soil_vault.awaken(seed.seed_id)
            if restored:
                with self._lock:
                    self._hearth[restored.seed_id] = restored
                re_added.append(restored)
        return re_added

    def size(self) -> int:
        with self._lock:
            return len(self._hearth)

    def get_seed(self, seed_id: str) -> Optional[SeedPacket]:
        with self._lock:
            return self._hearth.get(seed_id)
