"""
test_cognitive_feed_adapter.py - Tests for Theme Shading, Burst Consolidation, and Feed Adapter.

Validates:
1. Multi-message user burst consolidation (3-4 user messages before response).
2. Strict omission of 'turn #' in all user-facing labels.
3. Theme palette shades across all 7 supported themes.
4. Retention of 7-slot working memory across visual /clear calls.
5. 100% schema compatibility with production FeedArea (_all_messages: list[dict]).
6. Safe mode fallback when cortex is unavailable.
7. Double-tap Home semantics (topic horizon vs chat origin).
8. Transient raycast protection and virtual-to-history index translation.
9. Stream-idle gating (injection suppressed during active token generation).
"""

import unittest
import os
import time
from sandbox.mind_twin.core.chat_dissector import (
    ChatDissector, ConcurrentStagingBuffer, ShardDomain, ShardCategory, BufferedTurn
)
from sandbox.mind_twin.core.relational_cortex import RelationalCortex
from sandbox.mind_twin.core.cognitive_card import CognitiveCard, CognitiveIntent, COGNITIVE_BADGES
from sandbox.mind_twin.core.theme_styler import ThemeShadeLens, THEMES
from sandbox.mind_twin.core.cognitive_feed_adapter import CognitiveFeedAdapter


class TestCognitiveFeedAdapter(unittest.TestCase):
    def setUp(self):
        self.test_db = "sandbox/mind_twin/data/test_adapter_temp.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.cortex = RelationalCortex(db_path=self.test_db)
        self.dissector = ChatDissector()
        self.adapter = CognitiveFeedAdapter(self.cortex, theme_name="purple")

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_multi_message_user_burst_consolidation(self):
        """
        Simulates user sending 4 rapid messages in a row before Gemini answers.
        Tests that UserBurstConsolidator unifies them and elevates salience.
        """
        staging = ConcurrentStagingBuffer()
        staging.push("msg_1", 101, "user", "Checking the 3D pipeline coordinate convention.")
        staging.push("msg_2", 102, "user", "Blender armature basis is Z-up.")
        staging.push("msg_3", 103, "user", "Godot 4 requires Y-up handedness.")
        staging.push("msg_4", 104, "user", "Invariant rule: Gram-Schmidt orthogonalization must run every 50 frames.")

        staged_items = staging.get_staged()
        self.assertEqual(len(staged_items), 4)

        # Dissect stream with consolidation
        shards = self.dissector.dissect_staged_stream(staged_items)
        self.assertGreater(len(shards), 0)

        # Verify unified domain and elevated salience
        primary_shard = shards[0]
        self.assertEqual(primary_shard.domain, ShardDomain.PIPELINE_3D)
        self.assertEqual(primary_shard.category, ShardCategory.INVARIANT_RULE)
        self.assertGreaterEqual(primary_shard.salience, 1.6)

        # Check provenance retains all 4 constituent message IDs
        self.assertEqual(len(primary_shard.constituent_turn_ids), 4)
        self.assertIn("msg_1", primary_shard.constituent_turn_ids)
        self.assertIn("msg_4", primary_shard.constituent_turn_ids)

        # Check content contains all parts
        self.assertIn("Z-up", primary_shard.content)
        self.assertIn("Gram-Schmidt", primary_shard.content)

    def test_no_turn_numbers_in_user_facing_labels(self):
        """
        Verifies that user-facing labels and summaries NEVER contain 'turn #' or 'Turn 123'.
        """
        card = CognitiveCard(
            card_id="cog_test",
            intent=CognitiveIntent.REMEMBER_THIS,
            headline="Gram-Schmidt Invariant Standard",
            body="Run basis drift correction every 50 frames.",
            source_context="3D Pipeline Conventions",
            domain="3d_pipeline"
        )
        msg_dict = card.to_feed_message_dict()
        
        # Check badge
        self.assertNotIn("turn", msg_dict["badge"].lower())
        self.assertNotIn("turn", msg_dict["sender"].lower())
        self.assertNotIn("turn", msg_dict["text"].lower())
        self.assertEqual(msg_dict["badge"], "🧠 Gemini • Remember this!")

        # Format turn message
        formatted = self.adapter.format_turn_message("user", "Hello there")
        self.assertEqual(formatted["sender"], "User")
        self.assertNotIn("turn", formatted["sender"].lower())

    def test_theme_shades_across_all_palettes(self):
        """
        Verifies all 7 themes produce valid shades and Rich headers.
        """
        theme_names = ["purple", "blue", "green", "orange", "yellow", "pink", "red"]
        styler = ThemeShadeLens()

        for t in theme_names:
            styler.set_theme(t)
            pal = styler.get_palette()
            self.assertIn("accent", pal)
            self.assertIn("accent_dim", pal)
            self.assertIn("accent_bright", pal)
            self.assertTrue(pal["accent"].startswith("#"))

            header = styler.format_card_header("🧠 Gemini • Remember this!", "accent_bright")
            self.assertIn(pal["accent_bright"], header)

            fold_label = styler.format_fold_label(12, "transient noise")
            self.assertIn("12 prior messages", fold_label)
            self.assertNotIn("turn", fold_label.lower())

    def test_clear_visual_runway_preserves_7_working_memory_slots(self):
        """
        Ensures that /clear clears the runway without wiping the 7 Miller's Law slots.
        """
        slots = [
            "blender_mesh", "godot_pbr", "gram_schmidt",
            "vulkan_sampler", "tailscale_mesh", "pbkdf2_vault", "emacs_dojo"
        ]
        self.adapter.update_working_memory(slots=slots, topic_anchor="3d_pipeline")
        self.assertEqual(len(self.adapter.working_memory_slots), 7)

        # Perform visual clear
        res = self.adapter.clear_visual_runway()
        self.assertEqual(res["action"], "visual_clear")
        self.assertEqual(len(res["working_memory_preserved"]), 7)

        # Working memory slots must STILL be intact in RAM!
        self.assertEqual(len(self.adapter.working_memory_slots), 7)
        self.assertEqual(self.adapter.current_topic_anchor, "3d_pipeline")
        self.assertEqual(self.adapter.working_memory_slots[0]["concept"], "blender_mesh")

    def test_feed_area_schema_compatibility(self):
        """
        Verifies that all message items generated by the adapter match
        the exact schema used by FeedArea (_all_messages: list[dict]).
        """
        # User message
        user_msg = self.adapter.format_turn_message("user", "Testing mesh export")
        self.assertIn("turn_id", user_msg)
        self.assertIn("role", user_msg)
        self.assertIn("text", user_msg)
        self.assertEqual(user_msg["role"], "user")

        # Assistant message
        asst_msg = self.adapter.format_turn_message("assistant", "Export completed")
        self.assertEqual(asst_msg["role"], "model")

        # Cognitive interlude card
        card = CognitiveCard(
            card_id="cog_99",
            intent=CognitiveIntent.CONSIDER_THIS,
            headline="Sampler Limit Check",
            body="Godot 4 Mobile renderer is limited to 16 texture samplers.",
            source_context="Godot PBR Shader",
            domain="3d_pipeline"
        )
        card_dict = card.to_feed_message_dict()
        # FeedArea expects at minimum turn_id, role, text
        self.assertIn("turn_id", card_dict)
        self.assertIn("role", card_dict)
        self.assertIn("text", card_dict)
        self.assertTrue(card_dict.get("is_memory"))
        self.assertTrue(card_dict.get("is_transient"))
        self.assertFalse(card_dict.get("can_fork"))

    def test_safe_mode_fallback(self):
        """
        Verifies that if cortex is None, adapter operates gracefully in safe mode
        without raising exceptions.
        """
        safe_adapter = CognitiveFeedAdapter(cortex=None)
        self.assertTrue(safe_adapter.safe_mode)

        # Evaluation cleanly returns None
        result = safe_adapter.evaluate_cognitive_interlude("Check rule", [])
        self.assertIsNone(result)

        # Working memory updates safely
        safe_adapter.update_working_memory(["safe_slot"])
        self.assertEqual(len(safe_adapter.working_memory_slots), 1)

        # Formatting works normally
        msg = safe_adapter.format_turn_message("user", "Hello")
        self.assertEqual(msg["sender"], "User")

    def test_double_tap_home_semantics(self):
        """
        Verifies that 1st Home press jumps to topic start and 2nd press within 1.5s
        jumps to chat origin (turn 0).
        """
        messages = [{"turn_id": f"t_{i}", "role": "user", "text": "msg"} for i in range(50)]
        self.adapter.topic_start_index = 35

        # 1st press: topic horizon
        idx1, toast1 = self.adapter.handle_home_key(messages, current_time=100.0)
        self.assertEqual(idx1, 35)
        self.assertIn("Topic Start", toast1)

        # 2nd press within 1.5s (e.g. 0.4s later): chat origin
        idx2, toast2 = self.adapter.handle_home_key(messages, current_time=100.4)
        self.assertEqual(idx2, 0)
        self.assertIn("Chat Origin", toast2)

        # 3rd press after 3.0s: back to 1st tap behavior
        idx3, toast3 = self.adapter.handle_home_key(messages, current_time=104.0)
        self.assertEqual(idx3, 35)
        self.assertIn("Topic Start", toast3)

    def test_transient_message_filtering_and_index_mapping(self):
        """
        Verifies that transient cognitive interludes are correctly flagged
        and translated back to pure ground-truth history indices.
        """
        feed = [
            {"turn_id": "m0", "role": "user", "text": "Hello"},
            {"turn_id": "m1", "role": "model", "text": "Hi"},
            {"turn_id": "cog1", "role": "model", "text": "Remember rule", "is_memory": True, "is_transient": True},
            {"turn_id": "m2", "role": "user", "text": "Let's build shaders"},
            {"turn_id": "cog2", "role": "model", "text": "Consider samplers", "card_type": "cognitive_interlude"},
            {"turn_id": "m3", "role": "model", "text": "Shader compiled"},
        ]

        # Transient detection
        self.assertFalse(CognitiveFeedAdapter.is_transient_message(feed[0]))
        self.assertFalse(CognitiveFeedAdapter.is_transient_message(feed[1]))
        self.assertTrue(CognitiveFeedAdapter.is_transient_message(feed[2]))
        self.assertFalse(CognitiveFeedAdapter.is_transient_message(feed[3]))
        self.assertTrue(CognitiveFeedAdapter.is_transient_message(feed[4]))
        self.assertFalse(CognitiveFeedAdapter.is_transient_message(feed[5]))

        # Mapping: feed[0] -> history[0]
        self.assertEqual(self.adapter.feed_index_to_history_index(feed, 0), 0)
        # feed[1] -> history[1]
        self.assertEqual(self.adapter.feed_index_to_history_index(feed, 1), 1)
        # feed[2] (transient) -> history[1] (snaps to preceding ground-truth)
        self.assertEqual(self.adapter.feed_index_to_history_index(feed, 2), 1)
        # feed[3] (m2) -> history[2]
        self.assertEqual(self.adapter.feed_index_to_history_index(feed, 3), 2)
        # feed[5] (m3) -> history[3]
        self.assertEqual(self.adapter.feed_index_to_history_index(feed, 5), 3)

    def test_stream_idle_gating(self):
        """
        Ensures cognitive cards are NOT injected while Gemini is actively streaming tokens.
        """
        # Inject an invariant rule into cortex
        staging = ConcurrentStagingBuffer()
        staging.push("msg_rule", 1, "user", "Invariant rule: Gram-Schmidt basis drift must be corrected every 50 frames.")
        shards = self.dissector.dissect_staged_stream(staging.drain_for_valuation())
        self.cortex.batch_insert_shards(shards)

        # With streaming ACTIVE: evaluate returns None
        self.adapter.set_streaming(True)
        res_streaming = self.adapter.evaluate_cognitive_interlude("Gram-Schmidt basis", [])
        self.assertIsNone(res_streaming)

        # With streaming IDLE: evaluate succeeds
        self.adapter.set_streaming(False)
        res_idle = self.adapter.evaluate_cognitive_interlude("Gram-Schmidt basis", [])
        self.assertIsNotNone(res_idle)
        self.assertEqual(res_idle["badge"], "🧠 Gemini • Remember this!")


if __name__ == "__main__":
    unittest.main()
