# GravityNullifier
# Kinetic modifier: simulates Jedi Force Levitation, anti-gravity zones, or vacuum.
class_name GravityNullifier
extends RefCounted

var gravity_scale: float = 0.1
var vertical_drag: float = 2.0

func _init(p_scale: float = 0.1, p_drag: float = 2.0) -> void:
	gravity_scale = p_scale
	vertical_drag = p_drag

func modify_gravity(base_gravity: float) -> float:
	return base_gravity * gravity_scale
