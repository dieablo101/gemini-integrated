"""
test_relational_lens.py - Test Suite & Benchmark for Relational Cortex & Feed Lens.

Validates the stream dissector, relational hyper-table storage, bi-mental
continuous pagination projection, and benchmarks performance against historical turns.
"""

import unittest
import os
import json
import time
import threading
from pathlib import Path

from sandbox.mind_twin.core.chat_dissector import (
    ChatDissector, ConcurrentStagingBuffer, ShardDomain, ShardCategory, ChatShard
)
from sandbox.mind_twin.core.relational_cortex import RelationalCortex
from sandbox.mind_twin.core.feed_lens import FeedLens, LensMode, VisibleShard, FoldedSegment


class TestChatDissector(unittest.TestCase):
    def setUp(self):
        self.dissector = ChatDissector()
        self.staging = ConcurrentStagingBuffer(capacity=10)

    def test_staging_buffer_concurrency(self):
        def worker(start_idx):
            for i in range(15):
                self.staging.push(
                    turn_id=f"turn_{start_idx}_{i}",
                    turn_index=start_idx + i,
                    role="user" if i % 2 == 0 else "assistant",
                    text=f"Blender coordinate test message {i} with Godot mesh basis"
                )

        threads = [threading.Thread(target=worker, args=(i * 100,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        staged = self.staging.get_staged()
        self.assertLessEqual(len(staged), 10)
        # Check reinforcement on earlier items
        total_reinforced = sum(item.reinforced_hits for item in staged)
        self.assertGreater(total_reinforced, 0)
        self.assertGreater(staged[0].reinforced_hits, 0)

    def test_epistemic_classification(self):
        # 3D Invariant rule
        text_3d = "Invariant rule: Blender armature basis is Z-up, but Godot 4 requires Y-up handedness. Gram-Schmidt every 50 frames."
        shards = self.dissector.dissect_turn("turn_1", 1, "user", text_3d)
        self.assertEqual(len(shards), 1)
        self.assertEqual(shards[0].domain, ShardDomain.PIPELINE_3D)
        self.assertEqual(shards[0].category, ShardCategory.INVARIANT_RULE)
        self.assertGreater(shards[0].salience, 1.5)

        # Fleet tech spec
        text_fleet = "Android satellite node ping is 45ms over Tailscale cluster 100.64.0.5."
        shards_fleet = self.dissector.dissect_turn("turn_2", 2, "gemini", text_fleet)
        self.assertEqual(shards_fleet[0].domain, ShardDomain.FLEET_TELEMETRY)
        self.assertEqual(shards_fleet[0].category, ShardCategory.TECHNICAL_SPEC)

        # Transient noise
        text_noise = "ok got it thanks"
        shards_noise = self.dissector.dissect_turn("turn_3", 3, "user", text_noise)
        self.assertEqual(shards_noise[0].category, ShardCategory.TRANSIENT_NOISE)
        self.assertLess(shards_noise[0].salience, 0.5)


class TestRelationalCortex(unittest.TestCase):
    def setUp(self):
        self.test_db = "sandbox/mind_twin/data/test_cortex_temp.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.cortex = RelationalCortex(db_path=self.test_db)
        self.dissector = ChatDissector()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_crud_and_indexing(self):
        shards = [
            ChatShard(
                shard_id="s1", source_turn_id="t1", turn_index=1, role="user",
                domain=ShardDomain.PIPELINE_3D, category=ShardCategory.INVARIANT_RULE,
                salience=1.8, content="Z-up basis is standard for Blender rigs.",
                summary="Blender Z-up standard", keywords=["blender", "basis", "rigs"]
            ),
            ChatShard(
                shard_id="s2", source_turn_id="t2", turn_index=2, role="assistant",
                domain=ShardDomain.PIPELINE_3D, category=ShardCategory.TECHNICAL_SPEC,
                salience=1.4, content="Godot 4 mesh loader transforms Z-up into Y-up via quaternion.",
                summary="Godot 4 mesh loader", keywords=["godot", "mesh", "basis"]
            ),
            ChatShard(
                shard_id="s3", source_turn_id="t3", turn_index=3, role="user",
                domain=ShardDomain.SECURITY_VAULT, category=ShardCategory.INVARIANT_RULE,
                salience=1.9, content="PyPI token is encrypted with PBKDF2 passkey.",
                summary="PyPI token encryption", keywords=["pypi", "token", "vault"]
            )
        ]
        self.cortex.batch_insert_shards(shards)
        stats = self.cortex.get_stats()
        self.assertEqual(stats["total_shards"], 3)
        self.assertEqual(stats["domains"][ShardDomain.PIPELINE_3D.value], 2)

        # Query by domain
        res_3d = self.cortex.query_shards(domain=ShardDomain.PIPELINE_3D.value)
        self.assertEqual(len(res_3d), 2)
        self.assertEqual(res_3d[0]["shard_id"], "s1")  # Higher salience first

        # Auto-linking
        links = self.cortex.auto_link_shards(shards, min_shared_keywords=1)
        self.assertGreater(links, 0)

        # BFS Traversal
        network = self.cortex.traverse_network("s1", max_depth=2)
        self.assertTrue(any(item["target_shard"] == "s2" for item in network))

        # Provenance verification
        prov = self.cortex.get_provenance("s1")
        self.assertIsNotNone(prov)
        self.assertEqual(prov["source_turn_id"], "t1")


class TestFeedLens(unittest.TestCase):
    def setUp(self):
        self.test_db = "sandbox/mind_twin/data/test_feed_lens_temp.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.cortex = RelationalCortex(db_path=self.test_db)
        self.dissector = ChatDissector()

        # Generate a synthetic conversation with 20 turns
        self.shards = []
        for i in range(20):
            if i in [2, 5, 12]:
                text = f"Blender Godot pipeline coordinate invariant {i} with mesh normals."
            elif i in [8, 9, 10, 11]:
                text = f"debug log ping ok exit 0 trace output {i}"
            else:
                text = f"General discussion note {i} about console UI layout."
            
            created = self.dissector.dissect_turn(f"t_{i}", i, "user", text)
            self.shards.extend(created)
        
        self.cortex.batch_insert_shards(self.shards)
        self.lens = FeedLens(self.cortex, viewport_height=8)

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_continuous_pagination_and_folding(self):
        # Set focus to 3D pipeline
        self.lens.update_bi_mental_focus(
            user_domain=ShardDomain.PIPELINE_3D.value,
            user_keywords=["blender", "godot", "mesh"],
            gemini_slots=["coordinate invariant", "mesh normals"]
        )

        # Render present view (scroll_offset == 0)
        proj_present = self.lens.render_projection()
        self.assertTrue(len(proj_present) > 0)
        
        # Paginate up into past
        self.lens.scroll_up(delta=5)
        proj_past = self.lens.render_projection()
        self.assertTrue(len(proj_past) > 0)

        # Check for presence of folded segment in cognitive mode
        has_fold = any(isinstance(item, FoldedSegment) for item in proj_past)
        self.assertTrue(has_fold, "Cognitive feed lens should fold consecutive low-salience turns")

    def test_lens_modes(self):
        # Raw mode
        self.lens.set_mode(LensMode.RAW)
        raw_proj = self.lens.render_projection()
        self.assertFalse(any(isinstance(item, FoldedSegment) for item in raw_proj))

        # Decision cards mode
        self.lens.set_mode(LensMode.DECISION_CARDS)
        cards_proj = self.lens.render_projection()
        for item in cards_proj:
            self.assertIn(item.category, [ShardCategory.INVARIANT_RULE.value, ShardCategory.TECHNICAL_SPEC.value, ShardCategory.PROJECT_ANCHOR.value])


class TestHistoricalCorpusBenchmark(unittest.TestCase):
    """
    Ingests the duplicated historical chat turns from sandbox/mind_twin/data/chats_source/
    and benchmarks relational sharding, retrieval latency, and bi-mental feed projection.
    """
    def test_historical_ingestion_and_speed(self):
        chats_path = "sandbox/mind_twin/data/chats_source/segment_0.json"
        if not os.path.exists(chats_path):
            self.skipTest(f"Historical chat source {chats_path} not found")

        with open(chats_path, "r", encoding="utf-8") as f:
            turns = json.load(f)

        db_path = "sandbox/mind_twin/data/cortex_benchmark.db"
        if os.path.exists(db_path):
            os.remove(db_path)

        cortex = RelationalCortex(db_path=db_path)
        dissector = ChatDissector()

        # 1. Measure Ingestion Speed
        t0 = time.perf_counter()
        all_shards = []
        for idx, turn in enumerate(turns):
            text = turn.get("text", "")
            turn_id = turn.get("turn_id", f"t_{idx}")
            role = turn.get("role", "unknown")
            ts = turn.get("timestamp", time.time())
            shards = dissector.dissect_turn(turn_id, idx, role, text, ts)
            all_shards.extend(shards)

        cortex.batch_insert_shards(all_shards)
        ingestion_time = time.perf_counter() - t0

        print(f"\n[BENCHMARK] Ingested {len(turns)} turns into {len(all_shards)} shards in {ingestion_time*1000:.2f}ms")

        # 2. Measure Auto-link associative hyperedges
        t1 = time.perf_counter()
        links = cortex.auto_link_shards(all_shards, min_shared_keywords=2)
        link_time = time.perf_counter() - t1
        print(f"[BENCHMARK] Auto-linked {links} associative hyperedges in {link_time*1000:.2f}ms")

        # 3. Latency Benchmark: Relational Query vs Flat Text Search
        # Relational lookup
        t2 = time.perf_counter()
        relational_results = cortex.query_shards(domain=ShardDomain.PIPELINE_3D.value, limit=7)
        relational_latency = (time.perf_counter() - t2) * 1000

        # Flat text linear scan over raw turns
        t3 = time.perf_counter()
        flat_results = []
        for turn in turns:
            text = turn.get("text", "")
            if "blender" in text.lower() or "godot" in text.lower():
                flat_results.append(turn)
            if len(flat_results) >= 7:
                break
        flat_latency = (time.perf_counter() - t3) * 1000

        print(f"[BENCHMARK] Relational Index Query: {relational_latency:.3f}ms (Returned {len(relational_results)} high-salience shards)")
        print(f"[BENCHMARK] Flat Text Linear Search: {flat_latency:.3f}ms")
        self.assertLess(relational_latency, 15.0, "Relational lookup must be sub-15ms")

        # 4. Feed Lens Projection Render Latency
        lens = FeedLens(cortex, viewport_height=20)
        lens.update_bi_mental_focus(
            user_domain=ShardDomain.PIPELINE_3D.value,
            user_keywords=["blender", "godot", "shader", "armature"],
            gemini_slots=["basis", "gram-schmidt", "pbr"]
        )

        t4 = time.perf_counter()
        projection = lens.render_projection()
        render_latency = (time.perf_counter() - t4) * 1000
        print(f"[BENCHMARK] Bi-Mental Feed Lens Projection Render: {render_latency:.3f}ms ({len(projection)} items in viewport)")
        self.assertLess(render_latency, 25.0, "Feed projection must render in sub-25ms for smooth terminal scrolling")

        # Clean up benchmark db
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    unittest.main()
