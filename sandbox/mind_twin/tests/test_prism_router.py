"""
Test Suite for Bilateral Prism Router (7-into-1 Somatic Collapser & 3-Tier Gate)
=============================================================================
Verifies:
  1. Sub-2ms somatic collapse latency benchmark (< 100 microseconds typical).
  2. 7-into-1 sensory track fusion into coherent CognitiveIntentFrame.
  3. Deictic anchoring resolution ('this', 'that', 'this error').
  4. Routing decision matrix:
     - SOMATIC_LOCAL: interrupts ('Stop', 'Wait'), active typing cadence, ambient idle.
     - FIREBASE_UPPERMIND: dirty topic notes, state synchronization (zero tokens).
     - API_UPPERMIND: direct typed submissions, spoken queries with pauses, failure triage.
"""

import time
import unittest

from sandbox.mind_twin.core.prism_router import (
    BilateralPrismRouter,
    CursorCoG,
    DeicticAnchor,
    RoutingTier,
    SomaticInterrupt,
    SomaticSensoryTracks,
    TemporalAnchorSlot,
    TerminalExecSlot,
    TopicAnchorSlot,
    TypingStateSlot,
    VoiceStreamSlot,
    WorkspaceDeltaSlot,
)


class TestBilateralPrismRouter(unittest.TestCase):

    def setUp(self):
        self.router = BilateralPrismRouter(speech_pause_threshold_ms=400.0)

    def test_sub_2ms_somatic_collapse_benchmark(self):
        """Collapsing 7 tracks into 1 focal frame must complete well within 2ms."""
        tracks = SomaticSensoryTracks(
            cursor=CursorCoG(file_path="core/lens.py", line_number=42, symbol_under_cursor="execute_frustum"),
            voice=VoiceStreamSlot(utterance="Why is this returning None?", is_speaking=False, pause_duration_ms=600.0),
            terminal=TerminalExecSlot(command="pytest", exit_code=1, stderr_tail="AssertionError: expected not None"),
            typing=TypingStateSlot(buffer_length=0, is_typing=False),
            topic=TopicAnchorSlot(topic_name="collaboration & bilateral autonomy", notes_count=220),
            temporal=TemporalAnchorSlot(turn_id="T66", turn_number=66, momentum_score=0.95),
            workspace=WorkspaceDeltaSlot(modified_files=["core/lens.py"], insertions=12, deletions=4)
        )

        # Run 1,000 iterations to verify sustained latency
        start_t = time.perf_counter()
        iterations = 500
        for _ in range(iterations):
            frame = self.router.collapse_and_route(tracks)
        total_time_ms = (time.perf_counter() - start_t) * 1000.0
        avg_latency_ms = total_time_ms / iterations

        self.assertLess(avg_latency_ms, 2.0, f"Average latency {avg_latency_ms:.3f}ms exceeded 2ms budget")
        self.assertLess(frame.somatic_latency_ms, 2.0)
        self.assertIn("Looking at core/lens.py:42", frame.focal_summary)

    def test_voice_interrupt_routes_to_local_somatic_reflex(self):
        """Spoken 'stop' or 'hold on' must trip local somatic reflex immediately without API call."""
        tracks = SomaticSensoryTracks(
            voice=VoiceStreamSlot(utterance="Hold on, stop!", is_speaking=False),
            cursor=CursorCoG(file_path="main.py", line_number=10)
        )
        frame = self.router.collapse_and_route(tracks)

        self.assertEqual(frame.routing_tier, RoutingTier.SOMATIC_LOCAL)
        self.assertEqual(frame.intent_category, "interrupt")
        self.assertEqual(tracks.voice.detected_interrupt, SomaticInterrupt.HALT)
        self.assertTrue(frame.actionable_intent)
        self.assertIn("[INTERRUPT]", frame.focal_summary)

    def test_deictic_grounding_resolves_symbol_and_error(self):
        """'this function' resolves to cursor symbol, 'this error' resolves to terminal output."""
        tracks = SomaticSensoryTracks(
            cursor=CursorCoG(file_path="router.py", line_number=99, symbol_under_cursor="route_matrix"),
            terminal=TerminalExecSlot(command="make", exit_code=2, stderr_tail="SyntaxError: invalid syntax on line 99"),
            voice=VoiceStreamSlot(
                utterance="Why is this error happening on this function?",
                is_speaking=False,
                pause_duration_ms=600.0
            )
        )
        frame = self.router.collapse_and_route(tracks)

        self.assertEqual(frame.routing_tier, RoutingTier.API_UPPERMIND)
        self.assertEqual(frame.intent_category, "triage")

        # Verify deictic anchors
        raw_refs = [a.raw_reference.lower() for a in frame.deictic_anchors]
        self.assertIn("this error", raw_refs)
        self.assertIn("this function", raw_refs)

        error_anchor = next(a for a in frame.deictic_anchors if a.raw_reference.lower() == "this error")
        self.assertEqual(error_anchor.target_kind, "terminal_error")
        self.assertIn("SyntaxError", error_anchor.resolved_value)

        symbol_anchor = next(a for a in frame.deictic_anchors if a.raw_reference.lower() == "this function")
        self.assertEqual(symbol_anchor.target_kind, "code_symbol")
        self.assertIn("route_matrix", symbol_anchor.resolved_value)

    def test_state_sync_routes_to_firebase_uppermind(self):
        """Dirty topic notes route to Firebase Upper Mind with 0 API tokens."""
        tracks = SomaticSensoryTracks(
            topic=TopicAnchorSlot(topic_name="photon ai engine", notes_count=16, is_dirty=True),
            typing=TypingStateSlot(buffer_length=0, is_typing=False)
        )
        frame = self.router.collapse_and_route(tracks)

        self.assertEqual(frame.routing_tier, RoutingTier.FIREBASE_UPPERMIND)
        self.assertEqual(frame.intent_category, "state_sync")
        self.assertTrue(frame.actionable_intent)
        self.assertIn("Firebase Upper Mind", frame.focal_summary)

    def test_active_typing_without_enter_stays_local_somatic(self):
        """When user is actively typing, stay local to protect typing cadence."""
        tracks = SomaticSensoryTracks(
            typing=TypingStateSlot(buffer_length=24, is_typing=True, submitted=False),
            cursor=CursorCoG(file_path="notes.md", line_number=5)
        )
        frame = self.router.collapse_and_route(tracks)

        self.assertEqual(frame.routing_tier, RoutingTier.SOMATIC_LOCAL)
        self.assertFalse(frame.actionable_intent)
        self.assertEqual(frame.intent_category, "ambient")

    def test_submitted_prompt_routes_to_api_uppermind(self):
        """Pressing Enter on typed query ignites API Upper Mind."""
        tracks = SomaticSensoryTracks(
            typing=TypingStateSlot(buffer_length=48, is_typing=False, submitted=True),
            topic=TopicAnchorSlot(topic_name="collaboration & bilateral autonomy")
        )
        frame = self.router.collapse_and_route(tracks)

        self.assertEqual(frame.routing_tier, RoutingTier.API_UPPERMIND)
        self.assertEqual(frame.intent_category, "query")
        self.assertTrue(frame.actionable_intent)

    def test_casual_speech_without_cadence_pause_stays_local(self):
        """Speech while still mid-sentence does not trigger accidental premature API call."""
        tracks = SomaticSensoryTracks(
            voice=VoiceStreamSlot(
                utterance="Hmm let's see how this works",
                is_speaking=True,
                pause_duration_ms=100.0  # below 400ms threshold
            )
        )
        frame = self.router.collapse_and_route(tracks)

        self.assertEqual(frame.routing_tier, RoutingTier.SOMATIC_LOCAL)
        self.assertFalse(frame.actionable_intent)


if __name__ == "__main__":
    unittest.main()
