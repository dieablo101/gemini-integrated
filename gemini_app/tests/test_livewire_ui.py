"""Unit tests for LiveWire Modals and Slash Commands."""

import os
import sys
import unittest
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Label

from gemini_app.ui.modals.live_wire_modal import (
    LivewireSessionInput,
    LiveWireModal,
)
from gemini_app.ui.modals.live_wire_settings import LiveWireSettingsModal
from live_wire_engine import (
    LiveWireSessionManager,
    validate_session_name,
    cancel_and_scrub_session,
    STUDIES_ROOT,
    PRODUCTION_ROOT
)


class TestLiveWireInputApp(App):
    def __init__(self, mode: str = "studies"):
        super().__init__()
        self.mode = mode
        self.input_widget = None

    def compose(self) -> ComposeResult:
        self.input_widget = LivewireSessionInput(
            mode_getter=lambda: self.mode,
            id="session_input"
        )
        yield self.input_widget


class TestLiveWireModalApp(App):
    def compose(self) -> ComposeResult:
        yield Label("Base Screen")


class TestLiveWireUI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mgr = LiveWireSessionManager.get_instance()
        self.mgr.current_session_name = ""
        self.mgr.is_recording = False
        self.mgr.is_connected = False

    def test_session_name_validation_rules(self):
        # 1. Reject without subfolder
        ok, err, f, fn = validate_session_name("pirate")
        self.assertFalse(ok)
        self.assertIn("must add subfolder", err)

        # 2. Reject empty
        ok, err, f, fn = validate_session_name("")
        self.assertFalse(ok)
        self.assertIn("please name your livewire session", err)

        # 3. Accept valid folder/filename
        ok, err, f, fn = validate_session_name("creatures/alien_stalker")
        self.assertTrue(ok)
        self.assertEqual(f, "creatures")
        self.assertEqual(fn, "alien_stalker")

    async def test_livewire_session_input_tab_autocomplete(self):
        test_folder = STUDIES_ROOT / "test_alien"
        test_folder.mkdir(parents=True, exist_ok=True)
        try:
            app = TestLiveWireInputApp(mode="studies")
            async with app.run_test() as pilot:
                inp = app.query_one("#session_input", LivewireSessionInput)
                inp.value = "test_al"
                await pilot.press("tab")
                self.assertEqual(inp.value, "test_alien/")
        finally:
            if test_folder.exists():
                test_folder.rmdir()

    async def test_livewire_modals_lifecycle_in_app(self):
        app = TestLiveWireModalApp()
        async with app.run_test() as pilot:
            # Push Settings Modal
            settings_modal = LiveWireSettingsModal()
            await app.push_screen(settings_modal)
            self.assertIsInstance(app.screen, LiveWireSettingsModal)
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, LiveWireSettingsModal)

            # Push LiveWire Cockpit Modal
            cockpit = LiveWireModal()
            await app.push_screen(cockpit)
            self.assertIsInstance(app.screen, LiveWireModal)

            # Check subfolder gate
            val_ok, err, _, _ = cockpit._check_name_and_collision("nakedfilename")
            self.assertFalse(val_ok)
            self.assertIn("must add subfolder", err)

            # Dismiss cockpit
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, LiveWireModal)


if __name__ == "__main__":
    unittest.main()
