"""
Wake-Up Rehydration Engine & Consolidation.
Bridges continuous time gaps between remote API calls.
"""
import time
from typing import Dict, List, Tuple, Optional
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.activation import ActivationEngine, ActivationResult
from sandbox.mind_twin.core.state import CognitiveStateVector, FocusItem

class RehydrationEngine:
    def __init__(self, hypergraph: Hypergraph, activation_engine: ActivationEngine):
        self.hypergraph = hypergraph
        self.activation_engine = activation_engine

    def step_decay(self, state: CognitiveStateVector, now: Optional[float] = None) -> CognitiveStateVector:
        """
        Applies Ebbinghaus power-law decay across the time delta since last turn.
        R(Δt) = (1 + α * Δt)^(-β)
        """
        now = now or time.time()
        delta_t = max(0.0, now - state.timestamp)
        alpha = self.hypergraph.decay_alpha
        beta = self.hypergraph.decay_beta
        retention = (1.0 + alpha * delta_t) ** (-beta)

        decayed_spotlight = []
        for item in state.focus_spotlight:
            new_energy = item.energy * retention
            if new_energy >= self.activation_engine.default_threshold * 0.5:
                decayed_spotlight.append(FocusItem(
                    concept_id=item.concept_id,
                    energy=new_energy,
                    primed_hops=item.primed_hops,
                    last_activated=item.last_activated
                ))

        state.focus_spotlight = decayed_spotlight
        state.timestamp = now
        return state

    def rehydrate_and_prime(
        self,
        previous_state: Optional[CognitiveStateVector],
        new_query: str,
        now: Optional[float] = None
    ) -> Tuple[CognitiveStateVector, ActivationResult]:
        """
        Collides warm residual spotlight with fresh query energy across elapsed time.
        """
        now = now or time.time()
        
        # 1. Decay previous state if present
        seed_boosts: Dict[str, float] = {}
        turn_num = 1
        if previous_state:
            decayed = self.step_decay(previous_state, now=now)
            turn_num = decayed.turn_counter + 1
            for item in decayed.focus_spotlight:
                seed_boosts[item.concept_id] = item.energy * 0.5

        # 2. Extract seeds from new query
        query_seeds = self.activation_engine.match_seeds(new_query)
        for seed_id, s_energy in query_seeds.items():
            seed_boosts[seed_id] = seed_boosts.get(seed_id, 0.0) + s_energy

        # 3. Fire spreading activation dynamics
        profile = self.activation_engine.spread(seed_boosts, query=new_query, t_now=now)

        # 4. Synthesize new cognitive state vector
        new_spotlight = []
        for vid, score, label in profile.get_top_nodes(top_n=15):
            new_spotlight.append(FocusItem(
                concept_id=label,
                energy=score,
                primed_hops=profile.hops_completed,
                last_activated=now
            ))

        # Extract top causal invariants
        invariants = [inv.summary for inv in profile.invariants[:5]]

        new_state = CognitiveStateVector(
            version=1,
            session_id=previous_state.session_id if previous_state else "active_session",
            timestamp=now,
            latent_intent=f"processing_query: {new_query[:30]}",
            focus_spotlight=new_spotlight,
            causal_invariants=invariants,
            turn_counter=turn_num,
            metadata={"elapsed_seconds": (now - previous_state.timestamp) if previous_state else 0.0}
        )

        return new_state, profile

    def consolidate_synapses(self, state: CognitiveStateVector, eta: float = 0.1):
        """
        Neocortical Consolidation ('Dreaming'):
        Strengthens Hebbian connections between co-active concepts in the spotlight.
        """
        active_labels = [item.concept_id for item in state.focus_spotlight if item.energy > 0.5]
        # Map labels back to IDs
        label_to_id = {v.label: vid for vid, v in self.hypergraph.vertices.items()}
        active_ids = [label_to_id[lbl] for lbl in active_labels if lbl in label_to_id]

        for i in range(len(active_ids)):
            for j in range(i + 1, len(active_ids)):
                id_a = active_ids[i]
                id_b = active_ids[j]
                self.hypergraph.apply_hebbian_reinforcement([id_a], [id_b], eta=eta)
