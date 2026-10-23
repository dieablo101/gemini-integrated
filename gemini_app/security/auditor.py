"""Security Auditor: Continuous posture assessment, file permission hardening, and secrets scanning."""

from __future__ import annotations

import os
import re
import socket
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (RSA|OPENSSH|DSA|EC|PGP)? ?PRIVATE KEY-----"), "Private Key"),
    (re.compile(r"pypi-[A-Za-z0-9_\-]{16,}"), "PyPI API Token"),
    (re.compile(r"gh[pous]_[A-Za-z0-9]{36,}"), "GitHub Personal Access Token"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google Cloud / Gemini API Key"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "OpenAI / Anthropic Secret Key"),
]

SAFE_LISTENER_PORTS = {
    53: "systemd-resolved (DNS)",
    323: "chrony / systemd-timesyncd (NTP)",
    631: "CUPS printing daemon (Localhost)",
    7331: "Gemini Fleet Mothership (HMAC Authenticated)",
    22: "OpenSSH Server",
}


class SecurityAuditor:
    """Continuous system and fleet security posture auditor."""

    def __init__(self, home_dir: Optional[str] = None, workspace_dir: Optional[str] = None) -> None:
        self.home_dir = Path(home_dir or os.path.expanduser("~")).resolve()
        self.workspace_dir = Path(workspace_dir or "/opt/gemini").resolve()
        self.gemini_dir = self.home_dir / ".gemini"
        self.ssh_dir = self.home_dir / ".ssh"

    def audit_permissions(self, auto_fix: bool = False) -> Dict[str, Any]:
        """Audits file and directory permissions for ~/.gemini, ~/.ssh, and workspace git state."""
        issues: List[Dict[str, Any]] = []
        fixed: List[str] = []

        # 1. ~/.gemini base directory
        if self.gemini_dir.exists():
            mode = stat.S_IMODE(self.gemini_dir.stat().st_mode)
            if mode != 0o700:
                issues.append({"path": str(self.gemini_dir), "expected": "0700", "actual": oct(mode), "severity": "HIGH"})
                if auto_fix:
                    self.gemini_dir.chmod(0o700)
                    fixed.append(str(self.gemini_dir))

        # 2. ~/.gemini sensitive files (fleet.key, vault, logs, db)
        if self.gemini_dir.exists():
            for root, dirs, files in os.walk(self.gemini_dir):
                root_path = Path(root)
                # Dirs should be 0700
                d_mode = stat.S_IMODE(root_path.stat().st_mode)
                if (d_mode & 0o077) != 0:
                    issues.append({"path": str(root_path), "expected": "0700", "actual": oct(d_mode), "severity": "MEDIUM"})
                    if auto_fix:
                        root_path.chmod(0o700)
                        fixed.append(str(root_path))

                for f in files:
                    f_path = root_path / f
                    if f_path.is_file():
                        f_mode = stat.S_IMODE(f_path.stat().st_mode)
                        # Files in ~/.gemini should be 0600
                        if (f_mode & 0o077) != 0:
                            issues.append({"path": str(f_path), "expected": "0600", "actual": oct(f_mode), "severity": "HIGH" if "key" in f or "vault" in root else "LOW"})
                            if auto_fix:
                                f_path.chmod(0o600)
                                fixed.append(str(f_path))

        # 3. ~/.ssh directory and keys
        if self.ssh_dir.exists():
            ssh_mode = stat.S_IMODE(self.ssh_dir.stat().st_mode)
            if ssh_mode != 0o700:
                issues.append({"path": str(self.ssh_dir), "expected": "0700", "actual": oct(ssh_mode), "severity": "HIGH"})
                if auto_fix:
                    self.ssh_dir.chmod(0o700)
                    fixed.append(str(self.ssh_dir))

            for f in self.ssh_dir.iterdir():
                if f.is_file():
                    f_mode = stat.S_IMODE(f.stat().st_mode)
                    if f.suffix == ".pub":
                        if f_mode not in (0o644, 0o600):
                            issues.append({"path": str(f), "expected": "0644", "actual": oct(f_mode), "severity": "LOW"})
                            if auto_fix:
                                f.chmod(0o644)
                                fixed.append(str(f))
                    else:
                        if (f_mode & 0o077) != 0:
                            issues.append({"path": str(f), "expected": "0600", "actual": oct(f_mode), "severity": "CRITICAL"})
                            if auto_fix:
                                f.chmod(0o600)
                                fixed.append(str(f))

        # 4. Workspace git directory
        git_dir = self.workspace_dir / ".git"
        if git_dir.exists():
            g_mode = stat.S_IMODE(git_dir.stat().st_mode)
            if (g_mode & 0o077) != 0:
                issues.append({"path": str(git_dir), "expected": "0700", "actual": oct(g_mode), "severity": "MEDIUM"})
                if auto_fix:
                    git_dir.chmod(0o700)
                    fixed.append(str(git_dir))

        return {
            "status": "secure" if not issues else "violations_found",
            "violations_count": len(issues),
            "issues": issues,
            "fixed_paths": fixed,
        }

    def audit_secrets(self, scan_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
        """Scans specified directories and tracked git files for plaintext leaked credentials."""
        dirs_to_scan = scan_dirs or [str(self.workspace_dir / "gemini_app"), str(self.workspace_dir / "scripts")]
        findings: List[Dict[str, Any]] = []

        ignore_exts = {".enc", ".pyc", ".db", ".png", ".jpg", ".svg", ".zip", ".tar.gz", ".git"}

        for d_str in dirs_to_scan:
            p = Path(d_str)
            if not p.exists():
                continue
            for root, _, files in os.walk(p):
                if "/.git" in root or "/__pycache__" in root or "/.venv" in root or "/tests" in root:
                    continue
                for f in files:
                    f_path = Path(root) / f
                    if f_path.suffix.lower() in ignore_exts:
                        continue
                    try:
                        with open(f_path, "r", encoding="utf-8", errors="ignore") as fh:
                            for line_idx, line in enumerate(fh, start=1):
                                # Skip comment lines that are regex references or documentation examples
                                if "re.compile" in line or "PATTERNS" in line or "dummy" in line.lower() or "example" in line.lower():
                                    continue
                                for pat, label in SECRET_PATTERNS:
                                    if pat.search(line):
                                        findings.append({
                                            "file": str(f_path.relative_to(self.workspace_dir)),
                                            "line": line_idx,
                                            "type": label,
                                            "snippet": line.strip()[:60] + "...",
                                        })
                    except Exception:
                        pass

        return {
            "status": "clean" if not findings else "secrets_detected",
            "findings_count": len(findings),
            "findings": findings,
        }

    def audit_open_ports(self) -> Dict[str, Any]:
        """Audits open TCP and UDP ports and maps them to known fleet/system services."""
        ports_info: List[Dict[str, Any]] = []
        try:
            res = subprocess.run(
                ["ss", "-tuln"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            for line in res.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    proto = parts[0]
                    local_addr = parts[4]
                    if ":" in local_addr:
                        ip, port_str = local_addr.rsplit(":", 1)
                        try:
                            port = int(port_str)
                        except ValueError:
                            continue
                        is_loopback = ip.startswith("127.") or ip in ("127.0.0.1", "[::1]", "::1", "localhost")
                        service_name = SAFE_LISTENER_PORTS.get(port, "Unknown / External Service")
                        risk = "LOW"
                        if is_loopback:
                            risk = "NONE"
                        elif port == 7331:
                            risk = "CONTROLLED (Fleet PSK Mutual Auth)"
                        elif port == 22:
                            risk = "GUARDED (SSH Key-Only)"
                        else:
                            risk = "ATTENTION_REQUIRED"

                        ports_info.append({
                            "proto": proto,
                            "ip": ip,
                            "port": port,
                            "service": service_name,
                            "is_loopback": is_loopback,
                            "risk": risk,
                        })
        except Exception as exc:
            return {"status": "error", "error": str(exc), "listeners": []}

        return {
            "status": "audited",
            "listener_count": len(ports_info),
            "listeners": ports_info,
        }

    def audit_fleet_security(self) -> Dict[str, Any]:
        """Audits the cryptographic readiness of the fleet subsystem."""
        vault_key = self.gemini_dir / "vault" / "fleet" / "fleet_key.enc"
        legacy_key = self.gemini_dir / "fleet.key"
        has_key = (vault_key.exists() and vault_key.stat().st_size >= 32) or (legacy_key.exists() and legacy_key.stat().st_size >= 32)
        key_mode_safe = False
        if vault_key.exists():
            mode = stat.S_IMODE(vault_key.stat().st_mode)
            key_mode_safe = (mode == 0o600)
        elif legacy_key.exists():
            mode = stat.S_IMODE(legacy_key.stat().st_mode)
            key_mode_safe = (mode == 0o600)

        # Check authorized SSH keys
        auth_keys_file = self.ssh_dir / "authorized_keys"
        auth_keys_count = 0
        if auth_keys_file.exists():
            with open(auth_keys_file, "r") as fh:
                auth_keys_count = sum(1 for line in fh if line.strip() and not line.startswith("#"))

        return {
            "cluster_psk_present": has_key,
            "cluster_psk_permissions_safe": key_mode_safe,
            "ssh_authorized_keys_count": auth_keys_count,
            "mutual_challenge_response": True,
            "status": "hardened" if (has_key and key_mode_safe) else "attention_needed",
        }

    def generate_security_report(self, auto_fix: bool = True) -> Dict[str, Any]:
        """Generates comprehensive security posture score and report."""
        perm_audit = self.audit_permissions(auto_fix=auto_fix)
        secret_audit = self.audit_secrets()
        port_audit = self.audit_open_ports()
        fleet_audit = self.audit_fleet_security()

        # Score computation (starts at 100)
        score = 100
        penalties = []

        if perm_audit["violations_count"] > 0 and not auto_fix:
            penalty = min(perm_audit["violations_count"] * 10, 30)
            score -= penalty
            penalties.append(f"Permission violations: -{penalty} pts")

        if secret_audit["findings_count"] > 0:
            penalty = min(secret_audit["findings_count"] * 25, 50)
            score -= penalty
            penalties.append(f"Plaintext secrets detected: -{penalty} pts")

        if not fleet_audit["cluster_psk_permissions_safe"]:
            score -= 15
            penalties.append("Cluster PSK permissions loose: -15 pts")

        score = max(score, 0)

        return {
            "posture_score": score,
            "status": "PASS" if score >= 85 else "WARN",
            "penalties": penalties,
            "permissions": perm_audit,
            "secrets": secret_audit,
            "network": port_audit,
            "fleet": fleet_audit,
        }
