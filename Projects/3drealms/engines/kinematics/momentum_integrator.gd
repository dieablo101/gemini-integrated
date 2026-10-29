# MomentumIntegrator
# Manages linear momentum p = m * v, external impulse forces, and inertial drag.
class_name MomentumIntegrator
extends RefCounted

var accumulated_impulse: Vector3 = Vector3.ZERO
var impulse_decay_rate: float = 8.0

func apply_impulse(impulse: Vector3) -> void:
	accumulated_impulse += impulse

func integrate(mass_kg: float, delta: float) -> Vector3:
	if accumulated_impulse.length_squared() < 0.001:
		accumulated_impulse = Vector3.ZERO
		return Vector3.ZERO
	
	# v = impulse / mass
	var impulse_velocity = accumulated_impulse / max(mass_kg, 1.0)
	accumulated_impulse = accumulated_impulse.move_toward(Vector3.ZERO, impulse_decay_rate * delta * max(mass_kg * 0.1, 1.0))
	return impulse_velocity
