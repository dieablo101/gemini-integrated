# Hitbox3D
# Kinetic-aware combat hitbox. Tracks real-time socket velocity and extracts
# mass from the parent entity's MassProfile to construct a KineticImpactPayload.
class_name Hitbox3D
extends Area3D

signal kinetic_impact_delivered(target: Area3D, payload: Dictionary)

@export var contact_area_m2: float = 0.005 # 50cm²
var prev_global_pos: Vector3 = Vector3.ZERO
var current_velocity: Vector3 = Vector3.ZERO

func _ready() -> void:
	prev_global_pos = global_position
	area_entered.connect(_on_area_entered)

func _physics_process(delta: float) -> void:
	if delta > 0.0:
		current_velocity = (global_position - prev_global_pos) / delta
	prev_global_pos = global_position

func _on_area_entered(other_area: Area3D) -> void:
	var parent_body = get_parent()
	var mass = 80.0
	var limb_ratio = 0.35
	
	if "mass_profile" in parent_body and parent_body.mass_profile:
		mass = parent_body.mass_profile.mass_kg
		limb_ratio = parent_body.mass_profile.limb_mass_ratio
		
	var payload = KineticImpactSolver.calculate_impact_payload(
		mass,
		limb_ratio,
		current_velocity,
		contact_area_m2
	)
	
	emit_signal("kinetic_impact_delivered", other_area, payload)
	if other_area.has_method("receive_kinetic_impact"):
		other_area.receive_kinetic_impact(payload, global_position)
