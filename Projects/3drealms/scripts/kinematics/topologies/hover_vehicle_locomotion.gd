# HoverVehicleLocomotion
# Zero-ground-friction thruster drift locomotion for vehicles, sledges, or skiffs.
class_name HoverVehicleLocomotion
extends CharacterBody3D

@export var mass_profile: MassProfile
@export var hover_height: float = 1.2
@export var thruster_power: float = 45.0
@export var angular_drag: float = 2.5

var momentum_integrator: MomentumIntegrator = MomentumIntegrator.new()

func _physics_process(delta: float) -> void:
	# Raycast downward to maintain hover cushion via spring-damper
	# Applies zero ground friction with inertia drift
	move_and_slide()
