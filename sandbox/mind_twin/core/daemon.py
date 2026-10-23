"""
Resilient Cognitive Daemon & Supervisor Architecture.
Guarantees continuous operation with automatic failure detection,
in-process graceful degradation fallback, daemon reboot, and lapse re-synchronization.
"""
import time
import os
from typing import Optional, Tuple, Dict, Any
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.activation import ActivationEngine, ActivationResult
from sandbox.mind_twin.core.state import CognitiveStateVector
from sandbox.mind_twin.core.rehydrate import RehydrationEngine
from sandbox.mind_twin.core.lapse import LapseManager, LapseEvent

class CognitiveDaemon:
    """
    Simulated local background daemon that maintains hypergraph memory,
    executes spreading activation, and maintains atomic checkpoints.
    """
    def __init__(self, checkpoint_path: str, hypergraph: Optional[Hypergraph] = None):
        self.checkpoint_path = checkpoint_path
        self.hypergraph = hypergraph or Hypergraph()
        self.activation_engine = ActivationEngine(self.hypergraph)
        self.rehydration_engine = RehydrationEngine(self.hypergraph, self.activation_engine)
        self.lapse_manager = LapseManager(checkpoint_path)
        self.current_state: Optional[CognitiveStateVector] = None
        self.is_running: bool = False
        self.pid: int = os.getpid()
        self.crashed: bool = False

    def start(self, now: Optional[float] = None) -> LapseEvent:
        """Starts the daemon, reconciling state across any prior lapse."""
        now = now or time.time()
        self.is_running = True
        self.crashed = False
        
        # Post-lapse reconciliation
        self.current_state, lapse_event = self.lapse_manager.reconcile_post_lapse(
            now=now,
            hypergraph=self.hypergraph
        )
        # Flush initial checkpoint
        self.lapse_manager.save_checkpoint(self.current_state, now=now)
        return lapse_event

    def ping(self) -> bool:
        """Health check probe. Returns False if daemon has died or crashed."""
        return self.is_running and not self.crashed

    def simulate_crash(self):
        """Simulates an abrupt process crash (e.g. SIGKILL or unhandled fault)."""
        self.is_running = False
        self.crashed = True

    def process_query(self, query: str, now: Optional[float] = None) -> Tuple[CognitiveStateVector, ActivationResult]:
        """Processes an incoming cognitive query and updates checkpoint."""
        if not self.ping():
            raise RuntimeError("Cognitive daemon is offline or crashed.")
            
        now = now or time.time()
        new_state, profile = self.rehydration_engine.rehydrate_and_prime(
            previous_state=self.current_state,
            new_query=query,
            now=now
        )
        self.rehydration_engine.consolidate_synapses(new_state)
        self.current_state = new_state
        self.lapse_manager.save_checkpoint(new_state, now=now)
        return new_state, profile


class ResilientCognitiveSupervisor:
    """
    Watches the daemon, provides instant local fallback if daemon dies,
    autonomously restarts the daemon, and triggers lapse re-sync.
    """
    def __init__(self, checkpoint_path: str, hypergraph: Optional[Hypergraph] = None):
        self.checkpoint_path = checkpoint_path
        self.hypergraph = hypergraph or Hypergraph()
        self.daemon: Optional[CognitiveDaemon] = None
        self.lapse_manager = LapseManager(checkpoint_path)
        self.reboot_count: int = 0
        self.fallback_invocations: int = 0
        self.last_lapse_event: Optional[LapseEvent] = None
        
        # Start initial daemon
        self.reboot_daemon()

    def reboot_daemon(self, now: Optional[float] = None) -> LapseEvent:
        """Autonomously spins up a fresh daemon instance and runs lapse re-sync."""
        now = now or time.time()
        self.daemon = CognitiveDaemon(self.checkpoint_path, hypergraph=self.hypergraph)
        lapse_event = self.daemon.start(now=now)
        self.reboot_count += 1
        self.last_lapse_event = lapse_event
        return lapse_event

    def execute_query(
        self,
        query: str,
        now: Optional[float] = None
    ) -> Tuple[CognitiveStateVector, bool]:
        """
        Executes query with zero-hang fallback:
        - If daemon alive: runs on daemon.
        - If daemon dead: buffers query, executes instant in-process fallback,
          and triggers autonomous daemon reboot & sync.
        Returns: (state_vector, used_fallback: bool)
        """
        now = now or time.time()
        
        # Check if daemon is active and healthy
        if self.daemon and self.daemon.ping():
            try:
                state, _ = self.daemon.process_query(query, now=now)
                return state, False
            except Exception:
                # Fall through to fallback handler
                pass

        # === DAEMON CRASH / OFFLINE DETECTED ===
        self.fallback_invocations += 1
        
        # 1. Buffer the event so lapse sync can reconcile it
        self.lapse_manager.buffer_event(
            event_type="query",
            payload={"query": query},
            timestamp=now
        )

        # 2. In-Process Ephemeral Direct Fallback (guarantees zero hang / crash)
        last_ckpt = self.lapse_manager.load_checkpoint()
        base_state = last_ckpt[0] if last_ckpt else CognitiveStateVector(session_id="fallback_mode")
        
        fallback_state = CognitiveStateVector(
            session_id=base_state.session_id,
            timestamp=now,
            latent_intent=f"[FALLBACK] processing: {query[:30]}",
            focus_spotlight=list(base_state.focus_spotlight),
            causal_invariants=list(base_state.causal_invariants),
            turn_counter=base_state.turn_counter + 1,
            metadata={"status": "daemon_fallback", "daemon_rebooting": True}
        )

        # 3. Autonomous Watchdog Auto-Reboot and Lapse Sync
        self.reboot_daemon(now=now)

        return fallback_state, True
