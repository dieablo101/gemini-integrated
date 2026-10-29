extends Node3D

# Holodeck Studio: Interactive 3D Turntable & Asset Inspector
# Showcases FLUX Mathematical PBR Shaders, Weapon Socketing, and Kinetic Volumes

const ActorAssembler = preload("res://engines/holodeck/assembly/actor_assembler.gd")

# Turntable Camera State
var cam_pivot: Node3D
var camera: Camera3D
var cam_distance: float = 3.2
var cam_pitch: float = -12.0
var cam_yaw: float = 25.0
var auto_turntable: bool = true
var turntable_speed: float = 24.0 # deg/sec
var is_dragging: bool = false
var last_mouse_pos: Vector2 = Vector2.ZERO

# Actor Handle
var actor_handle = null

# UI Elements
var hud_label: Label

# Snapshot automation state
var auto_snapshot_mode: bool = false
var snapshot_frame: int = 0

func _ready() -> void:
	# Check CLI arguments
	for arg in OS.get_cmdline_user_args():
		if arg == "--snapshot":
			auto_snapshot_mode = true
	for arg in OS.get_cmdline_args():
		if arg == "--snapshot":
			auto_snapshot_mode = true
			
	_setup_environment()
	_setup_lighting()
	_setup_pedestal()
	_setup_camera()
	_setup_ui()
	_load_character()
	
	print("[HOLODECK STUDIO] Initialized successfully. Snapshot mode: ", auto_snapshot_mode)

func _setup_environment() -> void:
	var env = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.04, 0.04, 0.06)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.12, 0.12, 0.16)
	env.ambient_light_energy = 0.8
	
	# Subtle bloom for steel specular highlights
	env.glow_enabled = true
	env.glow_intensity = 0.35
	env.glow_bloom = 0.15
	
	var world_env = WorldEnvironment.new()
	world_env.environment = env
	add_child(world_env)

func _setup_lighting() -> void:
	# 1. Key Light (Cold Steel Rim & Highlights)
	var key_light = DirectionalLight3D.new()
	key_light.name = "KeyLight"
	key_light.light_color = Color(0.90, 0.94, 1.0)
	key_light.light_energy = 1.4
	key_light.shadow_enabled = true
	key_light.rotation_degrees = Vector3(-35, 45, 0)
	add_child(key_light)
	
	# 2. Warm Amber Fill Light (Contrast & Depth)
	var fill_light = DirectionalLight3D.new()
	fill_light.name = "FillLight"
	fill_light.light_color = Color(0.85, 0.65, 0.45)
	fill_light.light_energy = 0.6
	fill_light.rotation_degrees = Vector3(-20, -135, 0)
	add_child(fill_light)
	
	# 3. Rim / Hair Light (Gleaming Edge Definition)
	var rim_light = DirectionalLight3D.new()
	rim_light.name = "RimLight"
	rim_light.light_color = Color(0.70, 0.85, 1.0)
	rim_light.light_energy = 1.8
	rim_light.rotation_degrees = Vector3(15, -170, 0)
	add_child(rim_light)

func _setup_pedestal() -> void:
	var pedestal = MeshInstance3D.new()
	pedestal.name = "StudioPedestal"
	var cyl = CylinderMesh.new()
	cyl.top_radius = 2.2
	cyl.bottom_radius = 2.4
	cyl.height = 0.15
	cyl.radial_segments = 64
	pedestal.mesh = cyl
	pedestal.position = Vector3(0.0, -0.075, 0.0)
	
	var mat = StandardMaterial3D.new()
	mat.albedo_color = Color(0.06, 0.05, 0.08)
	mat.roughness = 0.4
	mat.metallic = 0.2
	pedestal.material_override = mat
	add_child(pedestal)

func _setup_camera() -> void:
	cam_pivot = Node3D.new()
	cam_pivot.name = "CameraPivot"
	cam_pivot.position = Vector3(0.0, 1.15, 0.0) # Aim at barbarian's chest
	add_child(cam_pivot)
	
	camera = Camera3D.new()
	camera.name = "TurntableCamera"
	camera.current = true
	camera.fov = 45.0
	cam_pivot.add_child(camera)
	_update_camera_transform()

func _update_camera_transform() -> void:
	var yaw_rad = deg_to_rad(cam_yaw)
	var pitch_rad = deg_to_rad(cam_pitch)
	
	var offset = Vector3(
		cam_distance * cos(pitch_rad) * sin(yaw_rad),
		cam_distance * -sin(pitch_rad),
		cam_distance * cos(pitch_rad) * cos(yaw_rad)
	)
	camera.position = offset
	camera.look_at(cam_pivot.global_position, Vector3.UP)

func _setup_ui() -> void:
	var canvas = CanvasLayer.new()
	canvas.name = "StudioHUD"
	add_child(canvas)
	
	# Header Panel
	var panel = PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_TOP_LEFT)
	panel.offset_left = 20
	panel.offset_top = 20
	panel.offset_right = 440
	panel.offset_bottom = 240
	
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.05, 0.04, 0.08, 0.85)
	style.border_color = Color(0.65, 0.35, 0.95, 0.7)
	style.set_border_width_all(2)
	style.set_corner_radius_all(6)
	style.set_content_margin_all(14)
	panel.add_theme_stylebox_override("panel", style)
	canvas.add_child(panel)
	
	hud_label = Label.new()
	hud_label.add_theme_color_override("font_color", Color(0.9, 0.9, 0.95))
	hud_label.add_theme_font_size_override("font_size", 13)
	panel.add_child(hud_label)
	_update_hud()

func _load_character() -> void:
	actor_handle = ActorAssembler.assemble_gothic_barbarian()
	if not actor_handle:
		push_error("Failed to assemble Gothic Barbarian actor!")
		return
	add_child(actor_handle.root_node)
	_update_hud()

func _process(delta: float) -> void:
	if auto_turntable and not is_dragging and not auto_snapshot_mode:
		cam_yaw += turntable_speed * delta
		if cam_yaw >= 360.0:
			cam_yaw -= 360.0
		_update_camera_transform()
		
	if auto_snapshot_mode:
		snapshot_frame += 1
		if snapshot_frame == 15:
			_capture_snapshot("res://renders/gothic_barbarian_resting.png")
			if actor_handle:
				actor_handle.toggle_weapon_socket()
				_update_hud()
		elif snapshot_frame == 25:
			_capture_snapshot("res://renders/gothic_barbarian_socketed.png")
			print("[HOLODECK STUDIO] Both preview snapshots captured. Exiting.")
			get_tree().quit(0)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			is_dragging = event.pressed
			last_mouse_pos = event.position
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			cam_distance = clamp(cam_distance - 0.25, 0.8, 6.0)
			_update_camera_transform()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			cam_distance = clamp(cam_distance + 0.25, 0.8, 6.0)
			_update_camera_transform()
			
	elif event is InputEventMouseMotion and is_dragging:
		var delta_pos = event.position - last_mouse_pos
		last_mouse_pos = event.position
		cam_yaw -= delta_pos.x * 0.4
		cam_pitch = clamp(cam_pitch + delta_pos.y * 0.4, -75.0, 75.0)
		_update_camera_transform()
		
	elif event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_TAB:
				if actor_handle:
					actor_handle.toggle_weapon_socket()
					_update_hud()
			KEY_V:
				if actor_handle:
					actor_handle.toggle_debug_visualizers()
					_update_hud()
			KEY_R, KEY_SPACE:
				auto_turntable = !auto_turntable
				_update_hud()
			KEY_F12:
				_capture_snapshot("res://renders/gothic_barbarian_manual.png")
			KEY_ESCAPE:
				get_tree().quit()

func _update_hud() -> void:
	if not hud_label:
		return
	var weapon_str = "SOCKETED (In Hand)" if (actor_handle and actor_handle.is_weapon_socketed) else "RESTING (Beside Body)"
	var vis_str = "ENABLED" if (actor_handle and actor_handle.debug_visualizers_visible) else "HIDDEN"
	var spin_str = "ACTIVE (360°)" if auto_turntable else "PAUSED"
	
	hud_label.text = """DIEABLO: HOLODECK STUDIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Model: Gothic Barbarian (7,251 Vertices)
• Weapon: Colossal Greatsword (1,014 Vertices)
• Shaders: 4x FLUX PBR (Pure GPU Math, 0 KB Textures)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[TAB] Weapon State:     %s
[V]   Kinetic Volumes:  %s
[R]   Turntable Spin:   %s
[Drag / Wheel] Orbit & Zoom
[F12] Capture High-Res Snapshot
[ESC] Exit
""" % [weapon_str, vis_str, spin_str]

func _capture_snapshot(p_path: String) -> void:
	var img = get_viewport().get_texture().get_image()
	var dir = DirAccess.open("res://")
	if not dir.dir_exists("renders"):
		dir.make_dir("renders")
	img.save_png(p_path)
	print("[HOLODECK STUDIO] Snapshot captured to: ", p_path)
