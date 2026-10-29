# Studysource: Brush Kinematics Bridge
# Translates recorded LiveWire study brush dynamics (pressure, cadence, jerk, curvature)
# into Godot/Photon kinematic solver profiles for combat follow-through, surface denting,
# and procedural IK locomotion.

class_name StudySourceKinematics
extends RefCounted

# Archetype mapping to kinematic impulse behaviors
enum KinematicStudyType {
	CLAY_BUILDUP, # Organic accumulation, swelling mass curve
	CREASE_PINCH, # Sharp localized focal denting / slice
	FLATTEN_PLANE,# Planar surface compression & hard stop
	MOVE_GRAB,    # Structural displacement & biological recoil
	SMOOTH_RELAX  # High-frequency damping / decay dissipation
}

# Ingested study profile resource
class StudyKinematicProfile:
	var archetype_name: String
	var peak_impulse: float = 1.0
	var average_drag: float = 0.5
	var jerk_variance: float = 0.1
	var attack_curve: Array[float] = []
	var curvature_profile: Array[float] = []

	func sample_attack_impulse(progress: float) -> float:
		if attack_curve.is_empty():
			return 1.0
		var clamped_p = clampf(progress, 0.0, 1.0)
		var index_float = clamped_p * float(attack_curve.size() - 1)
		var idx = int(index_float)
		var frac = index_float - float(idx)
		if idx >= attack_curve.size() - 1:
			return attack_curve[attack_curve.size() - 1]
		return lerpf(attack_curve[idx], attack_curve[idx + 1], frac)


# Factory method: parses JSON exported from LiveWire's BrushKinematicsExtractor
static func load_from_study_dict(data: Dictionary) -> StudyKinematicProfile:
	var profile = StudyKinematicProfile.new()
	profile.archetype_name = data.get("archetype", "unknown")
	profile.peak_impulse = data.get("peak_pressure", 1.0) * data.get("peak_speed", 1.0)
	profile.average_drag = data.get("avg_speed", 0.5)
	profile.jerk_variance = data.get("jerk_variance", 0.1)
	
	var raw_curve = data.get("attack_curve", [])
	for val in raw_curve:
		profile.attack_curve.append(float(val))
		
	var raw_curv = data.get("curvature_profile", [])
	for val in raw_curv:
		profile.curvature_profile.append(float(val))
		
	return profile


# Applies biological stroke kinematics to an ongoing physical impulse
static func modulate_kinetic_impact(
	base_force: Vector3,
	progress: float,
	profile: StudyKinematicProfile
) -> Vector3:
	if profile == null:
		return base_force
	var mod = profile.sample_attack_impulse(progress)
	return base_force * mod
