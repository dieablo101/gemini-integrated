# ActorAssembler: Wires imported skeletal models with procedural FLUX PBR materials,
# bone sockets, LOD cascades, and Kinetic Strike Volumes.
class_name ActorAssembler
extends RefCounted

const GLB_PATH: String = "res://models/characters/male/highpoly/gothic_barbarian.glb"

# Shader paths
const SHADER_PLATE: String = "res://engines/flux/shaders/flux_gothic_plate.gdshader"
const SHADER_IRON: String = "res://engines/flux/shaders/flux_dark_iron.gdshader"
const SHADER_BLADE: String = "res://engines/flux/shaders/flux_honed_blade.gdshader"
const SHADER_LEATHER: String = "res://engines/flux/shaders/flux_worn_leather.gdshader"

# Assembled entity handle
class AssembledActor:
	var root_node: Node3D
	var skeleton: Skeleton3D
	var barbarian_mesh: MeshInstance3D
	var weapon_mesh: MeshInstance3D
	var weapon_socket_attachment: BoneAttachment3D
	var weapon_rest_transform: Transform3D
	var is_weapon_socketed: bool = false
	var kinetic_volumes: Array[Node3D] = []
	var debug_visualizers_visible: bool = true

	func toggle_weapon_socket() -> void:
		set_weapon_socketed(!is_weapon_socketed)

	func set_weapon_socketed(socketed: bool) -> void:
		if is_weapon_socketed == socketed:
			return
		is_weapon_socketed = socketed
		
		if not weapon_mesh:
			return
			
		if socketed:
			# Parent into BoneAttachment3D socket
			weapon_mesh.owner = null
			if weapon_mesh.get_parent():
				weapon_mesh.get_parent().remove_child(weapon_mesh)
			weapon_socket_attachment.add_child(weapon_mesh)
			# Align hilt to socket center
			weapon_mesh.position = Vector3(0.0, -0.32, 0.0)
			weapon_mesh.rotation_degrees = Vector3(0, 0, 0)
		else:
			# Return to resting position beside character
			weapon_mesh.owner = null
			if weapon_mesh.get_parent():
				weapon_mesh.get_parent().remove_child(weapon_mesh)
			root_node.add_child(weapon_mesh)
			weapon_mesh.transform = weapon_rest_transform

	func toggle_debug_visualizers() -> void:
		set_debug_visualizers(!debug_visualizers_visible)

	func set_debug_visualizers(visible: bool) -> void:
		debug_visualizers_visible = visible
		for vol in kinetic_volumes:
			vol.visible = visible


static func assemble_gothic_barbarian() -> AssembledActor:
	var gltf_doc = GLTFDocument.new()
	var gltf_state = GLTFState.new()
	
	var err = gltf_doc.append_from_file(GLB_PATH, gltf_state)
	if err != OK:
		push_error("ActorAssembler: Failed to append GLTF: %d" % err)
		return null
		
	var root: Node3D = gltf_doc.generate_scene(gltf_state) as Node3D
	if not root:
		push_error("ActorAssembler: Failed to generate scene from GLTF")
		return null
		
	var actor = AssembledActor.new()
	actor.root_node = root
	
	# Locate skeleton and meshes
	_find_nodes_recursive(root, actor)
	
	if not actor.skeleton:
		push_error("ActorAssembler: Skeleton3D not found in hierarchy!")
		return null
		
	# Store weapon resting transform
	if actor.weapon_mesh:
		actor.weapon_rest_transform = actor.weapon_mesh.transform
		
	# Apply FLUX Procedural PBR Shaders
	_apply_flux_materials(actor)
	
	# Setup Bone Socket for Greatsword
	_setup_weapon_socket(actor)
	
	# Setup Kinetic Strike Volumes (Knuckles & Swept Blade)
	_setup_kinetic_strike_volumes(actor)
	
	return actor


static func _find_nodes_recursive(node: Node, actor: AssembledActor) -> void:
	if node is Skeleton3D:
		actor.skeleton = node as Skeleton3D
	elif node is MeshInstance3D:
		if node.name.begins_with("Gothic_Barbarian"):
			actor.barbarian_mesh = node as MeshInstance3D
		elif node.name.begins_with("Gothic_Greatsword"):
			actor.weapon_mesh = node as MeshInstance3D
			
	for child in node.get_children():
		_find_nodes_recursive(child, actor)


static func _apply_flux_materials(actor: AssembledActor) -> void:
	# Load shaders
	var sh_plate = load(SHADER_PLATE) as Shader
	var sh_iron = load(SHADER_IRON) as Shader
	var sh_blade = load(SHADER_BLADE) as Shader
	var sh_leather = load(SHADER_LEATHER) as Shader
	
	# Barbarian Mesh
	if actor.barbarian_mesh:
		var mat_plate = ShaderMaterial.new()
		mat_plate.shader = sh_plate
		actor.barbarian_mesh.set_surface_override_material(0, mat_plate)
		
		if actor.barbarian_mesh.get_surface_override_material_count() > 1 or actor.barbarian_mesh.mesh.get_surface_count() > 1:
			var mat_iron = ShaderMaterial.new()
			mat_iron.shader = sh_iron
			actor.barbarian_mesh.set_surface_override_material(1, mat_iron)
			
	# Greatsword Mesh
	if actor.weapon_mesh:
		var mat_blade = ShaderMaterial.new()
		mat_blade.shader = sh_blade
		actor.weapon_mesh.set_surface_override_material(0, mat_blade)
		
		if actor.weapon_mesh.get_surface_override_material_count() > 1 or actor.weapon_mesh.mesh.get_surface_count() > 1:
			var mat_leather = ShaderMaterial.new()
			mat_leather.shader = sh_leather
			actor.weapon_mesh.set_surface_override_material(1, mat_leather)


static func _setup_weapon_socket(actor: AssembledActor) -> void:
	var bone_idx = actor.skeleton.find_bone("Socket.Weapon.R")
	if bone_idx == -1:
		push_warning("ActorAssembler: 'Socket.Weapon.R' not found, falling back to 'Hand.R'")
		bone_idx = actor.skeleton.find_bone("Hand.R")
		
	var socket_attach = BoneAttachment3D.new()
	socket_attach.name = "BoneAttachment_Socket_Weapon_R"
	socket_attach.bone_name = actor.skeleton.get_bone_name(bone_idx)
	actor.skeleton.add_child(socket_attach)
	
	actor.weapon_socket_attachment = socket_attach


static func _setup_kinetic_strike_volumes(actor: AssembledActor) -> void:
	# 1. Left Fist Kinetic Volume (Armored Knuckles)
	var fist_l_idx = actor.skeleton.find_bone("Hand.L")
	if fist_l_idx != -1:
		var attach_l = BoneAttachment3D.new()
		attach_l.name = "Attachment_Fist_L"
		attach_l.bone_name = "Hand.L"
		actor.skeleton.add_child(attach_l)
		
		var vol_l = _create_kinetic_volume_node("KineticVolume_Fist_L", 0.12, Color(0.9, 0.2, 0.2, 0.45))
		attach_l.add_child(vol_l)
		actor.kinetic_volumes.append(vol_l)
		
	# 2. Right Fist Kinetic Volume
	var fist_r_idx = actor.skeleton.find_bone("Hand.R")
	if fist_r_idx != -1:
		var attach_r = BoneAttachment3D.new()
		attach_r.name = "Attachment_Fist_R"
		attach_r.bone_name = "Hand.R"
		actor.skeleton.add_child(attach_r)
		
		var vol_r = _create_kinetic_volume_node("KineticVolume_Fist_R", 0.12, Color(0.9, 0.2, 0.2, 0.45))
		attach_r.add_child(vol_r)
		actor.kinetic_volumes.append(vol_r)
		
	# 3. Swept Greatsword Kinetic Blade Volumes (Ricasso, Mid-Blade, Tip)
	if actor.weapon_mesh:
		var ricasso = _create_kinetic_volume_node("KineticVolume_Blade_Ricasso", 0.08, Color(0.2, 0.6, 1.0, 0.5))
		ricasso.position = Vector3(0.0, 0.70, 0.0)
		actor.weapon_mesh.add_child(ricasso)
		actor.kinetic_volumes.append(ricasso)
		
		var mid = _create_kinetic_volume_node("KineticVolume_Blade_Mid", 0.09, Color(0.2, 0.8, 1.0, 0.5))
		mid.position = Vector3(0.0, 1.35, 0.0)
		actor.weapon_mesh.add_child(mid)
		actor.kinetic_volumes.append(mid)
		
		var tip = _create_kinetic_volume_node("KineticVolume_Blade_Tip", 0.07, Color(0.3, 1.0, 0.7, 0.6))
		tip.position = Vector3(0.0, 2.02, 0.0)
		actor.weapon_mesh.add_child(tip)
		actor.kinetic_volumes.append(tip)


static func _create_kinetic_volume_node(p_name: String, p_radius: float, p_color: Color) -> Node3D:
	var container = Node3D.new()
	container.name = p_name
	
	# Physics Area3D
	var area = Area3D.new()
	area.name = "StrikeArea"
	var col_shape = CollisionShape3D.new()
	var sphere = SphereShape3D.new()
	sphere.radius = p_radius
	col_shape.shape = sphere
	area.add_child(col_shape)
	container.add_child(area)
	
	# Visualizer Sphere Mesh (for debug overlay)
	var vis = MeshInstance3D.new()
	vis.name = "DebugVisualizer"
	var mesh = SphereMesh.new()
	mesh.radius = p_radius
	mesh.height = p_radius * 2.0
	mesh.radial_segments = 16
	mesh.rings = 8
	vis.mesh = mesh
	
	var mat = StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = p_color
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	vis.material_override = mat
	container.add_child(vis)
	
	return container
