"""
Unit tests for Phone Sensory Integration (PNS) in Sandbox.
Verifies telemetry harvesting, synthesis into somatic anchors, and socket pipeline.
"""
import json
import time
import unittest
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.pns_sensor import (
    PhoneSensoryTelemetry,
    PhoneSensorySynthesizer,
    PNSSensoryReceiver,
)
from sandbox.mind_twin.core.termux_probe import transmit_to_mothership


class TestPhoneSensoryIntegration(unittest.TestCase):
    def setUp(self):
        self.hg = Hypergraph(decay_alpha=0.01, decay_beta=0.5)
        self.synth = PhoneSensorySynthesizer(self.hg)

    def test_sensory_anchors_initialization(self):
        """Verifies initial somatic concepts are registered in hypergraph."""
        labels = [v.label for v in self.hg.vertices.values()]
        self.assertIn("somatic:circadian_night", labels)
        self.assertIn("somatic:circadian_day", labels)
        self.assertIn("somatic:user_present_desk", labels)
        self.assertIn("somatic:user_mobile", labels)

    def test_circadian_and_motion_synthesis(self):
        """Verifies dark room + stationary phone triggers quiet desk session."""
        # 1. Dark room, sitting still on desk, charging
        dark_desk = PhoneSensoryTelemetry(
            lux=4.2,
            battery_pct=98.0,
            battery_charging=True,
            motion_magnitude=0.01,
            audio_amplitude_db=-50.0,
            proximity_covered=False,
        )
        nodes = self.synth.ingest(dark_desk)
        self.assertIn("somatic:circadian_night", nodes)
        self.assertIn("somatic:user_present_desk", nodes)
        self.assertIn("somatic:power_tethered", nodes)
        self.assertIn("somatic:acoustic_quiet", nodes)

        frame = self.synth.build_somatic_frame()
        self.assertIn("Night", frame)
        self.assertIn("Desk/Stationary", frame)
        self.assertIn("Chg", frame)

    def test_mobile_active_daylight_synthesis(self):
        """Verifies outdoor/active motion triggers mobile status."""
        active_day = PhoneSensoryTelemetry(
            lux=1200.0,
            battery_pct=65.0,
            battery_charging=False,
            motion_magnitude=0.75,
            audio_amplitude_db=-25.0,
            proximity_covered=False,
        )
        nodes = self.synth.ingest(active_day)
        self.assertIn("somatic:circadian_day", nodes)
        self.assertIn("somatic:user_mobile", nodes)
        self.assertIn("somatic:acoustic_active", nodes)

        frame = self.synth.build_somatic_frame()
        self.assertIn("Day (1200lx)", frame)
        self.assertIn("Mobile", frame)

    def test_pocket_facedown_detection(self):
        """Verifies proximity covered activates standby."""
        pocket = PhoneSensoryTelemetry(
            lux=0.0,
            proximity_covered=True,
            motion_magnitude=0.1,
        )
        nodes = self.synth.ingest(pocket)
        self.assertIn("somatic:pocket_standby", nodes)
        frame = self.synth.build_somatic_frame()
        self.assertIn("Pocket/FaceDown", frame)

    def test_socket_receiver_pipeline(self):
        """Verifies TCP socket receiver receives telemetry payload and updates synthesizer."""
        # Spin up receiver on non-conflicting loopback port
        receiver = PNSSensoryReceiver(host="127.0.0.1", port=7339, synthesizer=self.synth)
        receiver.start()
        try:
            sample_payload = {
                "timestamp": time.time(),
                "device_id": "test_phone_termux",
                "lux": 12.0,
                "battery_pct": 82.0,
                "battery_charging": True,
                "motion_magnitude": 0.03,
                "wifi_ssid": "Home-5G",
                "audio_amplitude_db": -48.0,
                "screen_on": True,
                "proximity_covered": False,
            }
            success = transmit_to_mothership(sample_payload, host="127.0.0.1", port=7339)
            self.assertTrue(success)
            time.sleep(0.1)

            # Ensure synthesizer received it
            self.assertIsNotNone(self.synth.last_telemetry)
            self.assertEqual(self.synth.last_telemetry.device_id, "test_phone_termux")
            self.assertEqual(self.synth.last_telemetry.lux, 12.0)
            self.assertTrue(self.synth.last_telemetry.battery_charging)

            # Frame check
            frame = self.synth.build_somatic_frame()
            self.assertIn("Night", frame)
            self.assertIn("Chg", frame)
        finally:
            receiver.stop()


if __name__ == "__main__":
    unittest.main()
