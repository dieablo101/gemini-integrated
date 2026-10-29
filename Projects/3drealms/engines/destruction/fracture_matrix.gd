# FractureMatrix
# Destructibles engine: consumes KineticImpactSolver payload, checks yield limits,
# and generates Voronoi fracture patterns and dynamic debris shards.
class_name FractureMatrix
extends RefCounted

signal object_fractured(fracture_origin: Vector3, debris_impulse: Vector3, shard_count: int)

static func evaluate_impact(material_name: String, impact_payload: Dictionary, global_hit_pos: Vector3) -> bool:
	var yield_data = MaterialYieldDatabase.get_material_yield(material_name)
	var pressure = impact_payload.get("pressure_mpa", 0.0)
	
	if pressure >= yield_data["shear_mpa"]:
		# Material failed under shear stress: fracture triggered!
		return true
	return false
