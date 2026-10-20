#!/usr/bin/env python3
"""Pre-commit security hook: Prevents accidental commit of keys, tokens, or credentials."""

import os
import re
import subprocess
import sys

PATTERNS = [
    (re.compile(r"-----BEGIN (RSA|OPENSSH|DSA|EC|PGP)? ?PRIVATE KEY-----"), "Private Key detected"),
    (re.compile(r"pypi-[A-Za-z0-9_\-]{30,}"), "PyPI API Token detected"),
    (re.compile(r"gh[pous]_[A-Za-z0-9]{36,}"), "GitHub Token detected"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google API Key detected"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "Secret Key detected"),
]

BLOCKED_EXTENSIONS = {
    ".key", ".enc", ".pem", ".pfx", ".p12", ".token", ".db", ".sqlite", ".sock"
}


def main() -> int:
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except Exception:
        return 0

    staged_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
    violations = []

    for path in staged_files:
        _, ext = os.path.splitext(path)
        if ext.lower() in BLOCKED_EXTENSIONS:
            violations.append(f"Blocked file extension '{ext}' in staged file: {path}")

        if not os.path.isfile(path):
            continue

        try:
            diff_res = subprocess.run(
                ["git", "diff", "--cached", "-U0", "--", path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except Exception:
            continue

        for line in diff_res.stdout.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_text = line[1:]
                for pattern, desc in PATTERNS:
                    if pattern.search(added_text):
                        violations.append(f"{desc} in {path}: line matches pattern")

    if violations:
        sys.stderr.write("\n🚨 [SECURITY HOOK BLOCKED COMMIT] Secret / Sensitive Data Detected:\n")
        for v in violations:
            sys.stderr.write(f"   • {v}\n")
        sys.stderr.write("\nPlease remove or encrypt the sensitive file/data before committing.\n\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
