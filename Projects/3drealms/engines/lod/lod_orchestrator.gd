# @tool
class_name LODOrchestrator
extends RefCounted

## Master Facade for 3DRealms Geometric Simplification Engine
## Generates cascading LOD stages, calculates Nanite-style screen error transition distances,
## and returns structured data for Holodeck, Eco, and Destruction pipelines.

const EdgeCollapser = preload("res://engines/lod/edge_collapser.gd")
const ScreenErrorMetric = preload("res://engines/lod/error_metric.gd")

## Standard LOD decimation ratios
const DEFAULT_LOD_RATIOS = [1.0, 0.50, 0.25, 0.10, 0.03]

## Generates a complete LOD cascade for an input ArrayMesh
## Returns a Dictionary:
## {
##   "lod_levels": [
##      {
##         "lod_index": 0,
##         "mesh": ArrayMesh,
##         "triangle_count": int,
##         "geometric_error": float,
##         "switch_distance": float,
##         "hysteresis": { "drop_distance": float, "promote_distance": float }
##      },
##      ...
##   ]
## }
static func generate_lod_cascade(
	source_mesh: ArrayMesh,
	ratios: Array = DEFAULT_LOD_RATIOS,
	target_pixel_error: float = 1.0,
	fov_degrees: float = 75.0,
	viewport_height: float = 1080.0
) -> Dictionary:
	var result_levels: Array = []

	if source_mesh == null or source_mesh.get_surface_count() == 0:
		return {"lod_levels": []}

	# Process surface 0
	var surface_arrays = source_mesh.surface_get_arrays(0)
	var mat = source_mesh.surface_get_material(0)

	for i in range(ratios.size()):
		var ratio: float = ratios[i]

		var decimation = EdgeCollapser.simplify_surface_arrays(surface_arrays, ratio)
		var geom_error: float = decimation["geometric_error"]

		var switch_dist: float = ScreenErrorMetric.calculate_lod_switch_distance(
			geom_error,
			target_pixel_error,
			fov_degrees,
			viewport_height
		)
		var hysteresis = ScreenErrorMetric.calculate_hysteresis_range(switch_dist)

		# Build discrete ArrayMesh for this LOD level
		var lod_mesh = ArrayMesh.new()
		lod_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, decimation["arrays"])
		if mat:
			lod_mesh.surface_set_material(0, mat)

		result_levels.append({
			"lod_index": i,
			"mesh": lod_mesh,
			"triangle_count": decimation["decimated_triangles"],
			"original_triangles": decimation["original_triangles"],
			"geometric_error": geom_error,
			"switch_distance": switch_dist if i > 0 else 0.0,
			"hysteresis": hysteresis
		})

	return {
		"lod_levels": result_levels,
		"lod_count": result_levels.size()
	}
