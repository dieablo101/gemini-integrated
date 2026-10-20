"""Unit tests for Gemini Security Subsystem (Auditor, Fleet Guard, Posture Scoring)."""

import os
import shutil
import stat
import tempfile
import time
import unittest

from gemini_app.security.auditor import SecurityAuditor
from gemini_app.security.fleet_guard import FleetGuard


class TestSecurityAuditor(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="gemini_sec_test_")
        self.home_dir = os.path.join(self.test_dir, "home")
        self.workspace_dir = os.path.join(self.test_dir, "workspace")
        os.makedirs(self.home_dir, mode=0o755)
        os.makedirs(self.workspace_dir, mode=0o755)

        self.gemini_dir = os.path.join(self.home_dir, ".gemini")
        self.ssh_dir = os.path.join(self.home_dir, ".ssh")
        os.makedirs(self.gemini_dir, mode=0o755)
        os.makedirs(self.ssh_dir, mode=0o755)

        self.auditor = SecurityAuditor(home_dir=self.home_dir, workspace_dir=self.workspace_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_permission_audit_detects_loose_permissions(self) -> None:
        # Create loose files
        loose_key = os.path.join(self.ssh_dir, "id_ed25519")
        with open(loose_key, "w") as f:
            f.write("key data")
        os.chmod(loose_key, 0o644)

        fleet_key = os.path.join(self.gemini_dir, "fleet.key")
        with open(fleet_key, "w") as f:
            f.write("fleet-cluster-psk")
        os.chmod(fleet_key, 0o664)

        report = self.auditor.audit_permissions(auto_fix=False)
        self.assertEqual(report["status"], "violations_found")
        self.assertGreaterEqual(report["violations_count"], 2)

    def test_permission_audit_auto_fixes(self) -> None:
        loose_key = os.path.join(self.ssh_dir, "id_ed25519")
        with open(loose_key, "w") as f:
            f.write("key data")
        os.chmod(loose_key, 0o644)

        report = self.auditor.audit_permissions(auto_fix=True)
        self.assertIn(loose_key, report["fixed_paths"])

        # Verify fixed mode
        mode = stat.S_IMODE(os.stat(loose_key).st_mode)
        self.assertEqual(mode, 0o600)

        # Re-audit should be secure
        clean_report = self.auditor.audit_permissions(auto_fix=False)
        self.assertEqual(clean_report["status"], "secure")

    def test_secrets_auditor_detects_pattern(self) -> None:
        app_dir = os.path.join(self.workspace_dir, "gemini_app")
        os.makedirs(app_dir, exist_ok=True)
        leaked_file = os.path.join(app_dir, "leak.py")
        with open(leaked_file, "w") as f:
            f.write('TOKEN = "pypi-AgEIcHlwaS5vcmcCJDI1NjA5"\n')

        sec_report = self.auditor.audit_secrets(scan_dirs=[app_dir])
        self.assertEqual(sec_report["status"], "secrets_detected")
        self.assertEqual(sec_report["findings_count"], 1)
        self.assertEqual(sec_report["findings"][0]["type"], "PyPI API Token")

    def test_security_score_calculation(self) -> None:
        report = self.auditor.generate_security_report(auto_fix=True)
        self.assertIn("posture_score", report)
        self.assertGreaterEqual(report["posture_score"], 80)


class TestFleetGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = FleetGuard(max_failures=3, ban_duration=1.0, nonce_window=5.0)

    def test_ip_ban_on_repeated_failures(self) -> None:
        ip = "192.168.1.55"
        self.assertFalse(self.guard.is_ip_banned(ip))

        self.assertFalse(self.guard.record_auth_failure(ip))
        self.assertFalse(self.guard.record_auth_failure(ip))
        banned = self.guard.record_auth_failure(ip)

        self.assertTrue(banned)
        self.assertTrue(self.guard.is_ip_banned(ip))

        # Test expiration
        time.sleep(1.1)
        self.assertFalse(self.guard.is_ip_banned(ip))

    def test_auth_success_resets_failures(self) -> None:
        ip = "192.168.1.60"
        self.guard.record_auth_failure(ip)
        self.guard.record_auth_failure(ip)
        self.guard.record_auth_success(ip)

        # After success, another failure should not trigger ban (starts count fresh)
        banned = self.guard.record_auth_failure(ip)
        self.assertFalse(banned)
        self.assertFalse(self.guard.is_ip_banned(ip))

    def test_nonce_replay_protection(self) -> None:
        nonce = "test-nonce-12345"
        now = time.time()

        # First consumption is valid
        self.assertTrue(self.guard.verify_and_consume_nonce(nonce, now))

        # Replay attempt with same nonce is rejected
        self.assertFalse(self.guard.verify_and_consume_nonce(nonce, now))

        # Expired nonce is rejected
        expired_nonce = "test-nonce-expired"
        self.assertFalse(self.guard.verify_and_consume_nonce(expired_nonce, now - 100))


if __name__ == "__main__":
    unittest.main()
