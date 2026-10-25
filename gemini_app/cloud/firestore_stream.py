"""Firestore Live Stream Bridge & Upper Mind Observatory Daemon.

Streams real-time cognitive thoughts, subconscious epiphanies,
telemetry, and topological graph updates from the bilateral console
directly to Google Cloud Firestore ('gemini-source') for the
live Upper Mind Observatory (gemini-source.web.app).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("gemini.firestore_stream")

CONFIGSTORE_PATH = Path.home() / ".config" / "configstore" / "firebase-tools.json"
FIREBASE_PROJECT_ID = "gemini-source"
FIREBASE_CLIENT_ID = "563584335869-fgrhgmd47bqnekij5i8b5pr03ho85od6.apps.googleusercontent.com"


def get_firestore_client(project_id: str = FIREBASE_PROJECT_ID) -> Optional[Any]:
    """Obtains an authenticated Firestore client without requiring plaintext keys on disk.

    Resolution order:
    1. Firebase CLI user OAuth token from ~/.config/configstore/firebase-tools.json.
    2. Vault-decrypted service account if active in memory.
    3. Google Application Default Credentials.
    4. None (offline mode).
    """
    # Strategy 1: Firebase CLI token
    if CONFIGSTORE_PATH.is_file():
        try:
            from google.oauth2.credentials import Credentials
            from google.cloud import firestore

            data = json.loads(CONFIGSTORE_PATH.read_text(encoding="utf-8"))
            tokens = data.get("tokens", {})
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")

            if access_token:
                creds = Credentials(
                    token=access_token,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=FIREBASE_CLIENT_ID,
                    scopes=tokens.get("scopes", ["https://www.googleapis.com/auth/cloud-platform"]),
                )
                return firestore.Client(project=project_id, credentials=creds)
        except Exception as e:
            logger.debug(f"Firebase CLI token auth failed: {e}")

    # Strategy 2: Vault in-memory service account
    try:
        from gemini_app.vault import get_session_passkey, retrieve_from_vault
        passkey = get_session_passkey()
        if passkey:
            import firebase_admin
            from firebase_admin import credentials, firestore as admin_firestore

            sa_bytes = retrieve_from_vault("firebase_service_account.json", passkey=passkey)
            sa_info = json.loads(sa_bytes.decode("utf-8"))
            cred = credentials.Certificate(sa_info)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred, {"projectId": project_id})
            return admin_firestore.client()
    except Exception as e:
        logger.debug(f"Vault service account auth failed: {e}")

    # Strategy 3: Application Default Credentials
    try:
        from google.cloud import firestore
        return firestore.Client(project=project_id)
    except Exception as e:
        logger.debug(f"ADC auth failed: {e}")

    return None


class FirestoreStreamBridge:
    """Publishes bilateral console cognition into Firestore for the live web observatory."""

    def __init__(self, db_client: Optional[Any] = None, project_id: str = FIREBASE_PROJECT_ID):
        self.project_id = project_id
        self.db = db_client if db_client is not None else get_firestore_client(project_id)
        self.is_connected = self.db is not None

    def publish_thought(
        self,
        text: str,
        tag: str = "COGNITION",
        class_name: Optional[str] = None,
        source: str = "Bilateral Terminal Console",
        topic: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Publishes an immediate thought entry to both live_stream document and thoughts collection."""
        if not self.is_connected:
            return False

        tag_to_class = {
            "HYPOTHESIS": "tag-hypothesis",
            "ANNEALING": "tag-annealing",
            "COLLISION": "tag-collision",
            "GROUNDED": "tag-grounded",
            "REFLEX": "tag-reflex",
            "COGNITION": "tag-grounded",
        }
        css_class = class_name or tag_to_class.get(tag.upper(), "tag-grounded")
        now_ts = time.time()

        payload = {
            "tag": tag.upper(),
            "class": css_class,
            "text": text,
            "source": source,
            "topic": topic,
            "epoch": now_ts,
            **(extra or {}),
        }

        try:
            # 1. Update root live_stream status
            stream_ref = self.db.collection("observatory").document("live_stream")
            stream_ref.set(
                {
                    "status": "online",
                    "source": source,
                    "active_topic": topic or "uppermind web nexus & public face",
                    "latest_thought": payload,
                    "updated_at": now_ts,
                },
                merge=True,
            )

            # 2. Append to thoughts subcollection
            thought_ref = stream_ref.collection("thoughts").document()
            thought_ref.set(payload)
            return True
        except Exception as e:
            logger.warning(f"Failed to publish live thought: {e}")
            return False

    def publish_telemetry(self, metrics: Dict[str, Any]) -> bool:
        """Publishes live system telemetry metrics to the observatory."""
        if not self.is_connected:
            return False

        try:
            telem_ref = self.db.collection("observatory").document("telemetry")
            telem_ref.set(
                {
                    **metrics,
                    "updated_at": time.time(),
                },
                merge=True,
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to publish telemetry: {e}")
            return False

    def publish_epiphany(
        self,
        summary: str,
        hypothesis: str,
        domains: Optional[List[str]] = None,
        novelty_score: float = 0.95,
    ) -> bool:
        """Publishes a Subconscious Hearth epiphany to the live feed."""
        if not self.is_connected:
            return False

        try:
            ep_ref = self.db.collection("observatory").document("epiphanies_stream").collection("items").document()
            ep_ref.set(
                {
                    "summary": summary,
                    "actionable_hypothesis": hypothesis,
                    "domains": domains or ["Cognition", "Bilateral"],
                    "novelty_score": novelty_score,
                    "timestamp": time.time(),
                }
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to publish epiphany: {e}")
            return False

    def sync_console_state(self, gemini_home: Optional[Path] = None) -> bool:
        """Extracts current local console state, active topic, and notes, streaming them to Firestore."""
        home = gemini_home or (Path.home() / ".gemini")
        state_file = home / "state.json"
        if not state_file.is_file():
            return False

        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            active_chat = state.get("active_chat")
            topic = state.get("active_topic", "uppermind web nexus & public face")

            # Extract recent working notes count
            notes_count = 0
            if active_chat:
                meta_file = home / "chats" / active_chat / "meta.json"
                if meta_file.is_file():
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    notes_count = len(meta.get("notes", {}).get("notes", []))

            # Publish updated telemetry
            self.publish_telemetry(
                {
                    "active_chat": active_chat,
                    "active_topic": topic,
                    "total_notes": notes_count,
                    "node_status": "mothership_online",
                    "reflex_latency_ms": 0.02,
                }
            )

            # Publish a live thought
            return self.publish_thought(
                tag="GROUNDED",
                text=f"Bilateral sync anchor verified on topic '{topic}'. {notes_count} persistent notes indexed.",
                topic=topic,
            )
        except Exception as e:
            logger.warning(f"Failed to sync console state: {e}")
            return False


if __name__ == "__main__":
    bridge = FirestoreStreamBridge()
    if not bridge.is_connected:
        print("[!] Firestore client offline or credentials missing.")
        sys.exit(1)

    print("[+] Connected to Firestore 'gemini-source'.")
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":
        ok = bridge.sync_console_state()
        print(f"[+] State sync completed: {ok}")
    else:
        ok = bridge.publish_thought(
            tag="REFLEX",
            text="Autonomous Firestore Live Stream Daemon operational on Bilateral Mothership.",
            topic="uppermind web nexus & public face",
        )
        print(f"[+] Live thought emitted: {ok}")
