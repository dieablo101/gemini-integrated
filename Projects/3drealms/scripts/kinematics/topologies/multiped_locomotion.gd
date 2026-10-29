# MultipedLocomotion
# Locomotion controller for 4-legged or 6-legged beasts/aliens.
# Integrates multi-point ground planting and distributed weight stability.
class_name MultipedLocomotion
extends CharacterBody3D

@export var mass_profile: MassProfile
@export var trot_speed: float = 6.0
@export var gallop_speed: float = 12.0
@export var leg_count: int = 4

var momentum_integrator: MomentumIntegrator = MomentumIntegrator.new()
var kinetic_modifiers: Array = []

func _physics_process(delta: float) -> void:
	var gravity = KinematicsSolver3D.DEFAULT_GRAVITY
	for mod in kinetic_modifiers:
		if mod.has_method("modify_gravity"):
			gravity = mod.modify_gravity(gravity)
			
	var is_grounded = is_on_floor()
	var ground_normal = get_floor_normal() if is_grounded else Vector3.UP
	velocity = KinematicsSolver3D.solve_vertical_motion(velocity, gravity, is_grounded, ground_normal, delta)
	
	var mass = mass_profile.mass_kg if mass_profile else 300.0
	velocity += momentum_integrator.integrate(mass, delta)
	move_and_slide()
