# MassProfile
# Inertial Mass & Density Resource. Decoupled from mesh or character identity.
class_name MassProfile
extends Resource

@export var profile_name: String = "Standard"
@export var mass_kg: float = 80.0
@export var density_g_cm3: float = 1.0
@export var ground_friction: float = 10.0
@export var air_drag: float = 0.5
@export var limb_mass_ratio: float = 0.35 # Body mass leveraged into a strike
@export var center_of_mass_offset: Vector3 = Vector3(0.0, 1.0, 0.0)
