class_name SemanticSegmenter
extends RefCounted

## SemanticSegmenter (Surface Semantic Dissector)
## Parses mesh geometry into isolated semantic regions (e.g. blade, handle, pommel, cloth).
## Enables an AI or user to address mesh parts by name rather than arbitrary polygon indices.

class SemanticSlot:
	var id: int
	var name: String
	var surface_index: int
	var vertex_count: int
	var uv_bounds: Rect2
	var mask_color: Color

## Analyzes an ArrayMesh or MeshInstance3D and extracts semantic partition definitions
static func analyze_mesh(mesh: Mesh) -> Array[SemanticSlot]:
	var slots: Array[SemanticSlot] = []
	if not mesh:
		return slots
		
	var surface_count = mesh.get_surface_count()
	var palette = [
		Color(1, 0, 0, 1),
		Color(0, 1, 0, 1),
		Color(0, 0, 1, 1),
		Color(1, 1, 0, 1),
		Color(1, 0, 1, 1),
		Color(0, 1, 1, 1)
	]
	
	for s in range(surface_count):
		var slot = SemanticSlot.new()
		slot.id = s
		slot.surface_index = s
		slot.mask_color = palette[s % palette.size()]
		
		var arrays = mesh.surface_get_arrays(s)
		if arrays.size() > 0:
			var verts = arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			var uvs = arrays[Mesh.ARRAY_TEX_UV] as PackedVector2Array
			slot.vertex_count = verts.size()
			
			# Calculate UV bounding box
			if uvs.size() > 0:
				var min_uv = Vector2(INF, INF)
				var max_uv = Vector2(-INF, -INF)
				for uv in uvs:
					min_uv.x = minf(min_uv.x, uv.x)
					min_uv.y = minf(min_uv.y, uv.y)
					max_uv.x = maxf(max_uv.x, uv.x)
					max_uv.y = maxf(max_uv.y, uv.y)
				slot.uv_bounds = Rect2(min_uv, max_uv - min_uv)
				
		# Surface name heuristic: fallback to "segment_X" if unnamed
		slot.name = "segment_" + str(s)
		slots.append(slot)
		
	return slots

## Maps a human/AI semantic dictionary (e.g. {"blade": 0, "hilt": 1}) to verified mesh slots
static func bind_semantic_names(slots: Array[SemanticSlot], mapping: Dictionary) -> void:
	for slot in slots:
		for name in mapping:
			if int(mapping[name]) == slot.id or mapping[name] == slot.name:
				slot.name = name
				break
