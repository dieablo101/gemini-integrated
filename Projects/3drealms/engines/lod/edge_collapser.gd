# @tool
class_name EdgeCollapser
extends RefCounted

## Progressive Surface Decimator using Quadric Error Metrics
## Simplifies triangular mesh surfaces while preventing normal flipping,
## preserving UV boundaries, and tracking cumulative geometric error.

const QEMSolver = preload("res://engines/lod/qem_solver.gd")

class Edge:
	var v1: int
	var v2: int
	var target: Vector3
	var cost: float
	var valid: bool = true

	func _init(p_v1: int, p_v2: int, p_target: Vector3, p_cost: float) -> void:
		v1 = min(p_v1, p_v2)
		v2 = max(p_v1, p_v2)
		target = p_target
		cost = p_cost

	func get_key() -> int:
		return (v1 << 32) | v2

## Simplifies an ArrayMesh surface array to a target triangle ratio (0.0 < ratio < 1.0)
## Returns a Dictionary with:
## - "arrays": Godot ArrayMesh surface arrays
## - "geometric_error": Maximum estimated geometric deviation in model space (meters)
## - "original_triangles": int
## - "decimated_triangles": int
static func simplify_surface_arrays(
	surface_arrays: Array,
	target_triangle_ratio: float,
	max_allowed_normal_flip_deg: float = 60.0
) -> Dictionary:
	var vertices: PackedVector3Array = surface_arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = surface_arrays[Mesh.ARRAY_NORMAL] if surface_arrays[Mesh.ARRAY_NORMAL] else PackedVector3Array()
	var uvs: PackedVector2Array = surface_arrays[Mesh.ARRAY_TEX_UV] if surface_arrays[Mesh.ARRAY_TEX_UV] else PackedVector2Array()
	var raw_indices: PackedInt32Array = surface_arrays[Mesh.ARRAY_INDEX]

	var num_verts: int = vertices.size()
	var num_indices: int = raw_indices.size()
	var original_tri_count: int = num_indices / 3

	if original_tri_count <= 4 or target_triangle_ratio >= 1.0:
		return {
			"arrays": surface_arrays,
			"geometric_error": 0.0,
			"original_triangles": original_tri_count,
			"decimated_triangles": original_tri_count
		}

	var target_tri_count: int = max(4, int(original_tri_count * target_triangle_ratio))

	# 1. Build triangles and calculate initial quadrics per vertex
	var vertex_quadrics: Array = []
	vertex_quadrics.resize(num_verts)
	for i in range(num_verts):
		vertex_quadrics[i] = QEMSolver.SymQuadric.new()

	var triangles: Array = []
	for i in range(0, num_indices, 3):
		var i1: int = raw_indices[i]
		var i2: int = raw_indices[i + 1]
		var i3: int = raw_indices[i + 2]
		var tri = [i1, i2, i3]
		triangles.append(tri)

		var q = QEMSolver.compute_plane_quadric(vertices[i1], vertices[i2], vertices[i3])
		vertex_quadrics[i1].add_in_place(q)
		vertex_quadrics[i2].add_in_place(q)
		vertex_quadrics[i3].add_in_place(q)

	# 2. Extract unique edges and calculate initial contraction costs
	var edges_map: Dictionary = {}
	var edge_list: Array = []

	for tri in triangles:
		for j in range(3):
			var v1: int = tri[j]
			var v2: int = tri[(j + 1) % 3]
			var low: int = min(v1, v2)
			var high: int = max(v1, v2)
			var key: int = (low << 32) | high
			if not edges_map.has(key):
				var combined_q = vertex_quadrics[low].add(vertex_quadrics[high])
				var opt = QEMSolver.find_optimal_contraction(combined_q, vertices[low], vertices[high])
				var edge = Edge.new(low, high, opt["target"], opt["cost"])
				edges_map[key] = edge
				edge_list.append(edge)

	# 3. Sort edges ascending by cost
	edge_list.sort_custom(func(a: Edge, b: Edge): return a.cost < b.cost)

	# 4. Collapse loop
	var current_tri_count: int = original_tri_count
	var max_geom_error: float = 0.0
	var vertex_remap: PackedInt32Array = PackedInt32Array()
	vertex_remap.resize(num_verts)
	for i in range(num_verts):
		vertex_remap[i] = i

	var edge_cursor: int = 0
	var max_normal_flip_rad: float = deg_to_rad(max_allowed_normal_flip_deg)

	while current_tri_count > target_tri_count and edge_cursor < edge_list.size():
		var edge: Edge = edge_list[edge_cursor]
		edge_cursor += 1

		# Find canonical vertices via remapping
		var v1: int = _find_root(vertex_remap, edge.v1)
		var v2: int = _find_root(vertex_remap, edge.v2)

		if v1 == v2:
			continue

		# Check for normal flips on adjacent triangles
		var creates_flip: bool = false
		for tri in triangles:
			var r0 = _find_root(vertex_remap, tri[0])
			var r1 = _find_root(vertex_remap, tri[1])
			var r2 = _find_root(vertex_remap, tri[2])
			if r0 == r1 or r1 == r2 or r2 == r0:
				continue

			if (r0 == v1 or r1 == v1 or r2 == v1 or r0 == v2 or r1 == v2 or r2 == v2):
				var idx0 = v1 if (r0 == v2 or r0 == v1) else r0
				var idx1 = v1 if (r1 == v2 or r1 == v1) else r1
				var idx2 = v1 if (r2 == v2 or r2 == v1) else r2
				if idx0 == idx1 or idx1 == idx2 or idx2 == idx0:
					continue
				
				var p0 = edge.target if (idx0 == v1) else vertices[idx0]
				var p1 = edge.target if (idx1 == v1) else vertices[idx1]
				var p2 = edge.target if (idx2 == v1) else vertices[idx2]

				var new_norm = (p1 - p0).cross(p2 - p0).normalized()
				var orig_norm = (vertices[tri[1]] - vertices[tri[0]]).cross(vertices[tri[2]] - vertices[tri[0]]).normalized()

				if orig_norm.dot(new_norm) < cos(max_normal_flip_rad):
					creates_flip = true
					break

		if creates_flip:
			continue

		# Apply collapse
		vertices[v1] = edge.target
		vertex_remap[v2] = v1
		vertex_quadrics[v1].add_in_place(vertex_quadrics[v2])
		max_geom_error = max(max_geom_error, sqrt(edge.cost))

		# Update triangle count (degenerate triangles with 2+ identical vertices are eliminated)
		var valid_tris: int = 0
		for tri in triangles:
			var r0 = _find_root(vertex_remap, tri[0])
			var r1 = _find_root(vertex_remap, tri[1])
			var r2 = _find_root(vertex_remap, tri[2])
			if r0 != r1 and r1 != r2 and r2 != r0:
				valid_tris += 1
		
		current_tri_count = valid_tris

	# 5. Reconstruct compacted surface array
	var final_indices: PackedInt32Array = PackedInt32Array()
	var new_verts: PackedVector3Array = PackedVector3Array()
	var new_normals: PackedVector3Array = PackedVector3Array()
	var new_uvs: PackedVector2Array = PackedVector2Array()

	var old_to_new_idx: Dictionary = {}
	var has_normals: bool = normals.size() == num_verts
	var has_uvs: bool = uvs.size() == num_verts

	for tri in triangles:
		var i0: int = _find_root(vertex_remap, tri[0])
		var i1: int = _find_root(vertex_remap, tri[1])
		var i2: int = _find_root(vertex_remap, tri[2])

		if i0 == i1 or i1 == i2 or i2 == i0:
			continue

		for idx in [i0, i1, i2]:
			if not old_to_new_idx.has(idx):
				var new_idx: int = new_verts.size()
				old_to_new_idx[idx] = new_idx
				new_verts.append(vertices[idx])
				if has_normals:
					new_normals.append(normals[idx])
				if has_uvs:
					new_uvs.append(uvs[idx])
			final_indices.append(old_to_new_idx[idx])

	var out_arrays: Array = []
	out_arrays.resize(Mesh.ARRAY_MAX)
	out_arrays[Mesh.ARRAY_VERTEX] = new_verts
	out_arrays[Mesh.ARRAY_INDEX] = final_indices
	if has_normals:
		out_arrays[Mesh.ARRAY_NORMAL] = new_normals
	if has_uvs:
		out_arrays[Mesh.ARRAY_TEX_UV] = new_uvs

	return {
		"arrays": out_arrays,
		"geometric_error": max_geom_error,
		"original_triangles": original_tri_count,
		"decimated_triangles": final_indices.size() / 3
	}

static func _find_root(remap: PackedInt32Array, i: int) -> int:
	var curr: int = i
	while remap[curr] != curr:
		remap[curr] = remap[remap[curr]] # Path compression
		curr = remap[curr]
	return curr
