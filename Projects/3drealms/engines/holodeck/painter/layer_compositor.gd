class_name LayerCompositor
extends RefCounted

## LayerCompositor (Holodeck Smart Material Engine)
## Stacks and blends FLUX procedural layers using baked curvature, AO, and ID maps.
## Produces a game-ready Godot 4 Spatial ShaderMaterial.

const COMPOSITOR_SHADER_PATH = "res://engines/holodeck/painter/holodeck_compositor.gdshader"

## Assembles a complete composite ShaderMaterial for a target semantic slot
static func composite_material(recipe: PainterRecipe, slot_name: String, baked_maps: HolodeckBaker.BakeResults) -> ShaderMaterial:
	var mat = ShaderMaterial.new()
	if ResourceLoader.exists(COMPOSITOR_SHADER_PATH):
		mat.shader = load(COMPOSITOR_SHADER_PATH)
	else:
		push_warning("[LayerCompositor] Compositor shader not found at " + COMPOSITOR_SHADER_PATH)
		return mat
		
	# 1. Bind Baked Maps
	if baked_maps:
		if baked_maps.curvature_map:
			mat.set_shader_parameter("map_curvature", baked_maps.curvature_map)
		if baked_maps.ao_map:
			mat.set_shader_parameter("map_ambient_occlusion", baked_maps.ao_map)
		if baked_maps.thickness_map:
			mat.set_shader_parameter("map_thickness", baked_maps.thickness_map)
		if baked_maps.id_map:
			mat.set_shader_parameter("map_material_id", baked_maps.id_map)

	# 2. Extract layers for this slot from the recipe
	var layers = recipe.layers_by_slot.get(slot_name, []) as Array
	for layer in layers:
		var l_dict = layer as Dictionary
		var mask_type = l_dict.get("mask_type", "base")
		var uniforms = l_dict.get("uniforms", {}) as Dictionary
		
		match mask_type:
			"base":
				_apply_base_layer(mat, uniforms)
			"curvature":
				_apply_wear_layer(mat, l_dict, uniforms)
			"ambient_occlusion":
				_apply_grime_layer(mat, l_dict, uniforms)
				
	return mat

static func _apply_base_layer(mat: ShaderMaterial, uniforms: Dictionary) -> void:
	if uniforms.has("albedo_tint"):
		mat.set_shader_parameter("base_albedo", uniforms["albedo_tint"])
	if uniforms.has("roughness"):
		mat.set_shader_parameter("base_roughness", float(uniforms["roughness"]))
	if uniforms.has("metallic"):
		mat.set_shader_parameter("base_metallic", float(uniforms["metallic"]))

static func _apply_wear_layer(mat: ShaderMaterial, layer: Dictionary, uniforms: Dictionary) -> void:
	if uniforms.has("albedo_tint"):
		mat.set_shader_parameter("wear_albedo", uniforms["albedo_tint"])
	if uniforms.has("roughness"):
		mat.set_shader_parameter("wear_roughness", float(uniforms["roughness"]))
	if uniforms.has("metallic"):
		mat.set_shader_parameter("wear_metallic", float(uniforms["metallic"]))
		
	if layer.has("mask_threshold"):
		mat.set_shader_parameter("wear_threshold", float(layer["mask_threshold"]))
	if layer.has("mask_softness"):
		mat.set_shader_parameter("wear_softness", float(layer["mask_softness"]))
	if layer.has("mask_intensity"):
		mat.set_shader_parameter("wear_intensity", float(layer["mask_intensity"]))

static func _apply_grime_layer(mat: ShaderMaterial, layer: Dictionary, uniforms: Dictionary) -> void:
	if uniforms.has("albedo_tint"):
		mat.set_shader_parameter("grime_albedo", uniforms["albedo_tint"])
	if uniforms.has("roughness"):
		mat.set_shader_parameter("grime_roughness", float(uniforms["roughness"]))
	if uniforms.has("metallic"):
		mat.set_shader_parameter("grime_metallic", float(uniforms["metallic"]))
		
	if layer.has("mask_threshold"):
		mat.set_shader_parameter("grime_threshold", float(layer["mask_threshold"]))
	if layer.has("mask_softness"):
		mat.set_shader_parameter("grime_softness", float(layer["mask_softness"]))
	if layer.has("mask_intensity"):
		mat.set_shader_parameter("grime_intensity", float(layer["mask_intensity"]))
