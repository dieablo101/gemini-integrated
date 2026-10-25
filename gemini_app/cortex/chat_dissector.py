"""
chat_dissector.py - Epistemic Stream Dissector & Concurrent Staging Buffer.

Transforms linear conversational transcripts and real-time streaming messages
into atomic semantic shards categorized by domain, invariant permanence,
and salience, holding messages in a concurrent staging buffer until valued.
Includes UserBurstConsolidator to seamlessly unify multiple consecutive user messages.
"""

from __future__ import annotations
import re
import time
import uuid
import hashlib
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
import threading


class ShardCategory(str, Enum):
    INVARIANT_RULE = "invariant_rule"       # Security policies, coordinate conventions, encryption rules
    TECHNICAL_SPEC = "technical_spec"       # Ports, baud rates, GPU/Vulkan/shader limits, paths
    PROJECT_ANCHOR = "project_anchor"       # Milestones, feature branches, persistent task threads
    UNRESOLVED_TODO = "unresolved_todo"     # Pending action items, calibrate timers, rescue queues
    TRANSIENT_NOISE = "transient_noise"     # Fleeting banter, raw stdout/stderr logs, intermediate errors


class ShardDomain(str, Enum):
    PIPELINE_3D = "3d_pipeline"
    FLEET_TELEMETRY = "fleet_telemetry"
    SECURITY_VAULT = "security_vault"
    EMACS_DOJO = "emacs_dojo"
    COGNITIVE_MIND = "cognitive_mind"
    SYSTEM_RUNTIME = "system_runtime"
    GENERAL = "general"


@dataclass
class ChatShard:
    shard_id: str
    source_turn_id: str
    turn_index: int
    role: str
    domain: ShardDomain
    category: ShardCategory
    salience: float                       # Dynamic energy float (0.0 -> 2.0)
    content: str                          # Distilled semantic proposition
    summary: str                          # One-line headline for card view
    keywords: List[str] = field(default_factory=list)
    sha256: str = ""
    timestamp: float = field(default_factory=time.time)
    epistemic_decay_rate: float = 0.05    # Lower = more permanent
    reinforcement_count: int = 1
    constituent_turn_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.sha256 and self.content:
            self.sha256 = hashlib.sha256(self.content.encode("utf-8")).hexdigest()[:16]
        if not self.constituent_turn_ids and self.source_turn_id:
            self.constituent_turn_ids = [self.source_turn_id]


@dataclass
class BufferedTurn:
    turn_id: str
    turn_index: int
    role: str
    text: str
    timestamp: float
    reinforced_hits: int = 0
    staged_at: float = field(default_factory=time.time)


class ConcurrentStagingBuffer:
    """
    Thread-safe staging buffer keeping recent incoming messages concurrent
    and fluid in RAM before solidification into relational database tables.
    """
    def __init__(self, capacity: int = 20, hold_window_seconds: float = 2.0):
        self.capacity = capacity
        self.hold_window_seconds = hold_window_seconds
        self._lock = threading.Lock()
        self._buffer: List[BufferedTurn] = []

    def push(self, turn_id: str, turn_index: int, role: str, text: str, timestamp: Optional[float] = None) -> None:
        with self._lock:
            ts = timestamp if timestamp is not None else time.time()
            # Reinforcement scan: check if new text references terms in earlier buffered items
            words = set(re.findall(r"\w{4,}", text.lower()))
            for item in self._buffer:
                item_words = set(re.findall(r"\w{4,}", item.text.lower()))
                common = words.intersection(item_words)
                if common:
                    item.reinforced_hits += len(common)

            self._buffer.append(BufferedTurn(
                turn_id=turn_id,
                turn_index=turn_index,
                role=role,
                text=text,
                timestamp=ts
            ))
            if len(self._buffer) > self.capacity:
                self._buffer.pop(0)

    def get_staged(self) -> List[BufferedTurn]:
        with self._lock:
            return list(self._buffer)

    def drain_for_valuation(self) -> List[BufferedTurn]:
        with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
            return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)


class UserBurstConsolidator:
    """
    Consolidates 2, 3, or 4 consecutive user messages into coherent propositional units
    before sharding. Prevents thought fragmentation when user types in short bursts.
    """
    def __init__(self, max_burst_gap_seconds: float = 60.0):
        self.max_burst_gap_seconds = max_burst_gap_seconds

    def consolidate_messages(self, messages: List[BufferedTurn]) -> List[Dict[str, Any]]:
        """
        Groups consecutive messages from the same role. If multiple user messages
        occur in sequence, unifies their text into a single coherent burst while
        preserving individual IDs and timestamps.
        """
        if not messages:
            return []

        bursts: List[Dict[str, Any]] = []
        current_burst: Optional[Dict[str, Any]] = None

        for msg in messages:
            if current_burst is None:
                current_burst = {
                    "role": msg.role,
                    "turn_ids": [msg.turn_id],
                    "turn_indices": [msg.turn_index],
                    "texts": [msg.text],
                    "first_timestamp": msg.timestamp,
                    "last_timestamp": msg.timestamp,
                    "reinforced_hits": msg.reinforced_hits
                }
            elif current_burst["role"] == msg.role and msg.role in ("user", CURRENT_USER if 'CURRENT_USER' in globals() else "user"):
                # Consecutive user messages: fold into the current burst
                current_burst["turn_ids"].append(msg.turn_id)
                current_burst["turn_indices"].append(msg.turn_index)
                current_burst["texts"].append(msg.text)
                current_burst["last_timestamp"] = msg.timestamp
                current_burst["reinforced_hits"] += msg.reinforced_hits
            else:
                bursts.append(current_burst)
                current_burst = {
                    "role": msg.role,
                    "turn_ids": [msg.turn_id],
                    "turn_indices": [msg.turn_index],
                    "texts": [msg.text],
                    "first_timestamp": msg.timestamp,
                    "last_timestamp": msg.timestamp,
                    "reinforced_hits": msg.reinforced_hits
                }

        if current_burst is not None:
            bursts.append(current_burst)

        # Build clean output units
        consolidated: List[Dict[str, Any]] = []
        for b in bursts:
            unified_text = "\n".join(t.strip() for t in b["texts"] if t.strip())
            consolidated.append({
                "role": b["role"],
                "primary_turn_id": b["turn_ids"][-1],
                "constituent_turn_ids": b["turn_ids"],
                "turn_index": b["turn_indices"][-1],
                "text": unified_text,
                "timestamp": b["first_timestamp"],
                "reinforced_hits": b["reinforced_hits"],
                "burst_count": len(b["turn_ids"])
            })

        return consolidated


class ChatDissector:
    """
    Epistemic classifier and semantic sharder.
    Breaks unstructured conversation turns into structured atomic shards.
    """
    DOMAIN_PATTERNS = {
        ShardDomain.PIPELINE_3D: [
            r"\b(blender|godot|mesh|rigging|armature|pbr|shader|bmesh|bpy|fbx|gltf|quaternion|basis|gram[- ]schmidt)\b"
        ],
        ShardDomain.FLEET_TELEMETRY: [
            r"\b(fleet|satellite|ish|termux|android|ipad|node_id|ping|mesh|cluster|ssh rescue|tailscale)\b"
        ],
        ShardDomain.SECURITY_VAULT: [
            r"\b(vault|pypi_token|encrypted|passkey|pbkdf2|aes|sha[- ]?256|secret|credential|token\.txt\.enc)\b"
        ],
        ShardDomain.EMACS_DOJO: [
            r"\b(emacs|dojo|scratch buffer|keystroke|cadence|avy|bracket|mentorship|keybinding)\b"
        ],
        ShardDomain.COGNITIVE_MIND: [
            r"\b(mind_twin|erebos|hypergraph|cortex|working memory|miller'?s law|ebbinghaus|directional gate|shard)\b"
        ],
        ShardDomain.SYSTEM_RUNTIME: [
            r"\b(unittest|reboot|systemd|kernel|pty|stdout|stderr|exit_code|traceback|socket|daemon)\b"
        ]
    }

    CATEGORY_PATTERNS = {
        ShardCategory.INVARIANT_RULE: [
            r"\b(rule|must always|never|invariant|convention|strictly|standard|protocol|policy)\b",
            r"(Z-up|Y-up|PBKDF2|AES-256|LWW-CRDT|safe mode)"
        ],
        ShardCategory.TECHNICAL_SPEC: [
            r"(\b\d+\s*(ms|fps|gb|mb|hz|frame|interval|sampler|port)\b|\b0x[0-9a-fA-F]+\b|\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)",
            r"(\.py|\.json|\.db|\.enc|~/\.gemini/|/opt/gemini/)"
        ],
        ShardCategory.UNRESOLVED_TODO: [
            r"\b(todo|fixme|pending|get back to|calibrate|investigate|needs? to be|shelved for now)\b"
        ],
        ShardCategory.PROJECT_ANCHOR: [
            r"\b(scaffold|phase [0-9]|architecture|roadmap|implementation plan|pipeline|stage [0-9])\b"
        ]
    }

    def __init__(self):
        self.compiled_domains = {
            domain: [re.compile(p, re.IGNORECASE) for p in pats]
            for domain, pats in self.DOMAIN_PATTERNS.items()
        }
        self.compiled_categories = {
            cat: [re.compile(p, re.IGNORECASE) for p in pats]
            for cat, pats in self.CATEGORY_PATTERNS.items()
        }
        self.burst_consolidator = UserBurstConsolidator()

    def classify_domain(self, text: str) -> ShardDomain:
        scores: Dict[ShardDomain, int] = {d: 0 for d in ShardDomain}
        for domain, patterns in self.compiled_domains.items():
            for pat in patterns:
                matches = pat.findall(text)
                scores[domain] += len(matches)
        best_domain, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score == 0:
            return ShardDomain.GENERAL
        return best_domain

    def classify_category(self, text: str) -> ShardCategory:
        scores: Dict[ShardCategory, int] = {c: 0 for c in ShardCategory}
        for category, patterns in self.compiled_categories.items():
            for pat in patterns:
                matches = pat.findall(text)
                scores[category] += len(matches)
        
        # Check if text is mostly noise/traceback
        if len(text.strip().splitlines()) > 10 and ("Traceback" in text or "exit_code:" in text or "  File " in text):
            return ShardCategory.TRANSIENT_NOISE

        best_cat, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score == 0:
            if len(text.strip()) < 50 and not any(ch in text for ch in [':', '=', '{', '[']):
                return ShardCategory.TRANSIENT_NOISE
            return ShardCategory.PROJECT_ANCHOR
        return best_cat

    def compute_salience(self, category: ShardCategory, domain: ShardDomain, text_len: int, reinforced_hits: int = 0, burst_count: int = 1) -> float:
        base_weights = {
            ShardCategory.INVARIANT_RULE: 1.8,
            ShardCategory.PROJECT_ANCHOR: 1.4,
            ShardCategory.TECHNICAL_SPEC: 1.2,
            ShardCategory.UNRESOLVED_TODO: 1.3,
            ShardCategory.TRANSIENT_NOISE: 0.3,
        }
        base = base_weights.get(category, 1.0)
        # Reinforcement & multi-message burst bonus
        reinforce_bonus = min(0.5, (reinforced_hits * 0.1) + ((burst_count - 1) * 0.15))
        # Length factor
        length_factor = 1.0
        if text_len < 30:
            length_factor = 0.6
        elif text_len > 4000:
            length_factor = 0.85
        
        salience = round(base * length_factor + reinforce_bonus, 3)
        return max(0.1, min(2.0, salience))

    def extract_keywords(self, text: str) -> List[str]:
        words = re.findall(r"\b[A-Za-z0-9_]{3,}\b", text.lower())
        stopwords = {
            "this", "that", "with", "from", "have", "here", "what", "when", "then",
            "will", "about", "your", "user", "turn", "system", "into", "also", "just",
            "need", "make", "true", "false", "none", "item", "the", "are", "and",
            "for", "was", "were", "been", "being", "has", "had", "does", "did",
            "doing", "would", "should", "could", "let", "lets", "which", "their",
            "there", "some", "such", "than", "more", "very"
        }
        filtered = [w for w in words if w not in stopwords and not w.isdigit() and len(w) >= 3]
        counts: Dict[str, int] = {}
        for w in filtered:
            counts[w] = counts.get(w, 0) + 1
        sorted_kw = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [k for k, _ in sorted_kw[:15]]

    def extract_summary(self, text: str) -> str:
        lines = [line.strip().lstrip("#-•* ") for line in text.splitlines() if line.strip()]
        if not lines:
            return "Empty Shard"
        first = lines[0]
        # Never mention "Turn #" or turn indexes in summary
        first = re.sub(r"\bTurn\s*\d+\b", "", first, flags=re.IGNORECASE).strip()
        if len(first) > 80:
            return first[:77] + "..."
        return first

    def dissect_turn(
        self,
        turn_id: str,
        turn_index: int,
        role: str,
        text: str,
        timestamp: float = 0.0,
        reinforced_hits: int = 0,
        constituent_ids: Optional[List[str]] = None,
        burst_count: int = 1
    ) -> List[ChatShard]:
        """
        Dissects a single turn (or unified user burst) into one or more semantic shards.
        Partitions large entries so high-value rules are decoupled from transient text.
        """
        sections = self._partition_text(text)
        shards: List[ChatShard] = []
        c_ids = constituent_ids or [turn_id]

        for idx, sec in enumerate(sections):
            domain = self.classify_domain(sec)
            category = self.classify_category(sec)
            salience = self.compute_salience(category, domain, len(sec), reinforced_hits, burst_count)
            decay_rate = 0.005 if category == ShardCategory.INVARIANT_RULE else (0.15 if category == ShardCategory.TRANSIENT_NOISE else 0.05)
            
            shard_id = f"{turn_id}_{idx}" if len(sections) > 1 else turn_id
            keywords = self.extract_keywords(sec)
            summary = self.extract_summary(sec)

            shards.append(ChatShard(
                shard_id=shard_id,
                source_turn_id=turn_id,
                turn_index=turn_index,
                role=role,
                domain=domain,
                category=category,
                salience=salience,
                content=sec.strip(),
                summary=summary,
                keywords=keywords,
                timestamp=timestamp or time.time(),
                epistemic_decay_rate=decay_rate,
                reinforcement_count=1 + reinforced_hits,
                constituent_turn_ids=c_ids
            ))

        return shards

    def dissect_staged_stream(self, staged_turns: List[BufferedTurn]) -> List[ChatShard]:
        """
        Processes a series of buffered turns, consolidating consecutive user bursts first.
        """
        consolidated = self.burst_consolidator.consolidate_messages(staged_turns)
        all_shards: List[ChatShard] = []

        for item in consolidated:
            shards = self.dissect_turn(
                turn_id=item["primary_turn_id"],
                turn_index=item["turn_index"],
                role=item["role"],
                text=item["text"],
                timestamp=item["timestamp"],
                reinforced_hits=item["reinforced_hits"],
                constituent_ids=item["constituent_turn_ids"],
                burst_count=item["burst_count"]
            )
            all_shards.extend(shards)

        return all_shards

    def _partition_text(self, text: str) -> List[str]:
        if len(text) < 600:
            return [text]
        splits = re.split(r"\n(?=#{1,3}\s+|\b[A-Z\s]{4,}:|\n---\n)", text)
        clean = [s.strip() for s in splits if len(s.strip()) > 40]
        return clean if clean else [text]
