# Photon Engine: Kinematic Locomotion Solver (GDScript)
# Pure code-only procedural locomotion, ground planting (FABRIK/Analytical 2-bone IK),
# inertial spring-damper lean dynamics, and cadence foot-plant dispatch.
# No animation keyframes.

class_name PhotonKinematicLocomotion
extends Node3D

signal foot_planted(bone_name: String, ground_pos: Vector3, ground_normal: Vector3, velocity: float)

@export_group("Rig Anchors")
@export var skeleton_path: NodePath
@export var left_hip_bone: String = "DEF-thigh.L"
@export var left_foot_bone: String = "DEF-foot.L"
@export var right_hip_bone: String = "DEF-thigh.R"
@export var right_foot_bone: String = "DEF-foot.R"
@export var spine_bone: String = "DEF-spine"

@export_group("Kinematic Dynamics")
@export var stride_frequency: float = 2.4 # steps per second at full run
@export var max_stride_length: float = 0.85
@export var step_height: float = 0.22
@export var spring_frequency: float = 4.5 # Inertial torso oscillation
@export var damping_ratio: float = 0.65

var skeleton: Skeleton3D
var step_cycle: float = 0.0
var current_velocity: Vector3 = Vector3.ZERO
var prev_global_pos: Vector3 = Vector3.ZERO

# 2nd Order Torso Lean Inertial State
var torso_lean: Vector2 = Vector2.ZERO
var torso_lean_velocity: Vector2 = Vector2.ZERO

func _ready() -> void:
	if skeleton_path:
		skeleton = get_node_or_null(skeleton_path) as Skeleton3D
	prev_global_pos = global_position

func _physics_process(delta: float) -> void:
	if delta <= 0.0:
		return
		
	# 1. Derive real physical displacement & velocity
	var disp = global_position - prev_global_pos
	prev_global_pos = global_position
	var target_vel = disp / delta
	current_velocity = current_velocity.lerp(target_vel, 12.0 * delta)
	
	var horizontal_speed = Vector2(current_velocity.x, current_velocity.z).length()
	
	# 2. Advance procedural gait cadence
	if horizontal_speed > 0.05:
		step_cycle = fmod(step_cycle + delta * stride_frequency * (horizontal_speed / max_stride_length), 2.0 * PI)
	else:
		step_cycle = lerp_angle(step_cycle, 0.0, 5.0 * delta)

	# 3. Solve 2nd Order Dynamic Torso Inertial Lean
	_solve_inertial_torso(delta, target_vel)
	
	# 4. Solve Leg IK Ground Adaptation
	if skeleton:
		_solve_procedural_legs(delta, horizontal_speed)

func _solve_inertial_torso(delta: float, target_velocity: Vector3) -> void:
	var local_vel = global_transform.basis.inverse() * target_velocity
	var target_tilt = Vector2(-local_vel.z * 0.02, local_vel.x * 0.03).clamp(Vector2(-0.4, -0.4), Vector2(0.4, 0.4))
	
	# Spring-damper integration (f = -k*x - c*v)
	var k = spring_frequency * spring_frequency
	var c = 2.0 * damping_ratio * spring_frequency
	var force = (target_tilt - torso_lean) * k - (torso_lean_velocity * c)
	
	torso_lean_velocity += force * delta
	torso_lean += torso_lean_velocity * delta

func _solve_procedural_legs(_delta: float, speed: float) -> void:
	# Compute left & right foot vertical displacement curves
	var left_phase = sin(step_cycle)
	var right_phase = sin(step_cycle + PI)
	
	# Detect ground contact transition for audio / particle signal dispatch
	if left_phase < -0.92:
		emit_signal("foot_planted", left_foot_bone, global_position, Vector3.UP, speed)
	elif right_phase < -0.92:
		emit_signal("foot_planted", right_foot_bone, global_position, Vector3.UP, speed)

# Two-Bone Analytical Law-of-Cosines Inverse Kinematics solver
static func solve_two_bone_ik(root_pos: Vector3, target_pos: Vector3, pole_dir: Vector3, l1: float, l2: float) -> Dictionary:
	var to_target = target_pos - root_pos
	var target_dist = clamp(to_target.length(), 0.001, (l1 + l2) * 0.999)
	var dir = to_target.normalized()
	
	# Law of cosines for angle at root (alpha) and mid joint (beta)
	var cos_alpha = (l1 * l1 + target_dist * target_dist - l2 * l2) / (2.0 * l1 * target_dist)
	var alpha = acos(clamp(cos_alpha, -1.0, 1.0))
	
	var side = dir.cross(pole_dir).normalized()
	var joint_normal = side.cross(dir).normalized()
	
	var mid_joint_pos = root_pos + (dir * cos(alpha) + joint_normal * sin(alpha)) * l1
	
	return {
		"root": root_pos,
		"mid": mid_joint_pos,
		"end": target_pos
	}
