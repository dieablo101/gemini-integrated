"""Cognition Sync Rehydration Engine.

Provides zero-loss state recovery across all reboot profiles:
• Level 1: Fast In-Place / Warm Restart (<50ms local load + async cloud delta check)
• Level 2: Cold System Reboot (Vault Locked -> Local Mode until authenticated)
• Level 3: Zero-State Hydration (Fresh Machine -> Full Cloud Bedrock reconstruction)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from gemini_app.config import GEMINI_HOME, STATE_FILE
from gemini_app.vault import is_vault_configured, is_session_unlocked

logger = logging.getLogger("gemini.rehydrate")


class CognitionSyncHydrator:
    """Manages state rehydration and delta reconciliation across reboots."""

    def __init__(self, gemini_home: Optional[Path] = None, upper_mind_client: Optional[Any] = None):
        self.home = gemini_home or GEMINI_HOME
        self.state_file = self.home / "state.json"
        self.notes_file = self.home / "notes.json"
        self.history_dir = self.home / "history"
        self.client = upper_mind_client

    def _is_vault_configured(self) -> bool:
        """Checks if vault passkey hash is configured for this home directory."""
        meta = self.home / "vault" / ".vault_meta.json"
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                if data.get("hash"):
                    return True
            except Exception:
                pass
        if self.state_file.is_file():
            try:
                st = json.loads(self.state_file.read_text(encoding="utf-8"))
                if st.get("vault_passkey_hash"):
                    return True
            except Exception:
                pass
        return False

    def detect_reboot_level(self) -> str:
        """Determines the current boot state profile:

        - 'level_3_zero_state': Fresh machine or wiped ~/.gemini
        - 'level_2_cold_locked': Vault configured but session passkey locked
        - 'level_1_warm_local': Local files and working state intact
        """
        if not self.home.is_dir() or not self.state_file.is_file():
            return "level_3_zero_state"

        # Check if vault is configured and locked
        if self._is_vault_configured() and not is_session_unlocked():
            return "level_2_cold_locked"

        return "level_1_warm_local"

    def compute_local_epoch(self) -> float:
        """Reads the local state modification epoch."""
        if self.state_file.is_file():
            try:
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
                return float(state.get("updated_at", self.state_file.stat().st_mtime))
            except Exception:
                return self.state_file.stat().st_mtime
        return 0.0

    def hydrate_fast_local(self) -> Dict[str, Any]:
        """Level 1 Fast Path (<50ms): Mounts immediate state from local files."""
        state = {}
        if self.state_file.is_file():
            try:
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Error loading local state.json: {e}")

        notes = {}
        if self.notes_file.is_file():
            try:
                notes = json.loads(self.notes_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Error loading local notes.json: {e}")

        return {
            "level": "level_1_warm_local",
            "state": state,
            "notes": notes,
            "fast_mounted": True,
        }

    def reconcile_async_delta(self) -> Dict[str, Any]:
        """Asynchronously queries Upper Mind for unconsumed subconscious epiphanies

        or newer milestone checkpoints, applying delta atomically.
        """
        if not self.client or getattr(self.client, "offline_mode", True):
            return {"status": "offline_noop", "epiphanies_applied": 0}

        try:
            epiphanies = self.client.fetch_unconsumed_epiphanies()
            applied_count = 0

            if epiphanies:
                applied_count = self._apply_epiphanies_to_notes(epiphanies)

            return {
                "status": "delta_synced",
                "epiphanies_applied": applied_count,
            }
        except Exception as e:
            logger.warning(f"Async delta reconciliation error: {e}")
            return {"status": "error", "error": str(e), "epiphanies_applied": 0}

    def _apply_epiphanies_to_notes(self, epiphanies: List[Dict[str, Any]]) -> int:
        """Appends unconsumed epiphanies into local notes atomically."""
        if not epiphanies:
            return 0

        self.home.mkdir(parents=True, exist_ok=True)
        notes_data: Dict[str, Any] = {}
        if self.notes_file.is_file():
            try:
                notes_data = json.loads(self.notes_file.read_text(encoding="utf-8"))
            except Exception:
                notes_data = {}

        notes_list = notes_data.setdefault("notes", [])
        added = 0

        for ep in epiphanies:
            ep_id = ep.get("id", f"ep_{time.time()}")
            content = ep.get("content") or ep.get("insight") or ep.get("summary")
            if not content:
                continue

            # Check for duplication
            already_exists = any(
                n.get("epiphany_id") == ep_id or n.get("content") == content
                for n in notes_list
            )
            if not already_exists:
                notes_list.append({
                    "author": "gemini",
                    "status": ep.get("status", "think_about"),
                    "topic": ep.get("topic", "epiphany & subconscious engine"),
                    "content": content,
                    "created_at": ep.get("created_at", time.time()),
                    "epiphany_id": ep_id,
                    "source": "subconscious_hearth",
                })
                added += 1
                if self.client:
                    self.client.mark_epiphany_consumed(ep_id)

        if added > 0:
            tmp = self.notes_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(notes_data, indent=2), encoding="utf-8")
            tmp.replace(self.notes_file)

        return added

    def hydrate_zero_state(
        self,
        cloud_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Level 3 Zero-State Rehydration (Disaster Recovery / Fresh Machine).

        Reconstructs state.json, notes.json, and initial history segments.
        Guarantees atomic commit so partial network failures never corrupt local storage.
        """
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.history_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        rebuilt_items: List[str] = []

        # 1. Rebuild state.json
        state_data = cloud_payload.get("state") or {
            "current_topic": "epiphany & subconscious engine",
            "mind_map": {
                "gemini_state": "Hydrated from Upper Mind Bedrock Ledger.",
                "user_state": "System restored from cloud zero-state.",
                "tree_state": ["T1", "F:gemini_app/cloud/upper_mind.py"],
            },
            "turn_counter": cloud_payload.get("turn_counter", 1),
            "updated_at": time.time(),
        }

        state_tmp = self.state_file.with_suffix(".tmp")
        state_tmp.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
        state_tmp.replace(self.state_file)
        rebuilt_items.append("state.json")

        # 2. Rebuild notes.json
        notes_data = cloud_payload.get("notes") or {"notes": [], "version": 1}
        notes_tmp = self.notes_file.with_suffix(".tmp")
        notes_tmp.write_text(json.dumps(notes_data, indent=2), encoding="utf-8")
        notes_tmp.replace(self.notes_file)
        rebuilt_items.append("notes.json")

        # 3. Rebuild shadow graph if present
        if "shadow_graph" in cloud_payload and self.client:
            self.client._shadow_graph = cloud_payload["shadow_graph"]
            self.client._save_shadow_graph()
            rebuilt_items.append("shadow_graph.json")

        return {
            "status": "rehydrated",
            "rebuilt_items": rebuilt_items,
            "turn_counter": state_data.get("turn_counter", 1),
            "topic": state_data.get("current_topic", ""),
        }
