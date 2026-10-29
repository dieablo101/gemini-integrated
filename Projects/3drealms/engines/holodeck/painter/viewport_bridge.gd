class_name ViewportBridge
extends SubViewport

## ViewportBridge (Holodeck Headless Viewport & Snapshot Bridge)
## Spins up an offscreen 3D rendering pipeline to audit textured meshes,
## test light reflections, and capture visual snapshots for AI evaluation.

var camera: Camera3D
var stage_root: Node3D
var mesh_holder: Node3D
var env_node: WorldEnvironment
var key_light: DirectionalLight3D
var fill_light: DirectionalLight3D

func _init(viewport_size: Vector2i = Vector2i(1024, 1024)) -> void:
	size = viewport_size
	render_target_update_mode = SubViewport.UPDATE_ALWAYS
	render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	own_world_3d = true
	
	_setup_lighting_and_stage()

func _setup_lighting_and_stage() -> void:
	stage_root = Node3D.new()
	stage_root.name = "StageRoot"
	add_child(stage_root)
	
	# 1. Environment & Sky
	env_node = WorldEnvironment.new()
	var env = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.12, 0.12, 0.14, 1.0) # Studio charcoal
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.4, 0.42, 0.45)
	env.ambient_light_energy = 1.0
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env_node.environment = env
	stage_root.add_child(env_node)
	
	# 2. Key Light
	key_light = DirectionalLight3D.new()
	key_light.rotation_degrees = Vector3(-45, 45, 0)
	key_light.light_color = Color(1.0, 0.98, 0.92)
	key_light.light_energy = 1.2
	key_light.shadow_enabled = true
	stage_root.add_child(key_light)
	
	# 3. Fill / Rim Light
	fill_light = DirectionalLight3D.new()
	fill_light.rotation_degrees = Vector3(30, -135, 0)
	fill_light.light_color = Color(0.65, 0.75, 0.9)
	fill_light.light_energy = 0.5
	stage_root.add_child(fill_light)
	
	# 4. Camera
	camera = Camera3D.new()
	camera.position = Vector3(0, 0.5, 2.5)
	camera.current = true
	stage_root.add_child(camera)
	
	# 5. Mesh Holder
	mesh_holder = Node3D.new()
	mesh_holder.name = "MeshHolder"
	stage_root.add_child(mesh_holder)

## Mounts a target mesh instance onto the stage
func mount_mesh(mesh_instance: MeshInstance3D) -> void:
	for child in mesh_holder.get_children():
		mesh_holder.remove_child(child)
		child.queue_free()
		
	if mesh_instance:
		mesh_holder.add_child(mesh_instance)
		_center_camera_on_mesh(mesh_instance)

## Frames the camera around the mesh based on its AABB
func _center_camera_on_mesh(mesh_inst: MeshInstance3D) -> void:
	if not mesh_inst.mesh:
		return
	var aabb = mesh_inst.mesh.get_aabb()
	var center = aabb.get_center()
	var max_dim = maxf(aabb.size.x, maxf(aabb.size.y, aabb.size.z))
	var dist = max_dim * 2.2
	
	camera.position = center + Vector3(0, max_dim * 0.25, dist)
	camera.look_at(center, Vector3.UP)

## Sets the camera angle around the subject (orbit pitch/yaw)
func set_camera_orbit(yaw_deg: float, pitch_deg: float, distance_mult: float = 1.0) -> void:
	var target = Vector3.ZERO
	if mesh_holder.get_child_count() > 0:
		var m = mesh_holder.get_child(0) as MeshInstance3D
		if m and m.mesh:
			target = m.mesh.get_aabb().get_center()
			
	var yaw_rad = deg_to_rad(yaw_deg)
	var pitch_rad = deg_to_rad(pitch_deg)
	var radius = 2.5 * distance_mult
	
	var offset = Vector3(
		radius * cos(pitch_rad) * sin(yaw_rad),
		radius * sin(pitch_rad),
		radius * cos(pitch_rad) * cos(yaw_rad)
	)
	camera.position = target + offset
	camera.look_at(target, Vector3.UP)

## Captures a snapshot to disk as a PNG
func capture_snapshot(export_png_path: String) -> Error:
	var img = get_texture().get_image()
	if not img or img.is_empty():
		push_error("[ViewportBridge] Failed to capture viewport texture: image is empty.")
		return ERR_CANT_CREATE
		
	var err = img.save_png(export_png_path)
	if err != OK:
		push_error("[ViewportBridge] Failed to save snapshot to " + export_png_path)
	return err
