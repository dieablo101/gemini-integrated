extends SceneTree

# Test harness loading GLB directly via GLTFDocument and GLTFState (runtime loader)

func _init() -> void:
	print("--- TESTING GLTFDOCUMENT RUNTIME INGESTION ---")
	var glb_path = "res://models/characters/male/highpoly/gothic_barbarian.glb"
	
	var gltf_doc = GLTFDocument.new()
	var gltf_state = GLTFState.new()
	
	var err = gltf_doc.append_from_file(glb_path, gltf_state)
	if err != OK:
		printerr("FAIL: GLTFDocument append_from_file error: ", err)
		quit(1)
		return
		
	var root_node = gltf_doc.generate_scene(gltf_state)
	if not root_node:
		printerr("FAIL: Could not generate scene from GLTFState.")
		quit(1)
		return
		
	print("[1] GLTF Scene generated successfully!")
	_print_tree(root_node, "  ")
	
	# Find Skeleton3D
	var skeleton: Skeleton3D = _find_skeleton(root_node)
	if not skeleton:
		printerr("FAIL: Skeleton3D not found.")
		quit(1)
		return
		
	print("[2] Skeleton found! Bone count: ", skeleton.get_bone_count())
	for i in range(skeleton.get_bone_count()):
		var b_name = skeleton.get_bone_name(i)
		var p_idx = skeleton.get_bone_parent(i)
		var p_name = skeleton.get_bone_name(p_idx) if p_idx != -1 else "None"
		print("     Bone [", i, "]: ", b_name, " (Parent: ", p_name, ")")
		
	var sock_idx = skeleton.find_bone("Socket.Weapon.R")
	if sock_idx == -1:
		printerr("FAIL: Socket.Weapon.R missing.")
		quit(1)
		return
	print("[3] Socket.Weapon.R verified at index: ", sock_idx)
	
	var meshes = _find_all_meshes(root_node)
	print("[4] Mesh instances found: ", meshes.size())
	for m in meshes:
		print("  -> MeshInstance3D: ", m.name, " | Surfaces: ", m.mesh.get_surface_count())
		for s in range(m.mesh.get_surface_count()):
			var arrays = m.mesh.surface_get_arrays(s)
			var verts = arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array
			print("     Surface [", s, "] Vertex count: ", verts.size())
			
	print("--- RUNTIME GLTF INGESTION: ALL PASS ---")
	quit(0)

func _find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child in node.get_children():
		var s = _find_skeleton(child)
		if s:
			return s
	return null

func _find_all_meshes(node: Node) -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	if node is MeshInstance3D:
		result.append(node)
	for child in node.get_children():
		result.append_array(_find_all_meshes(child))
	return result

func _print_tree(node: Node, indent: String) -> void:
	print(indent, "- ", node.name, " (", node.get_class(), ")")
	for child in node.get_children():
		_print_tree(child, indent + "  ")
