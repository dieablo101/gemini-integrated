class_name HolodeckEngine
extends RefCounted

## HolodeckEngine (Substance Painter Core Engine API)
## Headless, programmatic facade for AI agents and game systems.
## Orchestrates baking, semantic segmentation, FLUX layer compositing, and viewport rendering.

const Baker = preload("res://engines/holodeck/painter/holodeck_baker.gd")
const Segmenter = preload("res://engines/holodeck/painter/semantic_segmenter.gd")
const Compositor = preload("res://engines/holodeck/painter/layer_compositor.gd")
const ViewportBridgeClass = preload("res://engines/holodeck/painter/viewport_bridge.gd")
const Recipe = preload("res://engines/holodeck/recipes/painter_recipe.gd")

## Runs the full painting pipeline for a mesh based on a PainterRecipe
static func execute_recipe(mesh_instance: MeshInstance3D, recipe: PainterRecipe, bake_res: int = 1024) -> Dictionary:
	var result = {
		"status": "in_progress",
		"baked_maps": null,
		"materials": {},
		"errors": []
	}
	
	if not mesh_instance or not mesh_instance.mesh:
		result["status"] = "error"
		result["errors"].append("MeshInstance3D or its mesh resource is null.")
		return result
		
	# 1. Headless Map Baking
	var baked = Baker.bake_mesh_maps(mesh_instance.mesh, bake_res)
	result["baked_maps"] = baked
	
	# 2. Semantic Analysis
	var slots = Segmenter.analyze_mesh(mesh_instance.mesh)
	Segmenter.bind_semantic_names(slots, recipe.semantic_slots)
	
	# 3. Layer Compositing per Slot
	for slot in slots:
		var slot_mat = Compositor.composite_material(recipe, slot.name, baked)
		mesh_instance.set_surface_override_material(slot.surface_index, slot_mat)
		result["materials"][slot.name] = slot_mat
		
	result["status"] = "success"
	return result

## Spawns a headless viewport harness to capture preview renders from multiple angles
static func capture_preview(mesh_instance: MeshInstance3D, output_png_path: String, camera_yaw: float = 45.0, camera_pitch: float = 25.0) -> Error:
	var bridge = ViewportBridgeClass.new(Vector2i(1024, 1024))
	bridge.mount_mesh(mesh_instance)
	bridge.set_camera_orbit(camera_yaw, camera_pitch)
	
	# Force render cycle
	var tree = Engine.get_main_loop() as SceneTree
	if tree and tree.root:
		tree.root.add_child(bridge)
		# Allow one frame for draw
		bridge.render_target_update_mode = SubViewport.UPDATE_ONCE
		var err = bridge.capture_snapshot(output_png_path)
		tree.root.remove_child(bridge)
		bridge.queue_free()
		return err
	else:
		return bridge.capture_snapshot(output_png_path)
