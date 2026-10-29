extends SceneTree

# Headless Godot Sculpt Study Rig
# Ingests glTF models exported from Nomad Link / Blender, analyzes physical collision
# geometries, bounding boxes, convex hulls, and kinetic strike volumes.

func _init():
	var args = OS.get_cmdline_user_args()
	if args.is_empty():
		args = OS.get_cmdline_args()
	var glb_path = ""
	var out_dir = ""
	
	for i in range(args.size()):
		if args[i] == "--glb" and i + 1 < args.size():
			glb_path = args[i + 1]
		elif args[i] == "--out" and i + 1 < args.size():
			out_dir = args[i + 1]
			
	if glb_path == "" or out_dir == "":
		print("[GodotStudy] Missing --glb or --out arguments.")
		quit(1)
		return
		
	print("[GodotStudy] Ingesting GLB: ", glb_path)
	var scene = load_glb(glb_path)
	if not scene:
		print("[GodotStudy] Failed to load GLB.")
		quit(1)
		return
		
	var metrics = analyze_node(scene)
	
	var out_path = out_dir + "/godot_study.json"
	var file = FileAccess.open(out_path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(metrics, "\t"))
		file.close()
		print("[GodotStudy] Godot metrics written -> ", out_path)
	else:
		print("[GodotStudy] Failed to write metrics to ", out_path)
		
	quit(0)

func load_glb(path: String) -> Node3D:
	var gltf_doc = GLTFDocument.new()
	var gltf_state = GLTFState.new()
	var err = gltf_doc.append_from_file(path, gltf_state)
	if err != OK:
		return null
	return gltf_doc.generate_scene(gltf_state)

func analyze_node(root: Node3D) -> Dictionary:
	var meshes = []
	find_meshes(root, meshes)
	
	var total_verts = 0
	var total_faces = 0
	var combined_aabb = AABB()
	var first = true
	var convex_hull_points = 0
	
	for mesh in meshes:
		if not mesh:
			continue
		var aabb = mesh.get_aabb()
		if first:
			combined_aabb = aabb
			first = false
		else:
			combined_aabb = combined_aabb.merge(aabb)
			
		for s in range(mesh.get_surface_count()):
			var arrays = mesh.surface_get_arrays(s)
			if arrays.size() > Mesh.ARRAY_VERTEX and arrays[Mesh.ARRAY_VERTEX]:
				total_verts += arrays[Mesh.ARRAY_VERTEX].size()
			if arrays.size() > Mesh.ARRAY_INDEX and arrays[Mesh.ARRAY_INDEX]:
				total_faces += arrays[Mesh.ARRAY_INDEX].size() / 3
				
		var shape = mesh.create_convex_shape()
		if shape and shape is ConvexPolygonShape3D:
			convex_hull_points += shape.points.size()
			
	var dimensions = combined_aabb.size
	var center = combined_aabb.get_center()
	var volume = dimensions.x * dimensions.y * dimensions.z
	
	# Compute kinetic combat envelope
	var kinetic_envelope = {
		"bounding_volume": volume,
		"center_of_mass": [center.x, center.y, center.z],
		"extents": [dimensions.x, dimensions.y, dimensions.z],
		"convex_hull_points": convex_hull_points,
		"convex_hull_reduction_ratio": float(convex_hull_points) / float(total_verts) if total_verts > 0 else 0.0,
		"estimated_strike_reach": dimensions.length() * 0.5
	}
	
	return {
		"mesh_count": meshes.size(),
		"total_godot_vertices": total_verts,
		"total_godot_triangles": total_faces,
		"aabb_position": [combined_aabb.position.x, combined_aabb.position.y, combined_aabb.position.z],
		"aabb_size": [dimensions.x, dimensions.y, dimensions.z],
		"kinetic_envelope": kinetic_envelope
	}

func find_meshes(node: Node, results: Array):
	if node is MeshInstance3D and node.mesh:
		results.append(node.mesh)
	elif node is ImporterMeshInstance3D and node.mesh:
		results.append(node.mesh.get_mesh())
	elif node.has_method("get_mesh"):
		var m = node.get_mesh()
		if m:
			results.append(m)
	for child in node.get_children():
		find_meshes(child, results)
