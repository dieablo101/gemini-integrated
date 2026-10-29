# MomentumMultiplier
# Kinetic modifier: Berserk fury or superhuman punch amplifier.
class_name MomentumMultiplier
extends RefCounted

var multiplier: float = 2.5

func _init(p_multiplier: float = 2.5) -> void:
	multiplier = p_multiplier

func modify_impact(payload: Dictionary) -> Dictionary:
	var modified = payload.duplicate()
	modified["kinetic_energy_joules"] = payload.get("kinetic_energy_joules", 0.0) * (multiplier * multiplier)
	modified["impulse_vector"] = payload.get("impulse_vector", Vector3.ZERO) * multiplier
	modified["pressure_mpa"] = payload.get("pressure_mpa", 0.0) * multiplier
	return modified
