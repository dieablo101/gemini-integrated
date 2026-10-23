"""
sandbox/mind_twin/tests/test_epiphany_storms.py

Stress tests for Subconscious Incubation & Epiphany Storms (Frontier 3).
Tests:
- Ring buffer saturation & lockless throughput under 10,000 concurrent epiphanies.
- Working memory slot 1 hijack prevention against rogue epiphanies.
- 60 FPS foreground tick preservation under heavy multi-threaded collision storms.
"""

import threading
import time
import unittest

from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine
from sandbox.mind_twin.core.hypergraph import Hypergraph
from sandbox.mind_twin.core.spatial_3d import SpatialHypergraphNavigator, Vector3
from sandbox.mind_twin.core.subconscious.epiphany_channel import EpiphanyChannel, EpiphanyPacket
from sandbox.mind_twin.core.subconscious.subconscious_worker import SubconsciousWorker


class TestEpiphanyStorms(unittest.TestCase):

    def test_ring_buffer_saturation_and_contention(self):
        """8 threads pushing 10,000 epiphanies into a 16-capacity ring buffer must never deadlock or leak."""
        channel = EpiphanyChannel(capacity=16)
        total_pushed = 0
        lock = threading.Lock()

        def worker_flood(worker_id: int):
            nonlocal total_pushed
            for i in range(1250):
                pkt = EpiphanyPacket(
                    packet_id=f"storm_{worker_id}_{i}",
                    spark_name=f"Spark {i}",
                    domain_bridge=["telemetry", "3d_engine"],
                    feasibility_score=0.85,
                    summary="Test breakthrough hypothesis under storm.",
                )
                channel.push(pkt)
                with lock:
                    total_pushed += 1

        threads = [threading.Thread(target=worker_flood, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(total_pushed, 10000)
        self.assertLessEqual(channel.size(), 16)
        # Drain all packets
        drained = channel.drain_all()
        self.assertEqual(len(drained), 16)
        self.assertTrue(channel.is_empty())

    def test_attention_hijack_prevention(self):
        """Working memory slot 1 (urgent user directive) must resist eviction from incoming epiphanies."""
        hg = Hypergraph()
        gate = DirectionalGateEngine(max_slots=7)

        # Core user directive with high energy
        hg.add_vertex("directive_safety", label="URGENT_SAFETY_PROTOCOL", vtype="anchor", base_energy=5.0)

        # 20 background epiphanies with moderate feasibility (0.75 - 0.85)
        for i in range(20):
            vid = f"epiphany_{i}"
            hg.add_vertex(vid, label=f"Epiphany {i}", vtype="epiphany", base_energy=1.5 + (i * 0.05))

        activations = {f"epiphany_{i}": 1.5 + (i * 0.05) for i in range(20)}
        activations["directive_safety"] = 10.0  # Dominant focus

        gate.update_trajectory("Execute safety protocol")
        snapshot = gate.gate_and_filter(hg, activations)

        # Verify Slot 1 is firmly anchored
        self.assertGreater(len(snapshot.slots), 0)
        slot_1 = snapshot.slots[0]
        self.assertEqual(slot_1.target_id, "directive_safety")
        # Ensure Miller's law bounds are strictly maintained
        self.assertLessEqual(len(snapshot.slots), 7)

    def test_foreground_tick_under_collision_storm(self):
        """Foreground spatial 60 FPS navigation loop must maintain sub-16.6ms frame time while workers collide."""
        hg = Hypergraph()
        # Seed graph with disparate domains
        for i in range(50):
            hg.add_vertex(f"sensory_{i}", label=f"Sensor Stream {i}", vtype="sensor", attributes={"topic": "stream", "lux": 200.0})
            hg.add_vertex(f"mesh_{i}", label=f"Godot Mesh {i}", vtype="mesh", attributes={"topic": "engine", "faces": 500})

        nav = SpatialHypergraphNavigator(hg, initial_pos=Vector3(0, 0, 0))
        for i in range(20):
            nav.add_spatial_cell(f"cell_{i}", f"Room {i}", Vector3(float(i * 3), 0.0, float(i * 3)))

        stop_workers = threading.Event()
        collision_count = 0

        def collision_runner():
            nonlocal collision_count
            worker = SubconsciousWorker(hg)
            worker.is_incubating = True
            while not stop_workers.is_set():
                worker.run_incubation_cycle()
                collision_count += 1
                time.sleep(0.0005)

        workers = [threading.Thread(target=collision_runner) for _ in range(3)]
        for w in workers:
            w.daemon = True
            w.start()

        # Run 50 foreground navigation ticks
        tick_durations = []
        for _ in range(50):
            nav.step_kinematics(dt=0.016, throttle=Vector3(0.5, 0.0, 1.0), delta_yaw=0.01)
            snapshot, telemetry = nav.navigate_tick()
            tick_durations.append(telemetry["tick_time_ms"])

        stop_workers.set()
        for w in workers:
            w.join(timeout=1.0)

        avg_tick = sum(tick_durations) / len(tick_durations)
        max_tick = max(tick_durations)

        self.assertLess(avg_tick, 10.0, f"Average tick {avg_tick:.2f}ms exceeded safe frame budget!")
        self.assertLess(max_tick, 25.0, f"Spike tick {max_tick:.2f}ms caused noticeable stutter!")
        self.assertGreater(collision_count, 10, "Subconscious collisions did not run sufficiently!")


if __name__ == "__main__":
    unittest.main()
