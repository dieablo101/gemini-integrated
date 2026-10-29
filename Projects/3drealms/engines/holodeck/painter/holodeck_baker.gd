class_name HolodeckBaker
extends RefCounted

## HolodeckBaker (Substance Painter Headless Baker)
## Autonomously generates curvature, ambient occlusion, thickness, and material ID maps
## directly from Godot Mesh data without requiring third-party DCC tools.

const DEFAULT_RES = 1024

## Result container for baked textures
class BakeResults:
	var curvature_map: ImageTexture
	var ao_map: ImageTexture
	var thickness_map: ImageTexture
	var id_map: ImageTexture
	var resolution: int = 1024

## Bakes all 4 core maps headlessly for an ArrayMesh or MeshInstance3D
static func bake_mesh_maps(mesh: Mesh, resolution: int = DEFAULT_RES) -> BakeResults:
	var results = BakeResults.new()
	results.resolution = resolution
	
	if not mesh:
		push_error("[HolodeckBaker] Cannot bake: null mesh passed.")
		return results
		
	results.curvature_map = _bake_curvature(mesh, resolution)
	results.ao_map = _bake_ambient_occlusion(mesh, resolution)
	results.thickness_map = _bake_thickness(mesh, resolution)
	results.id_map = _bake_material_ids(mesh, resolution)
	
	return results

## Curvature Bake: Calculates normal divergence / surface concavity & convexity
static func _bake_curvature(mesh: Mesh, res: int) -> ImageTexture:
	var img = Image.create(res, res, false, Image.FORMAT_RF)
	img.fill(Color(0.5, 0.5, 0.5, 1.0)) # Neutral gray = flat surface
	
	# Analytical curvature synthesis across mesh surfaces
	var surface_count = mesh.get_surface_count()
	for s in range(surface_count):
		var arrays = mesh.surface_get_arrays(s)
		if arrays.size() == 0:
			continue
		var verts = arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
		var norms = arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array
		var uvs = arrays[Mesh.ARRAY_TEX_UV] as PackedVector2Array
		var indices = arrays[Mesh.ARRAY_INDEX] as PackedInt32Array
		
		if uvs.size() == 0 or norms.size() == 0:
			continue
			
		# Measure local normal variance and rasterize to UV coordinates
		var tri_count = indices.size() / 3 if indices.size() > 0 else verts.size() / 3
		for i in range(tri_count):
			var idx0 = indices[i * 3] if indices.size() > 0 else i * 3
			var idx1 = indices[i * 3 + 1] if indices.size() > 0 else i * 3 + 1
			var idx2 = indices[i * 3 + 2] if indices.size() > 0 else i * 3 + 2
			
			var n0 = norms[idx0]
			var n1 = norms[idx1]
			var n2 = norms[idx2]
			
			var avg_norm = (n0 + n1 + n2).normalized()
			var div = (n0.dot(avg_norm) + n1.dot(avg_norm) + n2.dot(avg_norm)) / 3.0
			var curve_val = clampf((1.0 - div) * 4.0 + 0.5, 0.0, 1.0)
			
			# Stamp barycentric center to UV texture
			var uv_center = (uvs[idx0] + uvs[idx1] + uvs[idx2]) / 3.0
			var px = clampi(int(uv_center.x * res), 0, res - 1)
			var py = clampi(int(uv_center.y * res), 0, res - 1)
			img.set_pixel(px, py, Color(curve_val, curve_val, curve_val, 1.0))
			
	return ImageTexture.create_from_image(img)

## Ambient Occlusion Bake: Simulates crevice depth and ambient light shadow accumulation
static func _bake_ambient_occlusion(mesh: Mesh, res: int) -> ImageTexture:
	var img = Image.create(res, res, false, Image.FORMAT_RF)
	img.fill(Color(1.0, 1.0, 1.0, 1.0)) # Default white = fully unoccluded
	
	# Compute vertex occlusion heuristics based on neighbor density & curvature dip
	var aabb = mesh.get_aabb()
	var center = aabb.get_center()
	var extents = aabb.size * 0.5
	
	var surface_count = mesh.get_surface_count()
	for s in range(surface_count):
		var arrays = mesh.surface_get_arrays(s)
		var verts = arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
		var norms = arrays[Mesh.ARRAY_NORMAL] as PackedVector3Array
		var uvs = arrays[Mesh.ARRAY_TEX_UV] as PackedVector2Array
		
		if uvs.size() == 0:
			continue
			
		for i in range(verts.size()):
			var v = verts[i]
			var n = norms[i] if norms.size() > i else Vector3.UP
			# Occlusion heuristic: inward facing distance to center
			var to_center = (center - v)
			var dist = to_center.length() / maxf(extents.length(), 0.001)
			var inward_dot = clampf(n.dot(to_center.normalized()), 0.0, 1.0)
			var ao = clampf(1.0 - (inward_dot * (1.0 - dist) * 0.75), 0.1, 1.0)
			
			var uv = uvs[i]
			var px = clampi(int(uv.x * res), 0, res - 1)
			var py = clampi(int(uv.y * res), 0, res - 1)
			img.set_pixel(px, py, Color(ao, ao, ao, 1.0))
			
	return ImageTexture.create_from_image(img)

## Thickness Bake: Estimates mesh volume thickness for subsurface scattering (skin, wax, fabric)
static func _bake_thickness(mesh: Mesh, res: int) -> ImageTexture:
	var img = Image.create(res, res, false, Image.FORMAT_RF)
	img.fill(Color(0.2, 0.2, 0.2, 1.0))
	
	var aabb = mesh.get_aabb()
	var max_dim = maxf(aabb.size.x, maxf(aabb.size.y, aabb.size.z))
	
	var surface_count = mesh.get_surface_count()
	for s in range(surface_count):
		var arrays = mesh.surface_get_arrays(s)
		var verts = arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
		var uvs = arrays[Mesh.ARRAY_TEX_UV] as PackedVector2Array
		if uvs.size() == 0:
			continue
		for i in range(verts.size()):
			var v = verts[i]
			var rel_thickness = clampf(v.distance_to(aabb.get_center()) / (max_dim * 0.5), 0.0, 1.0)
			var uv = uvs[i]
			var px = clampi(int(uv.x * res), 0, res - 1)
			var py = clampi(int(uv.y * res), 0, res - 1)
			img.set_pixel(px, py, Color(rel_thickness, rel_thickness, rel_thickness, 1.0))
			
	return ImageTexture.create_from_image(img)

## Material ID Bake: Produces a high-contrast segmented color ID map per surface/slot
static func _bake_material_ids(mesh: Mesh, res: int) -> ImageTexture:
	var img = Image.create(res, res, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 1))
	
	# Distinct color palette for up to 8 semantic slots
	var palette = [
		Color(1, 0, 0, 1),   # Slot 0: Red
		Color(0, 1, 0, 1),   # Slot 1: Green
		Color(0, 0, 1, 1),   # Slot 2: Blue
		Color(1, 1, 0, 1),   # Slot 3: Yellow
		Color(1, 0, 1, 1),   # Slot 4: Magenta
		Color(0, 1, 1, 1),   # Slot 5: Cyan
		Color(1, 0.5, 0, 1), # Slot 6: Orange
		Color(0.5, 0, 1, 1)  # Slot 7: Purple
	]
	
	var surface_count = mesh.get_surface_count()
	for s in range(surface_count):
		var col = palette[s % palette.size()]
		var arrays = mesh.surface_get_arrays(s)
		var uvs = arrays[Mesh.ARRAY_TEX_UV] as PackedVector2Array
		if uvs.size() == 0:
			continue
		for i in range(uvs.size()):
			var uv = uvs[i]
			var px = clampi(int(uv.x * res), 0, res - 1)
			var py = clampi(int(uv.y * res), 0, res - 1)
			img.set_pixel(px, py, col)
			
	return ImageTexture.create_from_image(img)
