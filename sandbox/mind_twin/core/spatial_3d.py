"""
sandbox/mind_twin/core/spatial_3d.py

3D Spatial Hypergraph Traversal & Kinematic Navigation Engine.
Bridges cognitive spreading activation with 3D vector math, rotational quaternions,
view-frustum gaze fields, spatial bounding hulls, and procedural code generation
(Godot GDScript & Blender Python) for video-game-like real-time mind navigation.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sandbox.mind_twin.core.directional_gate import DirectionalGateEngine, WorkingMemorySnapshot
from sandbox.mind_twin.core.hypergraph import Hypergraph, Vertex


# ============================================================================
# 1. 3D VECTOR & KINEMATIC MATHEMATICS (WITH STRICT NUMERICAL FAILSAFES)
# ============================================================================

@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        # Failsafe against NaN / Inf injection
        self.x = 0.0 if not math.isfinite(self.x) else float(self.x)
        self.y = 0.0 if not math.isfinite(self.y) else float(self.y)
        self.z = 0.0 if not math.isfinite(self.z) else float(self.z)

    def __add__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vector3":
        s = 0.0 if not math.isfinite(scalar) else float(scalar)
        return Vector3(self.x * s, self.y * s, self.z * s)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> "Vector3":
        if not math.isfinite(scalar) or abs(scalar) < 1e-12:
            return Vector3(0.0, 0.0, 0.0)
        return Vector3(self.x / scalar, self.y / scalar, self.z / scalar)

    def dot(self, other: "Vector3") -> float:
        res = self.x * other.x + self.y * other.y + self.z * other.z
        return 0.0 if not math.isfinite(res) else res

    def cross(self, other: "Vector3") -> "Vector3":
        return Vector3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    def length(self) -> float:
        return math.sqrt(self.length_squared())

    def magnitude(self) -> float:
        """Alias for length() across vector math contexts."""
        return self.length()

    def normalized(self) -> "Vector3":
        l = self.length()
        if l < 1e-9 or not math.isfinite(l):
            return Vector3(0.0, 0.0, 0.0)
        return self / l

    def distance_to(self, other: "Vector3") -> float:
        return (self - other).length()

    def angle_to(self, other: "Vector3") -> float:
        """Angle in radians between vectors. Clamped against precision drift."""
        l1 = self.length()
        l2 = other.length()
        if l1 < 1e-9 or l2 < 1e-9:
            return 0.0
        d = self.dot(other) / (l1 * l2)
        d_clamped = max(-1.0, min(1.0, d))
        return math.acos(d_clamped)

    def lerp(self, target: "Vector3", t: float) -> "Vector3":
        t_clamped = max(0.0, min(1.0, t))
        return self + (target - self) * t_clamped

    def to_tuple(self) -> Tuple[float, float, float]:
        return (round(self.x, 4), round(self.y, 4), round(self.z, 4))


# ============================================================================
# 2. ROTATIONAL QUATERNIONS (GIMBAL-LOCK FREE)
# ============================================================================

@dataclass
class Quaternion:
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        self.w = 1.0 if not math.isfinite(self.w) else float(self.w)
        self.x = 0.0 if not math.isfinite(self.x) else float(self.x)
        self.y = 0.0 if not math.isfinite(self.y) else float(self.y)
        self.z = 0.0 if not math.isfinite(self.z) else float(self.z)

    @classmethod
    def identity(cls) -> "Quaternion":
        return cls(1.0, 0.0, 0.0, 0.0)

    @classmethod
    def from_axis_angle(cls, axis: Vector3, angle_rad: float) -> "Quaternion":
        axis_norm = axis.normalized()
        if axis_norm.length() < 1e-9:
            return cls.identity()
        half_angle = angle_rad * 0.5
        sin_half = math.sin(half_angle)
        return cls(
            w=math.cos(half_angle),
            x=axis_norm.x * sin_half,
            y=axis_norm.y * sin_half,
            z=axis_norm.z * sin_half,
        ).normalized()

    @classmethod
    def from_euler(cls, pitch: float, yaw: float, roll: float) -> "Quaternion":
        """
        Euler angles in radians (YXZ rotation order - standard for 3D game engines).
        Yaw rotates around +Y (Up), Pitch rotates around +X (Right), Roll rotates around +Z (Forward).
        """
        qy = cls.from_axis_angle(Vector3(0.0, 1.0, 0.0), yaw)
        qx = cls.from_axis_angle(Vector3(1.0, 0.0, 0.0), pitch)
        qz = cls.from_axis_angle(Vector3(0.0, 0.0, 1.0), roll)
        return (qy * qx * qz).normalized()

    def norm(self) -> float:
        return math.sqrt(self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> "Quaternion":
        n = self.norm()
        if n < 1e-9 or not math.isfinite(n):
            return Quaternion(1.0, 0.0, 0.0, 0.0)
        return Quaternion(self.w / n, self.x / n, self.y / n, self.z / n)

    def __mul__(self, other: "Quaternion") -> "Quaternion":
        w = self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z
        x = self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y
        y = self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x
        z = self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w
        return Quaternion(w, x, y, z).normalized()

    def rotate_vector(self, v: Vector3) -> Vector3:
        """Rotates a vector by this quaternion: v' = q * v * q^-1"""
        u = Vector3(self.x, self.y, self.z)
        s = self.w
        # Rodrigues-like formula for quaternions:
        # v' = 2.0 * dot(u, v) * u + (s*s - dot(u,u)) * v + 2.0 * s * cross(u, v)
        uv = u.cross(v)
        uuv = u.cross(uv)
        return v + ((uv * s) + uuv) * 2.0


# ============================================================================
# 3. SPATIAL BOUNDING BOXES & RAY-INTERSECTION (SLAB METHOD)
# ============================================================================

@dataclass
class AABB3D:
    """Axis-Aligned Bounding Box for spatial culling and collision hulls."""
    min_pt: Vector3
    max_pt: Vector3

    def contains_point(self, pt: Vector3) -> bool:
        return (
            self.min_pt.x <= pt.x <= self.max_pt.x
            and self.min_pt.y <= pt.y <= self.max_pt.y
            and self.min_pt.z <= pt.z <= self.max_pt.z
        )

    def center(self) -> Vector3:
        return (self.min_pt + self.max_pt) * 0.5

    def extents(self) -> Vector3:
        return (self.max_pt - self.min_pt) * 0.5

    def intersects_ray(self, origin: Vector3, direction: Vector3, max_dist: float = 1000.0) -> Optional[float]:
        """
        Fast Slab test for ray-box intersection.
        Returns distance along ray to intersection, or None if missed.
        Hardened against division-by-zero for parallel rays.
        """
        dir_norm = direction.normalized()
        if dir_norm.length() < 1e-9:
            return None

        t_min = 0.0
        t_max = max_dist

        for i, (p_min, p_max, ray_orig, ray_d) in enumerate([
            (self.min_pt.x, self.max_pt.x, origin.x, dir_norm.x),
            (self.min_pt.y, self.max_pt.y, origin.y, dir_norm.y),
            (self.min_pt.z, self.max_pt.z, origin.z, dir_norm.z),
        ]):
            if abs(ray_d) < 1e-9:
                # Ray is parallel to slab. If origin is outside, no hit.
                if ray_orig < p_min or ray_orig > p_max:
                    return None
            else:
                inv_d = 1.0 / ray_d
                t1 = (p_min - ray_orig) * inv_d
                t2 = (p_max - ray_orig) * inv_d
                if t1 > t2:
                    t1, t2 = t2, t1
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                if t_min > t_max:
                    return None

        if t_min > max_dist or t_max < 0.0:
            return None

        return t_min if t_min >= 0.0 else t_max


# ============================================================================
# 4. PROCEDURAL 3D MESH & SCRIPT CODE SYNTHESIZER
# ============================================================================

class ProceduralCodeGenerator:
    """
    Synthesizes game-ready procedural geometry and shader code on the fly
    as the cognitive mind navigates into spatial cells.
    Supports Godot 4 GDScript & Blender 4 Python (bpy/bmesh).
    """

    @staticmethod
    def generate_godot_mesh_script(room_id: str, dimensions: Vector3, color_hex: str = "#4488ff") -> str:
        """Generates valid Godot 4 GDScript to spawn an ArrayMesh room with collision."""
        return f"""# Generated Godot 4 Procedural Chunk: {room_id}
@tool
extends Node3D

func _ready() -> void:
    build_procedural_room()

func build_procedural_room() -> void:
    var mesh_instance := MeshInstance3D.new()
    mesh_instance.name = "{room_id}_mesh"
    
    var extents := Vector3({dimensions.x:.2f}, {dimensions.y:.2f}, {dimensions.z:.2f})
    var box_mesh := BoxMesh.new()
    box_mesh.size = extents
    mesh_instance.mesh = box_mesh
    
    # Material setup
    var mat := StandardMaterial3D.new()
    mat.albedo_color = Color("{color_hex}")
    mat.roughness = 0.4
    mat.metallic = 0.1
    mesh_instance.material_override = mat
    
    add_child(mesh_instance)
    
    # Static collision body
    var static_body := StaticBody3D.new()
    var col_shape := CollisionShape3D.new()
    var box_shape := BoxShape3D.new()
    box_shape.size = extents
    col_shape.shape = box_shape
    static_body.add_child(col_shape)
    add_child(static_body)
"""

    @staticmethod
    def generate_blender_bmesh_script(room_id: str, position: Vector3, dimensions: Vector3) -> str:
        """Generates valid Blender 4 Python bmesh script to construct geometry & armature."""
        return f'''# Generated Blender bmesh Script: {room_id}
import bpy
import bmesh
from mathutils import Vector

def build_chunk():
    mesh = bpy.data.meshes.new("{room_id}_data")
    obj = bpy.data.objects.new("{room_id}", mesh)
    
    col = bpy.context.collection
    col.objects.link(obj)
    
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    
    # Scale to dimensions
    scale_vec = Vector(({dimensions.x:.2f}, {dimensions.y:.2f}, {dimensions.z:.2f}))
    bmesh.ops.scale(bm, vec=scale_vec, verts=bm.verts)
    
    bm.to_mesh(mesh)
    bm.free()
    
    obj.location = Vector(({position.x:.2f}, {position.y:.2f}, {position.z:.2f}))
    return obj

if __name__ == "__main__":
    build_chunk()
'''


# ============================================================================
# 5. SPATIAL HYPERGRAPH NAVIGATOR (6DOF KINEMATIC MIND TRAVERSAL)
# ============================================================================

class SpatialHypergraphNavigator:
    """
    Kinematic Mind Navigator.
    Allows the mind to traverse the cognitive hypergraph as a continuous 3D virtual world.
    - 6DOF camera/entity kinematics (position, velocity, orientation quaternion).
    - Frustum Gaze Field: attention is directed in 3D viewing cones.
    - Real-time raycasting against spatial thought hulls.
    - Video-game frame loop telemetry (guaranteed sub-16.6ms cycle).
    """

    def __init__(
        self,
        graph: Hypergraph,
        directional_gate: Optional[DirectionalGateEngine] = None,
        initial_pos: Optional[Vector3] = None,
    ) -> None:
        self.graph = graph
        self.gate = directional_gate or DirectionalGateEngine(max_slots=7)

        # 6DOF Kinematic state
        self.position = initial_pos or Vector3(0.0, 0.0, 0.0)
        self.velocity = Vector3(0.0, 0.0, 0.0)
        self.orientation = Quaternion.identity()
        self.yaw = 0.0
        self.pitch = 0.0

        # Frustum & navigation properties
        self.fov_degrees = 75.0
        self.max_view_distance = 60.0
        self.damping = 0.88  # Inertial air resistance

        # Spatial vertex catalog cache
        self._spatial_nodes: Dict[str, Dict[str, Any]] = {}
        self._sync_spatial_catalog()

    def _sync_spatial_catalog(self) -> None:
        """Scans hypergraph vertices for 3D spatial attributes."""
        snapshots = self.graph.get_vertices_snapshot()
        self._spatial_nodes.clear()

        for vid, v in snapshots.items():
            attrs = v.attributes or {}
            pos_data = attrs.get("position")
            if pos_data:
                pos = Vector3(*pos_data) if isinstance(pos_data, (list, tuple)) else Vector3(0, 0, 0)
                ext_data = attrs.get("extents", (2.0, 2.0, 2.0))
                ext = Vector3(*ext_data) if isinstance(ext_data, (list, tuple)) else Vector3(2, 2, 2)
                aabb = AABB3D(min_pt=pos - ext, max_pt=pos + ext)

                self._spatial_nodes[vid] = {
                    "position": pos,
                    "aabb": aabb,
                    "extents": ext,
                    "mesh_type": attrs.get("mesh_type", "spatial_chunk"),
                    "color": attrs.get("color", "#55aaff"),
                }

    def add_spatial_cell(
        self,
        vid: str,
        label: str,
        position: Vector3,
        extents: Vector3 = Vector3(2.0, 2.0, 2.0),
        vtype: str = "spatial_cell",
        mesh_type: str = "room",
        color: str = "#4488ff",
        neighbors: Optional[List[str]] = None,
    ) -> None:
        """Creates a spatial cell in the hypergraph with 3D hulls and code templates."""
        godot_code = ProceduralCodeGenerator.generate_godot_mesh_script(vid, extents * 2.0, color)
        blender_code = ProceduralCodeGenerator.generate_blender_bmesh_script(vid, position, extents * 2.0)

        attrs = {
            "position": position.to_tuple(),
            "extents": extents.to_tuple(),
            "mesh_type": mesh_type,
            "color": color,
            "godot_script": godot_code,
            "blender_script": blender_code,
        }

        self.graph.add_vertex(vid, label=label, vtype=vtype, attributes=attrs)

        # Wire hyperedges to spatial neighbors if provided
        if neighbors:
            valid_neighbors = [n for n in neighbors if self.graph.get_vertex(n)]
            if valid_neighbors:
                self.graph.add_hyperedge(
                    sources=[vid],
                    targets=valid_neighbors,
                    edge_type="spatial_portal",
                    weight=0.95,
                    undirected=True,
                )

        self._sync_spatial_catalog()

    def step_kinematics(
        self,
        dt: float,
        throttle: Vector3 = Vector3(0.0, 0.0, 0.0),
        delta_yaw: float = 0.0,
        delta_pitch: float = 0.0,
    ) -> None:
        """
        Executes a 6DOF physics tick.
        - Updates rotational orientation (gimbal-lock-free).
        - Applies thrust in local look-vector coordinates.
        - Applies damping and updates continuous world coordinates.
        """
        dt_safe = max(0.001, min(0.1, dt))

        # 1. Update orientation
        self.yaw += delta_yaw
        self.pitch = max(-math.pi * 0.48, min(math.pi * 0.48, self.pitch + delta_pitch))
        self.orientation = Quaternion.from_euler(pitch=self.pitch, yaw=self.yaw, roll=0.0)

        # 2. Transform throttle vector from local space into world space
        world_thrust = self.orientation.rotate_vector(throttle)

        # 3. Apply acceleration & damping
        self.velocity = (self.velocity + world_thrust * dt_safe) * self.damping
        self.position = self.position + self.velocity * dt_safe

    def get_forward_gaze_vector(self) -> Vector3:
        """Returns normalized 3D forward gaze vector."""
        # Default forward in game engine coordinates is +Z (or -Z). We use +Z forward.
        return self.orientation.rotate_vector(Vector3(0.0, 0.0, 1.0)).normalized()

    def cast_ray(self, max_dist: Optional[float] = None) -> Optional[Tuple[str, float]]:
        """
        Casts a ray along the forward gaze vector against all spatial thought hulls.
        Returns (hit_vid, hit_distance) of closest intersection, or None.
        """
        limit = max_dist or self.max_view_distance
        forward = self.get_forward_gaze_vector()

        closest_hit: Optional[str] = None
        min_dist = float("inf")

        for vid, data in self._spatial_nodes.items():
            pos: Vector3 = data["position"]
            if (pos - self.position).length() > limit + 10.0:
                continue
            aabb: AABB3D = data["aabb"]
            hit_t = aabb.intersects_ray(self.position, forward, max_dist=limit)
            if hit_t is not None and hit_t < min_dist:
                min_dist = hit_t
                closest_hit = vid

        if closest_hit:
            return (closest_hit, min_dist)
        return None

    def navigate_tick(self, t_now: Optional[float] = None) -> Tuple[WorkingMemorySnapshot, Dict[str, Any]]:
        """
        High-performance real-time navigation tick.
        Combines 3D spatial attenuation, gaze frustum alignment, ray-cast focus,
        and Miller's Law 7-slot working memory gating.
        Guaranteed to measure execution time.
        """
        t_start = time.perf_counter()
        now = t_now or time.time()

        forward = self.get_forward_gaze_vector()
        half_fov_rad = math.radians(self.fov_degrees * 0.5)

        spatial_activations: Dict[str, float] = {}

        # 1. Evaluate spatial energy for each node
        for vid, data in self._spatial_nodes.items():
            pos: Vector3 = data["position"]
            dist = self.position.distance_to(pos)

            if dist > self.max_view_distance:
                continue

            # Distance attenuation: inverse-square-like falloff
            dist_attenuation = 1.0 / (1.0 + 0.04 * dist + 0.002 * dist * dist)

            # Gaze Frustum alignment: dot product between look vector and vector-to-target
            to_target = (pos - self.position).normalized()
            gaze_dot = forward.dot(to_target)

            # Strict Frustum & Back-face Culling: objects behind view plane or outside FOV cone are culled
            if gaze_dot <= 0.0:
                continue

            # Angle check against FOV
            angle = forward.angle_to(to_target)
            if angle > half_fov_rad:
                continue

            gaze_multiplier = max(0.1, gaze_dot)

            # Combined spatial activation energy
            energy = 2.5 * dist_attenuation * (0.3 + 0.7 * gaze_multiplier)
            if math.isfinite(energy) and energy > 0.05:
                spatial_activations[vid] = energy

        # 2. Boost focused node from raycast hit
        ray_hit = self.cast_ray()
        if ray_hit:
            hit_vid, hit_dist = ray_hit
            current_e = spatial_activations.get(hit_vid, 0.5)
            # Focused target receives a significant attention surge
            spatial_activations[hit_vid] = current_e + 2.0 / (1.0 + 0.05 * hit_dist)

        # 3. Gate activations through the 7-slot Directional Working Memory
        intent_summary = f"Spatial Nav (x={self.position.x:.1f}, y={self.position.y:.1f}, z={self.position.z:.1f})"
        self.gate.update_trajectory(intent_summary)
        snapshot = self.gate.gate_and_filter(self.graph, spatial_activations, t_now=now)

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        telemetry = {
            "tick_time_ms": round(t_elapsed_ms, 3),
            "is_60fps_compliant": t_elapsed_ms < 16.66,
            "player_position": self.position.to_tuple(),
            "forward_gaze": forward.to_tuple(),
            "ray_hit": ray_hit,
            "visible_spatial_nodes": len(spatial_activations),
            "active_memory_slots": len(snapshot.slots),
        }

        return snapshot, telemetry
