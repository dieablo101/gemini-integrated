# MaterialYieldDatabase
# Stores shear limits, compressive strengths, and fracture thresholds (in MPa)
# for destructible materials in the game world.
class_name MaterialYieldDatabase
extends RefCounted

const YIELD_LIMITS: Dictionary = {
	"rotten_wood": {"compressive_mpa": 1.5, "shear_mpa": 0.8, "density_kg_m3": 450.0},
	"weathered_brick": {"compressive_mpa": 12.0, "shear_mpa": 3.2, "density_kg_m3": 1900.0},
	"solid_oak": {"compressive_mpa": 35.0, "shear_mpa": 9.5, "density_kg_m3": 750.0},
	"reinforced_stone": {"compressive_mpa": 60.0, "shear_mpa": 18.0, "density_kg_m3": 2700.0},
	"forged_iron": {"compressive_mpa": 250.0, "shear_mpa": 120.0, "density_kg_m3": 7800.0}
}

static func get_material_yield(material_name: String) -> Dictionary:
	return YIELD_LIMITS.get(material_name, {"compressive_mpa": 5.0, "shear_mpa": 2.0, "density_kg_m3": 1000.0})
