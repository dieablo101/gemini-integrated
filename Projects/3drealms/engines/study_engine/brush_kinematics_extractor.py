"""
Brush Kinematics Study Source Bridge
====================================
Extracts biological human motor dynamics, stroke cadence, pressure curves,
and surface-deformation kernels from LiveWire study sessions and exports them
as game engine kinematic profiles for runtime combat, deformation, and locomotion.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import json
import math
import os
import numpy as np


@dataclass
class KinematicStrokeSample:
    t: float
    dt: float
    pos: List[float]
    velocity: List[float]
    acceleration: List[float]
    jerk: List[float]
    speed: float
    pressure: float
    curvature: float
    tangent: List[float]
    normal: List[float]


@dataclass
class ExtractedKinematicProfile:
    archetype: str
    duration: float
    sample_count: int
    peak_speed: float
    avg_speed: float
    peak_pressure: float
    avg_pressure: float
    impulse_integral: float
    jerk_variance: float
    attack_curve: List[float]      # Normalized 0.0..1.0 attack/build profile
    release_curve: List[float]     # Normalized 0.0..1.0 decay/follow-through profile
    curvature_profile: List[float] # Normalized stroke curvature over time
    samples: List[KinematicStrokeSample] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def export_godot_curve_resource(self, output_tres_path: str) -> None:
        """Exports the normalized dynamic curve as a Godot Engine Curve resource (.tres)."""
        os.makedirs(os.path.dirname(os.path.abspath(output_tres_path)), exist_ok=True)
        points: List[str] = []
        n = len(self.attack_curve)
        if n > 0:
            for idx, val in enumerate(self.attack_curve):
                pos_x = idx / max(1, (n - 1))
                points.append(f"{pos_x:.4f}, {val:.4f}, 0.0, 0.0, 0, 0")
        
        tres_content = (
            "[gd_resource type=\"Curve\" format=3]\n\n"
            "[resource]\n"
            f"_data = [Vector2({', '.join(points)})]\n"
            f"point_count = {len(points)}\n"
        )
        with open(output_tres_path, "w", encoding="utf-8") as f:
            f.write(tres_content)


class BrushKinematicsExtractor:
    """
    Extracts raw stroke series into engine kinematics:
    - Attack/release impulse curves for melee hits & recoil
    - Velocity and acceleration profiles for procedural animations
    - Deformation kernels for dynamic mesh impact and terrain displacement
    """

    @staticmethod
    def extract_from_stroke_samples(
        archetype: str,
        positions: np.ndarray,      # shape (N, 3)
        timestamps: np.ndarray,     # shape (N,)
        pressures: Optional[np.ndarray] = None  # shape (N,)
    ) -> ExtractedKinematicProfile:
        n = len(positions)
        if n < 2:
            return ExtractedKinematicProfile(
                archetype=archetype,
                duration=0.0,
                sample_count=n,
                peak_speed=0.0,
                avg_speed=0.0,
                peak_pressure=0.0,
                avg_pressure=0.0,
                impulse_integral=0.0,
                jerk_variance=0.0,
                attack_curve=[],
                release_curve=[],
                curvature_profile=[]
            )

        if pressures is None or len(pressures) != n:
            pressures = np.ones(n, dtype=np.float32)

        # Compute intervals
        dt = np.diff(timestamps)
        dt = np.where(dt <= 1e-6, 1e-4, dt) # clamp division by zero

        # Velocity (N-1, 3)
        vel = np.diff(positions, axis=0) / dt[:, np.newaxis]
        speeds = np.linalg.norm(vel, axis=1)

        # Acceleration (N-2, 3)
        acc = np.zeros((max(0, n - 2), 3), dtype=np.float32)
        if len(dt) > 1:
            dt_mid = 0.5 * (dt[:-1] + dt[1:])
            dt_mid = np.where(dt_mid <= 1e-6, 1e-4, dt_mid)
            acc = np.diff(vel, axis=0) / dt_mid[:, np.newaxis]

        # Jerk (N-3, 3)
        jerk = np.zeros((max(0, n - 3), 3), dtype=np.float32)
        if len(acc) > 1:
            dt_acc = 0.5 * (dt_mid[:-1] + dt_mid[1:])
            dt_acc = np.where(dt_acc <= 1e-6, 1e-4, dt_acc)
            jerk = np.diff(acc, axis=0) / dt_acc[:, np.newaxis]

        # Curvature calculation: kappa = |v x a| / |v|^3
        curvatures = []
        for i in range(len(acc)):
            v_i = vel[i]
            a_i = acc[i]
            speed_i = speeds[i]
            if speed_i > 1e-4:
                cross_mag = np.linalg.norm(np.cross(v_i, a_i))
                kappa = cross_mag / (speed_i ** 3)
                curvatures.append(float(kappa))
            else:
                curvatures.append(0.0)

        # Normalized dynamic curves (resampled to 16-point standard profile)
        resample_count = 16
        t_norm = (timestamps - timestamps[0]) / max(1e-4, (timestamps[-1] - timestamps[0]))
        xp = t_norm[:len(speeds)]
        target_x = np.linspace(0.0, 1.0, resample_count)

        if len(xp) > 1:
            speed_curve = np.interp(target_x, xp, speeds)
            pressure_curve = np.interp(target_x, t_norm, pressures)
            # Combine speed x pressure for kinetic work / impulse curve
            impulse_curve = speed_curve * pressure_curve
            max_imp = np.max(impulse_curve) if np.max(impulse_curve) > 1e-5 else 1.0
            attack_norm = (impulse_curve / max_imp).tolist()
        else:
            attack_norm = [1.0] * resample_count

        total_duration = float(timestamps[-1] - timestamps[0])
        peak_spd = float(np.max(speeds)) if len(speeds) > 0 else 0.0
        avg_spd = float(np.mean(speeds)) if len(speeds) > 0 else 0.0
        peak_prs = float(np.max(pressures)) if len(pressures) > 0 else 0.0
        avg_prs = float(np.mean(pressures)) if len(pressures) > 0 else 0.0
        impulse_int = float(np.sum(speeds * dt)) if len(speeds) > 0 else 0.0
        jerk_var = float(np.var(jerk)) if len(jerk) > 0 else 0.0

        return ExtractedKinematicProfile(
            archetype=archetype,
            duration=total_duration,
            sample_count=n,
            peak_speed=peak_spd,
            avg_speed=avg_spd,
            peak_pressure=peak_prs,
            avg_pressure=avg_prs,
            impulse_integral=impulse_int,
            jerk_variance=jerk_var,
            attack_curve=attack_norm,
            release_curve=list(reversed(attack_norm)),
            curvature_profile=curvatures[:resample_count]
        )
