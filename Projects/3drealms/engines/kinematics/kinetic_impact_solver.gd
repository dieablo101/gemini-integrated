# KineticImpactSolver
# Computes physical work, kinetic energy (Joules), impulse vector (N*s),
# and peak pressure (MPa) when a body/weapon strikes a physical surface.
class_name KineticImpactSolver
extends RefCounted

# Evaluates the kinetic payload delivered by an impact
static func calculate_impact_payload(
	attacker_mass_kg: float,
	limb_mass_ratio: float,
	velocity_vector: Vector3,
	contact_area_m2: float = 0.005 # ~50 cm² knuckle / blade point
) -> Dictionary:
	var speed = velocity_vector.length()
	# Effective mass transfer: body mass fraction + direct limb mass
	var effective_mass = attacker_mass_kg * clamp(limb_mass_ratio, 0.1, 1.0)
	
	# KE = 1/2 * m * v^2
	var joules = 0.5 * effective_mass * (speed * speed)
	
	# Impulse J = m * v (N*s)
	var impulse = velocity_vector * effective_mass
	
	# Force = Impulse / impact_duration (approx 0.015s deformation window)
	var impact_duration = 0.015
	var peak_force_newtons = (effective_mass * speed) / impact_duration
	
	# Pressure P = F / A (in Pascals -> converted to Megapascals MPa)
	var pressure_mpa = (peak_force_newtons / max(contact_area_m2, 0.0001)) / 1_000_000.0
	
	return {
		"kinetic_energy_joules": joules,
		"impulse_vector": impulse,
		"peak_force_n": peak_force_newtons,
		"pressure_mpa": pressure_mpa,
		"effective_mass_kg": effective_mass
	}
