#!/usr/bin/env python3
"""
Study Spec: 100% Data-Driven Specification for 3D Asset Study Engine
---------------------------------------------------------------------
Defines declarative schemas, profiles, and configuration objects for:
- Camera vantage points & optical lenses
- Lighting rigs & 32-bit linear radiance skyboxes
- Analytical geometry, curvature, and medial axis thresholds
- Multi-tier LOD decimation & texture bake profiles
- Target game engine export schemas (Godot 4, glTF, FBX)

Every study run is 100% reproducible from a pure JSON/dictionary spec.
"""

from __future__ import annotations
import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Any


@dataclass
class CameraSpec:
    name: str
    camera_type: str = "ORTHO"  # ORTHO, PERSP
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    dist_mult: float = 2.5
    ortho_scale_mult: float = 1.25
    lens_mm: float = 50.0
    aspect_ratio: Tuple[int, int] = (1, 1)


@dataclass
class LightNodeSpec:
    name: str
    light_type: str = "SUN"  # SUN, POINT, SPOT, AREA
    energy: float = 3.0
    color: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    rotation_euler_deg: Tuple[float, float, float] = (45.0, 0.0, 0.0)
    shadow_soft_size: float = 0.1


@dataclass
class LightingRigSpec:
    name: str
    mode: str = "dense"  # flat, dense, silhouette, custom
    lights: List[LightNodeSpec] = field(default_factory=list)
    background_color: Tuple[float, float, float, float] = (0.05, 0.05, 0.07, 1.0)
    background_strength: float = 0.3
    film_transparent: bool = True


@dataclass
class EnvironmentSkyboxSpec:
    name: str
    filename: str
    strength: float = 2.2
    rotation_deg: float = 0.0
    film_transparent: bool = True
    color_space: str = "Linear Rec.709"


@dataclass
class LODTierSpec:
    tier: str  # LOD0, LOD1, LOD2
    ratio: float = 1.0  # 1.0 = 100%, 0.25 = 25%
    target_triangles: Optional[int] = None
    decimate_method: str = "COLLAPSE"  # COLLAPSE, UNSUBDIV, PLANAR
    bake_normal: bool = False
    bake_ao: bool = False
    bake_resolution: int = 2048


@dataclass
class GeometricAnalysisSpec:
    medial_spine_slices: int = 10
    planar_percentile: float = 20.0
    crease_percentile: float = 8.0
    ridge_percentile: float = 92.0
    cranial_facial_split_y_pct: float = 0.6
    compute_pca_inertia: bool = True
    compute_shape_index: bool = True
    curvature_pigment_coupling: bool = True


@dataclass
class ExportTargetSpec:
    export_fbx: bool = True
    export_glb: bool = True
    export_gltf_separate: bool = True
    godot_scene: bool = True
    collision_shape: str = "CONVEX"  # CONVEX, TRIMESH, CAPSULE_APPROX
    materials_format: str = "PBR_METALLIC_ROUGHNESS"


@dataclass
class StudyProfile:
    name: str = "default_study"
    resolution: Tuple[int, int] = (512, 512)
    eevee_samples: int = 4
    cameras: List[CameraSpec] = field(default_factory=list)
    lighting_rigs: List[LightingRigSpec] = field(default_factory=list)
    environments: List[EnvironmentSkyboxSpec] = field(default_factory=list)
    lods: List[LODTierSpec] = field(default_factory=list)
    analysis: GeometricAnalysisSpec = field(default_factory=GeometricAnalysisSpec)
    export: ExportTargetSpec = field(default_factory=ExportTargetSpec)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, filepath: str):
        with open(filepath, "w") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StudyProfile:
        cameras = [CameraSpec(**c) for c in data.get("cameras", [])]
        
        lighting_rigs = []
        for lr in data.get("lighting_rigs", []):
            lights = [LightNodeSpec(**l) for l in lr.get("lights", [])]
            lr_copy = dict(lr)
            lr_copy["lights"] = lights
            lighting_rigs.append(LightingRigSpec(**lr_copy))
            
        environments = [EnvironmentSkyboxSpec(**e) for e in data.get("environments", [])]
        lods = [LODTierSpec(**l) for l in data.get("lods", [])]
        analysis = GeometricAnalysisSpec(**data.get("analysis", {})) if "analysis" in data else GeometricAnalysisSpec()
        export = ExportTargetSpec(**data.get("export", {})) if "export" in data else ExportTargetSpec()
        
        return cls(
            name=data.get("name", "study"),
            resolution=tuple(data.get("resolution", (512, 512))),
            eevee_samples=data.get("eevee_samples", 4),
            cameras=cameras,
            lighting_rigs=lighting_rigs,
            environments=environments,
            lods=lods,
            analysis=analysis,
            export=export
        )

    @classmethod
    def load(cls, filepath: str) -> StudyProfile:
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Pre-Configured Factory Profiles
# ---------------------------------------------------------------------------

def create_canonical_cameras() -> List[CameraSpec]:
    return [
        CameraSpec(name="front", camera_type="ORTHO", yaw_deg=0.0, pitch_deg=0.0),
        CameraSpec(name="right", camera_type="ORTHO", yaw_deg=90.0, pitch_deg=0.0),
        CameraSpec(name="back", camera_type="ORTHO", yaw_deg=180.0, pitch_deg=0.0),
        CameraSpec(name="left", camera_type="ORTHO", yaw_deg=270.0, pitch_deg=0.0),
        CameraSpec(name="top", camera_type="ORTHO", yaw_deg=0.0, pitch_deg=89.9),
        CameraSpec(name="hero", camera_type="PERSP", yaw_deg=45.0, pitch_deg=25.0, dist_mult=2.3, lens_mm=50.0),
    ]


def create_canonical_lighting() -> List[LightingRigSpec]:
    flat_rig = LightingRigSpec(
        name="flat",
        mode="flat",
        lights=[],
        background_color=(1.0, 1.0, 1.0, 1.0),
        background_strength=1.0,
        film_transparent=True
    )
    
    dense_rig = LightingRigSpec(
        name="dense",
        mode="dense",
        background_color=(0.05, 0.05, 0.07, 1.0),
        background_strength=0.3,
        film_transparent=True,
        lights=[
            LightNodeSpec(name="KeyLight", light_type="SUN", energy=3.5, color=(1.0, 0.98, 0.92), rotation_euler_deg=(45, 20, -35)),
            LightNodeSpec(name="FillLight", light_type="SUN", energy=1.2, color=(0.75, 0.85, 1.0), rotation_euler_deg=(50, -30, 140)),
            LightNodeSpec(name="RimLight", light_type="SUN", energy=4.0, color=(1.0, 0.8, 0.6), rotation_euler_deg=(-60, 0, 180)),
        ]
    )
    return [flat_rig, dense_rig]


def create_canonical_environments() -> List[EnvironmentSkyboxSpec]:
    return [
        EnvironmentSkyboxSpec(name="studio_small_01", filename="studio_small_01_1k.hdr", strength=2.2),
        EnvironmentSkyboxSpec(name="mpumalanga_veld", filename="mpumalanga_veld_1k.hdr", strength=2.2),
        EnvironmentSkyboxSpec(name="venetian_crossroads", filename="venetian_crossroads_1k.hdr", strength=2.2),
        EnvironmentSkyboxSpec(name="winter_river", filename="winter_river_1k.hdr", strength=2.2),
        EnvironmentSkyboxSpec(name="moonless_golf", filename="moonless_golf_1k.hdr", strength=2.2),
    ]


def create_canonical_lods() -> List[LODTierSpec]:
    return [
        LODTierSpec(tier="LOD0", ratio=1.0, bake_normal=False),
        LODTierSpec(tier="LOD1", ratio=0.25, target_triangles=20000, bake_normal=True, bake_ao=True, bake_resolution=2048),
        LODTierSpec(tier="LOD2", ratio=0.05, target_triangles=4000, bake_normal=True, bake_ao=False, bake_resolution=1024),
    ]


def get_default_study_profile() -> StudyProfile:
    """Returns the master canonical 100% data-driven study profile."""
    return StudyProfile(
        name="canonical_master_study",
        resolution=(512, 512),
        eevee_samples=4,
        cameras=create_canonical_cameras(),
        lighting_rigs=create_canonical_lighting(),
        environments=create_canonical_environments(),
        lods=create_canonical_lods(),
        analysis=GeometricAnalysisSpec(),
        export=ExportTargetSpec(
            export_fbx=True,
            export_glb=True,
            export_gltf_separate=True,
            godot_scene=True,
            collision_shape="CONVEX"
        )
    )


if __name__ == "__main__":
    profile = get_default_study_profile()
    profile_path = os.path.join(os.path.dirname(__file__), "canonical_study_profile.json")
    profile.save(profile_path)
    print(f"[StudySpec] Successfully exported canonical data-driven profile: {profile_path}")
