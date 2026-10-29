# Hurtbox3D
# Kinetic damage and impulse receiver. Passes impact payloads into parent health/poise
# systems and notifies destruction matrices if the owner is destructible.
class_name Hurtbox3D
extends Area3D

signal damage_received(amount: float, impulse: Vector3)
signal fracture_requested(impact_payload: Dictionary, hit_position: Vector3)

@export var owner_material: String = "flesh"

func receive_kinetic_impact(payload: Dictionary, hit_position: Vector3) -> void:
	var joules = payload.get("kinetic_energy_joules", 0.0)
	var impulse = payload.get("impulse_vector", Vector3.ZERO)
	
	emit_signal("damage_received", joules * 0.1, impulse)
	
	# If this hurtbox is attached to a destructible surface (e.g. wall, prop)
	if owner_material != "flesh":
		emit_signal("fracture_requested", payload, hit_position)
