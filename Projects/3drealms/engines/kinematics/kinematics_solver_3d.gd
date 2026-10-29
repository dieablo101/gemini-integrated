# KinematicsSolver3D
# Core kinematics resolution kernel: handles gravity integration, ground snapping,
# slope slipping, and step-up raycasts independent of character identity.
class_name KinematicsSolver3D
extends RefCounted

const DEFAULT_GRAVITY: float = 9.81
const MAX_SLOPE_ANGLE: float = 0.785398 # 45 degrees in radians

# Computes new velocity after slope projection, sliding, and friction
static func solve_ground_motion(
	current_velocity: Vector3,
	target_direction: Vector3,
	speed: float,
	acceleration: float,
	friction: float,
	delta: float,
	ground_normal: Vector3 = Vector3.UP
) -> Vector3:
	var target_vel = target_direction.normalized() * speed
	# Project motion onto ground plane
	if ground_normal != Vector3.UP and ground_normal.length_squared() > 0.01:
		target_vel = target_vel.slide(ground_normal).normalized() * speed
		
	var horiz = Vector3(current_velocity.x, 0.0, current_velocity.z)
	var target_horiz = Vector3(target_vel.x, 0.0, target_vel.z)
	var accel_factor = acceleration if target_horiz.length_squared() > 0.01 else friction
	horiz = horiz.move_toward(target_horiz, accel_factor * delta)
	
	return Vector3(horiz.x, current_velocity.y, horiz.z)

# Solves vertical gravity and slope slip
static func solve_vertical_motion(
	current_velocity: Vector3,
	gravity_accel: float,
	is_grounded: bool,
	ground_normal: Vector3,
	delta: float
) -> Vector3:
	var vel = current_velocity
	if not is_grounded:
		vel.y -= gravity_accel * delta
	else:
		var slope_angle = ground_normal.angle_to(Vector3.UP)
		if slope_angle > MAX_SLOPE_ANGLE:
			var slide_dir = Vector3.DOWN.slide(ground_normal).normalized()
			vel += slide_dir * gravity_accel * delta
		elif vel.y < 0.0:
			vel.y = -0.1 # Ground lock snap
	return vel
