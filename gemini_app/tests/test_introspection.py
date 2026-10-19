"""Unit tests for console introspection and UI interaction engine."""

import unittest
from unittest.mock import MagicMock

from gemini_app.config import THEMES
from gemini_app.introspection import (
    apply_accent_talk,
    format_introspection_summary,
    get_console_state,
    get_tier_1_visual,
    get_tier_2_runtime,
    get_tier_3_workflow,
    start_mind_animation,
)


class DummyWidget:
    def __init__(self, wid="feed"):
        self.id = wid
        self.styles = MagicMock()
        self.styles.border = None


class DummyApp:
    def __init__(self):
        self.active_palette_name = "blue"
        self.accent_color = "#3399ff"
        self.size = MagicMock(width=120, height=35)
        self.screen = MagicMock()
        self.screen.__class__.__name__ = "ChatApp"
        self.focused = DummyWidget("input")
        self.notes_open = False
        self.history = [{"role": "user", "text": "turn 1"}]
        self.current_chat_id = "test_chat_1"
        self.current_chat_parent_id = None
        self._request_phase = "idle"
        self._request_details = ""
        self.current_focused_turn_id = "t1"
        self.current_chat_center_marker = "t1:0"
        self.active_task_title = "Testing introspection"
        self.current_gemini_state = "Technical direction"
        self.current_user_state = "Exploring introspection"
        self.current_tree_state = ["T1"]
        self.current_tree_content = "└── Test"
        self.gemini_notes = "Working notes"
        self.notes_manager = MagicMock()
        self.notes_manager.active_topic = "introspection"
        self.notes_manager.get_all_topics.return_value = ["general", "introspection"]
        self.notes_manager.notes = []

        self.timers = []
        self.notifications = []
        self._widgets = {
            "#feed": [DummyWidget("feed")],
            "#input": [DummyWidget("input")],
        }

    def get_effective_working_dir(self):
        return "/opt/gemini"

    def query(self, selector):
        return self._widgets.get(selector, [])

    def set_timer(self, delay, callback):
        self.timers.append((delay, callback))

    def set_theme(self, palette, notify_user=True):
        self.active_palette_name = palette
        return True

    def notify(self, msg, **kwargs):
        self.notifications.append((msg, kwargs))


class TestIntrospection(unittest.TestCase):
    def setUp(self):
        self.app = DummyApp()

    def test_get_tier_1_visual(self):
        t1 = get_tier_1_visual(self.app)
        self.assertEqual(t1["tier"], 1)
        self.assertEqual(t1["active_theme"], "blue")
        self.assertEqual(t1["accent_color"], THEMES["blue"]["accent"])
        self.assertEqual(t1["viewport"]["width"], 120)
        self.assertEqual(t1["viewport"]["height"], 35)
        self.assertFalse(t1["viewport"]["is_mobile"])
        self.assertEqual(t1["views"]["focused_widget_id"], "input")

    def test_get_tier_2_runtime(self):
        t2 = get_tier_2_runtime(self.app)
        self.assertEqual(t2["tier"], 2)
        self.assertEqual(t2["working_dir"], "/opt/gemini")
        self.assertEqual(t2["chat_id"], "test_chat_1")
        self.assertEqual(t2["turns_count"], 1)
        self.assertEqual(t2["request_phase"], "idle")

    def test_get_tier_3_workflow(self):
        t3 = get_tier_3_workflow(self.app)
        self.assertEqual(t3["tier"], 3)
        self.assertEqual(t3["active_task_title"], "Testing introspection")
        self.assertEqual(t3["gemini_mind_state"], "Technical direction")
        self.assertEqual(t3["active_topic"], "introspection")

    def test_get_console_state_all(self):
        state = get_console_state(self.app, tier="all")
        self.assertEqual(state["status"], "success")
        self.assertIn("tier_1_visual", state)
        self.assertIn("tier_2_runtime", state)
        self.assertIn("tier_3_workflow", state)

    def test_get_console_state_tier_filter(self):
        v_state = get_console_state(self.app, tier="visual")
        self.assertEqual(v_state["status"], "success")
        self.assertIn("tier_1", v_state)
        self.assertNotIn("tier_2_runtime", v_state)

        r_state = get_console_state(self.app, tier="runtime")
        self.assertIn("tier_2", r_state)

        w_state = get_console_state(self.app, tier="workflow")
        self.assertIn("tier_3", w_state)

    def test_format_introspection_summary(self):
        summary = format_introspection_summary(self.app)
        self.assertIn("### BILATERAL CONSOLE INTROSPECTION", summary)
        self.assertIn("Visual Layer (Tier 1): Theme: 'blue'", summary)
        self.assertIn("Runtime Layer (Tier 2): CWD: /opt/gemini", summary)
        self.assertIn("Cognitive Layer (Tier 3): Task: 'Testing introspection'", summary)

    def test_apply_accent_talk_invalid_palette(self):
        res = apply_accent_talk(self.app, target="feed", palette="neon_nonexistent")
        self.assertEqual(res["status"], "error")
        self.assertIn("Invalid palette", res["message"])

    def test_apply_accent_talk_all_permanent(self):
        res = apply_accent_talk(self.app, target="all", palette="purple", duration=0.0)
        self.assertEqual(res["status"], "success")
        self.assertEqual(self.app.active_palette_name, "purple")

    def test_apply_accent_talk_all_pulse(self):
        res = apply_accent_talk(self.app, target="all", palette="pink", duration=2.0)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["action"], "theme_pulse")
        self.assertEqual(self.app.active_palette_name, "pink")
        self.assertEqual(len(self.app.timers), 1)
        # Execute reset timer callback
        self.app.timers[0][1]()
        self.assertEqual(self.app.active_palette_name, "blue")

    def test_apply_accent_talk_targeted_widget(self):
        res = apply_accent_talk(self.app, target="feed", palette="green", duration=3.0)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["target"], "feed")
        feed_widget = self.app._widgets["#feed"][0]
        self.assertEqual(feed_widget.styles.border, ("round", THEMES["green"]["accent"]))
        self.assertEqual(len(self.app.timers), 1)

    def test_start_mind_animation(self):
        res = start_mind_animation(self.app, effect="synapse", palette="yellow", duration=5.0, message="Synapse firing")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["effect"], "synapse")
        self.assertEqual(res["palette"], "yellow")
        self.assertEqual(self.app._active_mind_animation["effect"], "synapse")
        self.assertEqual(self.app._active_mind_animation["palette"], "yellow")
        self.assertEqual(self.app._active_mind_animation["message"], "Synapse firing")

    def test_start_mind_animation_fallback_effect(self):
        res = start_mind_animation(self.app, effect="unknown_effect")
        self.assertEqual(res["effect"], "sparkle")


if __name__ == "__main__":
    unittest.main()
