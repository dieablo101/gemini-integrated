# BipedLocomotion
# Composable locomotion controller for 2-legged actors.
# Decoupled from entity identity: takes a MassProfile and stackable KineticModifiers.
class_name BipedLocomotion
extends CharacterBody3D

@export var mass_profile: MassProfile
@export var walk_speed: float = 4.2
@export var sprint_speed: float = 7.5
@export var acceleration: float = 24.0

var momentum_integrator: MomentumIntegrator = MomentumIntegrator.new()
var kinetic_modifiers: Array = []

func _physics_process(delta: float) -> void:
	var gravity = KinematicsSolver3D.DEFAULT_GRAVITY
	
	# Apply stackable modifiers (e.g. Jedi levitation, slow motion)
	for mod in kinetic_modifiers:
		if mod.has_method("modify_gravity"):
			gravity = mod.modify_gravity(gravity)
			
	var is_grounded = is_on_floor()
	var ground_normal = get_floor_normal() if is_grounded else Vector3.UP
	
	# Vertical solve
	velocity = KinematicsSolver3D.solve_vertical_motion(velocity, gravity, is_grounded, ground_normal, delta)
	
	# Add external momentum (impulses, knockback)
	var mass = mass_profile.mass_kg if mass_profile else 80.0
	var impulse_vel = momentum_integrator.integrate(mass, delta)
	velocity += impulse_vel
	
	move_and_slide()

func add_kinetic_modifier(modifier: RefCounted) -> void:
	kinetic_modifiers.append(modifier)

func remove_kinetic_modifier(modifier: RefCounted) -> void:
	kinetic_modifiers.erase(modifier)
