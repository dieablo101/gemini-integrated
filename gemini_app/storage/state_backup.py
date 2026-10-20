"""Automated state backup manager for ~/.gemini to a private GitHub repository.

Manages continuous backup of chat history, SQLite memory indexes,
encrypted vault storage, emergency recovery logs, and configuration state
on a 24-hour daily check timer, with optional systemd timer persistence.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any
import urllib.error
import urllib.request

from gemini_app.config import GEMINI_HOME, STATE_FILE, VAULT_DIR
from gemini_app.fleet.keys import get_cluster_ssh_key

logger = logging.getLogger(__name__)

BACKUP_INTERVAL_SECONDS: int = 86400  # 24 hours
DEFAULT_REPO_NAME: str = ".gemini"
BACKUP_LOG_FILE: Path = GEMINI_HOME / "backup.log"
SYSTEMD_USER_DIR: Path = Path.home() / ".config" / "systemd" / "user"
SERVICE_NAME: str = "gemini-backup.service"
TIMER_NAME: str = "gemini-backup.timer"

GITIGNORE_CONTENT = """*.sock
*.tmp
*.lock
*.db-wal
*.db-shm
*.db-journal

# Vault Security: Plaintext secret protection
# NEVER track unencrypted secrets in git
vault/*.txt
vault/*.token
vault/*.key
!vault/*.enc
!vault/.vault_meta.json

# Screenshots & transient audit captures
screenshots/
"""


def get_backup_metadata() -> dict[str, Any]:
    """Reads current backup metadata from ~/.gemini/state.json."""
    if not STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {
            "last_backup_timestamp": data.get("last_backup_timestamp", 0.0),
            "last_backup_status": data.get("last_backup_status", "never_run"),
            "backup_remote_url": data.get("backup_remote_url", ""),
            "backup_repo_name": data.get("backup_repo_name", DEFAULT_REPO_NAME),
        }
    except Exception as e:
        logger.warning("Failed to read backup metadata: %s", e)
        return {}


def update_backup_metadata(status: str, error: str = "") -> None:
    """Updates last backup timestamp and status in ~/.gemini/state.json."""
    try:
        data: dict[str, Any] = {}
        if STATE_FILE.is_file():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["last_backup_timestamp"] = time.time()
        data["last_backup_status"] = status
        if error:
            data["last_backup_error"] = error
        elif "last_backup_error" in data:
            del data["last_backup_error"]

        STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        STATE_FILE.chmod(0o600)
    except Exception as e:
        logger.error("Failed to update backup metadata: %s", e)


def log_backup_event(message: str) -> None:
    """Appends a timestamped log line to ~/.gemini/backup.log."""
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with BACKUP_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{now_str}] {message}\n")
    except Exception:
        pass


def get_git_credentials() -> tuple[str, str]:
    """Retrieves user's git name and email from state or global git config."""
    name = "Kyle Gallagher"
    email = "kidlucrid@gmail.com"
    if STATE_FILE.is_file():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            name = data.get("git_name") or data.get("user_realname") or name
            email = data.get("git_email") or email
        except Exception:
            pass
    return name, email


def ensure_state_repo_initialized(remote_repo: str = DEFAULT_REPO_NAME) -> Path:
    """Initializes and hardens the git repository in ~/.gemini."""
    GEMINI_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)

    # 1. Write or update security-hardened .gitignore
    gitignore_path = GEMINI_HOME / ".gitignore"
    gitignore_path.write_text(GITIGNORE_CONTENT, encoding="utf-8")

    # 2. Check if git repo exists
    git_dir = GEMINI_HOME / ".git"
    if not git_dir.is_dir():
        subprocess.run(["git", "init", "-b", "main"], cwd=str(GEMINI_HOME), check=True, capture_output=True)

    # 3. Configure local committer credentials
    name, email = get_git_credentials()
    subprocess.run(["git", "config", "user.name", name], cwd=str(GEMINI_HOME), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", email], cwd=str(GEMINI_HOME), check=True, capture_output=True)

    # 4. Configure remote origin
    remote_url, _ = get_configured_backup_remote(remote_repo)
    if remote_url:
        res = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(GEMINI_HOME), capture_output=True, text=True)
        if res.returncode == 0:
            if res.stdout.strip() != remote_url:
                subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=str(GEMINI_HOME), check=True)
        else:
            subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(GEMINI_HOME), check=True)

    return GEMINI_HOME


def get_configured_backup_remote(remote_repo: str = DEFAULT_REPO_NAME) -> tuple[str, Optional[Path]]:
    """Resolves backup remote repository URL and SSH key from user config or state."""
    meta = get_backup_metadata()
    configured_url = meta.get("backup_remote_url", "").strip()
    if configured_url:
        return configured_url, get_cluster_ssh_key()

    # Check ~/.gemini/config.json for github_user, backup_remote_url, or backup_remote
    cfg_file = GEMINI_HOME / "config.json"
    user_name = ""
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            if cfg.get("backup_remote_url"):
                return cfg["backup_remote_url"].strip(), get_cluster_ssh_key()
            user_name = cfg.get("github_user", "").strip() or cfg.get("github_username", "").strip()
        except Exception:
            pass

    if not user_name and STATE_FILE.is_file():
        try:
            st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            user_name = st.get("github_user", "").strip() or st.get("github_username", "").strip()
        except Exception:
            pass

    if not user_name:
        # Default to github.com:current_user or standard fallback
        import getpass
        u = getpass.getuser()
        return f"git@github.com:{u}/{remote_repo}.git", get_cluster_ssh_key()

    return f"git@github.com:{user_name}/{remote_repo}.git", get_cluster_ssh_key()


def check_remote_repo_exists(remote_repo: str = DEFAULT_REPO_NAME) -> bool:
    """Checks if the remote GitHub repository exists and is accessible over SSH."""
    remote_url, ssh_key = get_configured_backup_remote(remote_repo)
    if not remote_url:
        return False

    env = os.environ.copy()
    ssh_cmd = "ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new"
    if ssh_key and ssh_key.is_file():
        ssh_cmd = f"ssh -i {ssh_key} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new"
    env["GIT_SSH_COMMAND"] = ssh_cmd

    try:
        res = subprocess.run(
            ["git", "ls-remote", remote_url],
            cwd=str(GEMINI_HOME),
            capture_output=True,
            text=True,
            env=env,
            timeout=8,
        )
        return res.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def create_private_github_repo(repo_name: str = DEFAULT_REPO_NAME, token: str | None = None) -> tuple[bool, str]:
    """Attempts to create the private repository on GitHub via gh CLI or GitHub REST API.

    Returns (success, message).
    """
    # 1. If explicit token provided or GH_TOKEN env var is set, use GitHub REST API directly
    auth_token = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if auth_token:
        try:
            url = "https://api.github.com/user/repos"
            payload = json.dumps({
                "name": repo_name,
                "private": True,
                "description": "Continuous bilateral state, encrypted vault & cognitive memory backup",
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "Gemini-State-Backup",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    msg = f"Private GitHub repository '{repo_name}' created successfully via GitHub API."
                    log_backup_event(msg)
                    return True, msg
        except urllib.error.HTTPError as e:
            if e.code == 422:
                # Repo likely already exists
                return True, f"Repository '{repo_name}' already exists on GitHub."
            return False, f"GitHub API error ({e.code}): {e.read().decode('utf-8', errors='replace')}"
        except Exception as e:
            return False, f"GitHub API request failed: {e}"

    # 2. Try gh CLI if installed in PATH or ~/.local/bin/gh
    gh_bin = shutil.which("gh") or str(Path.home() / ".local" / "bin" / "gh")
    if Path(gh_bin).is_file():
        res = subprocess.run(
            [gh_bin, "repo", "create", repo_name, "--private"],
            cwd=str(GEMINI_HOME),
            capture_output=True,
            text=True,
            timeout=20,
        )
        if res.returncode == 0:
            msg = f"Private GitHub repository '{repo_name}' created via GitHub CLI."
            log_backup_event(msg)
            return True, msg
        elif "already exists" in res.stderr.lower():
            return True, f"Repository '{repo_name}' already exists on GitHub."
        else:
            return False, f"gh CLI error: {res.stderr.strip()}"

    return False, "Neither GitHub authentication token nor authenticated gh CLI was available."


def perform_backup(force: bool = False) -> dict[str, Any]:
    """Performs an atomic commit and push of ~/.gemini to GitHub.

    Returns dict with keys: 'status', 'committed', 'pushed', 'error', 'timestamp'.
    """
    ensure_state_repo_initialized()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result: dict[str, Any] = {
        "status": "in_progress",
        "committed": False,
        "pushed": False,
        "error": "",
        "timestamp": time.time(),
    }

    # 1. Pre-flight check: Ensure vault protection is intact
    gitignore_path = GEMINI_HOME / ".gitignore"
    if not gitignore_path.is_file() or "vault/*.txt" not in gitignore_path.read_text(encoding="utf-8"):
        gitignore_path.write_text(GITIGNORE_CONTENT, encoding="utf-8")

    # 2. Stage all files (git add -A)
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(GEMINI_HOME), check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err = f"Failed to stage files: {e.stderr.decode(errors='replace')}"
        update_backup_metadata("failed", error=err)
        log_backup_event(f"ERROR: {err}")
        result["status"] = "failed"
        result["error"] = err
        return result

    # 3. Check for staged changes
    diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(GEMINI_HOME))
    has_changes = diff_res.returncode != 0

    if has_changes:
        # Count items for summary
        chat_count = len(list((GEMINI_HOME / "chats").glob("*"))) if (GEMINI_HOME / "chats").is_dir() else 0
        commit_msg = f"backup(state): {now_str} [chats: {chat_count}, memory index, encrypted vault]"
        try:
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(GEMINI_HOME),
                check=True,
                capture_output=True,
            )
            result["committed"] = True
            log_backup_event(f"Committed changes: {commit_msg}")
        except subprocess.CalledProcessError as e:
            err = f"Git commit failed: {e.stderr.decode(errors='replace')}"
            update_backup_metadata("failed", error=err)
            log_backup_event(f"ERROR: {err}")
            result["status"] = "failed"
            result["error"] = err
            return result
    else:
        log_backup_event("No uncommitted changes detected in ~/.gemini.")

    # 4. Check if remote repo exists before pushing
    remote_exists = check_remote_repo_exists(DEFAULT_REPO_NAME)
    remote_url, ssh_key = get_configured_backup_remote(DEFAULT_REPO_NAME)

    if not remote_exists:
        err = (
            f"Remote repository '{remote_url}' not found on GitHub. "
            f"Please create a private repo named '{DEFAULT_REPO_NAME}' at https://github.com/new "
            f"or run 'gh auth login' to allow automatic creation."
        )
        update_backup_metadata("awaiting_remote_repo", error=err)
        log_backup_event(f"WARNING: {err}")
        result["status"] = "awaiting_remote_repo"
        result["error"] = err
        return result

    # 5. Push to GitHub
    env = os.environ.copy()
    ssh_cmd = "ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new"
    if ssh_key and ssh_key.is_file():
        ssh_cmd = f"ssh -i {ssh_key} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new"
    env["GIT_SSH_COMMAND"] = ssh_cmd

    try:
        push_res = subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=str(GEMINI_HOME),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        if push_res.returncode == 0:
            result["pushed"] = True
            result["status"] = "success"
            update_backup_metadata("success")
            log_backup_event("Successfully pushed state backup to GitHub.")
        else:
            err = f"Git push failed: {push_res.stderr.strip()}"
            update_backup_metadata("failed", error=err)
            log_backup_event(f"ERROR: {err}")
            result["status"] = "failed"
            result["error"] = err
    except subprocess.TimeoutExpired:
        err = "Git push timed out after 60 seconds."
        update_backup_metadata("failed", error=err)
        log_backup_event(f"ERROR: {err}")
        result["status"] = "failed"
        result["error"] = err
    except Exception as e:
        err = f"Unexpected push error: {e}"
        update_backup_metadata("failed", error=err)
        log_backup_event(f"ERROR: {err}")
        result["status"] = "failed"
        result["error"] = err

    return result


def is_daily_backup_due() -> bool:
    """Returns True if at least 24 hours (86,400 seconds) have elapsed since the last backup."""
    meta = get_backup_metadata()
    last_time = meta.get("last_backup_timestamp", 0.0)
    if not last_time:
        return True
    return (time.time() - last_time) >= BACKUP_INTERVAL_SECONDS


def check_and_run_daily_backup(force: bool = False) -> dict[str, Any] | None:
    """Executes backup if due or if force=True."""
    if force or is_daily_backup_due():
        return perform_backup(force=force)
    return None


def install_systemd_backup_timer() -> tuple[bool, str]:
    """Configures and activates a systemd user timer to run daily backups at 03:00."""
    try:
        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        py_exec = shutil.which("python3") or "/usr/bin/python3"

        service_content = f"""[Unit]
Description=Gemini Bilateral State Continuous Backup (Private GitHub)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={GEMINI_HOME}
ExecStart={py_exec} -m gemini_app.storage.state_backup --run
Environment=PYTHONPATH=/opt/gemini
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""
        timer_content = """[Unit]
Description=Daily 24-hour backup trigger for ~/.gemini

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=900
Persistent=true

[Install]
WantedBy=timers.target
"""
        service_file = SYSTEMD_USER_DIR / SERVICE_NAME
        timer_file = SYSTEMD_USER_DIR / TIMER_NAME

        service_file.write_text(service_content, encoding="utf-8")
        timer_file.write_text(timer_content, encoding="utf-8")

        # Reload and enable timer
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", TIMER_NAME], check=True, capture_output=True)

        msg = f"Systemd user timer '{TIMER_NAME}' enabled and active (runs daily at 03:00 with persistence)."
        log_backup_event(msg)
        return True, msg
    except Exception as e:
        msg = f"Failed to configure systemd timer: {e}"
        log_backup_event(f"WARNING: {msg}")
        return False, msg


if __name__ == "__main__":
    import sys

    if "--install-timer" in sys.argv:
        ok, message = install_systemd_backup_timer()
        print(message)
        sys.exit(0 if ok else 1)
    elif "--run" in sys.argv or "--force" in sys.argv:
        res = perform_backup(force="--force" in sys.argv)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("status") == "success" else 1)
    else:
        # Default: check if 24 hours elapsed
        if is_daily_backup_due():
            res = perform_backup()
            print(json.dumps(res, indent=2))
        else:
            meta = get_backup_metadata()
            elapsed = time.time() - meta.get("last_backup_timestamp", 0.0)
            print(f"Daily backup not due yet ({elapsed / 3600:.1f}h / 24h elapsed). Use --force to run immediately.")
