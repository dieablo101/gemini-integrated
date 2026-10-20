"""Fleet Security Guard: Rate limiting, IP banning, and replay protection for Mothership."""

from __future__ import annotations

import threading
import time
from typing import Dict, Set


class FleetGuard:
    """Guards Mothership against unauthenticated flooding, brute-force HMAC attacks, and replay attacks."""

    def __init__(
        self,
        max_failures: int = 5,
        ban_duration: float = 600.0,
        nonce_window: float = 60.0,
    ) -> None:
        self.max_failures = max_failures
        self.ban_duration = ban_duration
        self.nonce_window = nonce_window

        self.failed_attempts: Dict[str, list[float]] = {}
        self.banned_ips: Dict[str, float] = {}  # ip -> banned_until
        self.seen_nonces: Dict[str, float] = {}  # nonce -> timestamp
        self.lock = threading.Lock()

    def is_ip_banned(self, ip: str) -> bool:
        """Checks if an IP address is currently banned."""
        with self.lock:
            now = time.time()
            if ip in self.banned_ips:
                if now < self.banned_ips[ip]:
                    return True
                else:
                    del self.banned_ips[ip]
            return False

    def record_auth_failure(self, ip: str) -> bool:
        """Records a failed authentication attempt. Returns True if IP was newly banned."""
        with self.lock:
            now = time.time()
            # Clean up old failure timestamps older than ban_duration
            timestamps = self.failed_attempts.setdefault(ip, [])
            timestamps = [t for t in timestamps if (now - t) < self.ban_duration]
            timestamps.append(now)
            self.failed_attempts[ip] = timestamps

            if len(timestamps) >= self.max_failures:
                self.banned_ips[ip] = now + self.ban_duration
                self.failed_attempts.pop(ip, None)
                return True
            return False

    def record_auth_success(self, ip: str) -> None:
        """Clears failure history upon successful HMAC challenge verification."""
        with self.lock:
            self.failed_attempts.pop(ip, None)

    def verify_and_consume_nonce(self, nonce: str, ts: float) -> bool:
        """Ensures a challenge nonce is consumed exactly once and within time drift limits."""
        with self.lock:
            now = time.time()
            if abs(now - ts) > self.nonce_window:
                return False
            if nonce in self.seen_nonces:
                return False

            self.seen_nonces[nonce] = now
            # Prune old nonces
            cutoff = now - self.nonce_window * 2
            self.seen_nonces = {n: t for n, t in self.seen_nonces.items() if t > cutoff}
            return True

    def unban_ip(self, ip: str) -> bool:
        """Manually unbans an IP address."""
        with self.lock:
            return bool(self.banned_ips.pop(ip, None))

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            now = time.time()
            active_bans = {ip: round(until - now, 1) for ip, until in self.banned_ips.items() if until > now}
            return {
                "active_bans": active_bans,
                "tracked_failed_ips": len(self.failed_attempts),
                "active_nonces": len(self.seen_nonces),
            }
