class_name FluxBridge
extends RefCounted

## FLUX Bridge (3DRealms Engine)
## Connects procedural mathematical FLUX recipes directly into Godot 4 Spatial Shaders.
## Eliminates raster PBR texture map dependencies.

const SHADER_DIR = "res://Projects/3drealms/engines/flux/shaders/"

## Returns a ShaderMaterial driven purely by mathematical FLUX kernels.
static func create_flux_material(shader_filename: String) -> ShaderMaterial:
	var path = SHADER_DIR + shader_filename
	var mat = ShaderMaterial.new()
	if ResourceLoader.exists(path):
		mat.shader = load(path)
	else:
		push_warning("[FLUX] Shader file not found at " + path)
	return mat

## Overrides procedural FLUX parameters dynamically at runtime (weathering, age, colors).
static func set_flux_uniforms(mat: ShaderMaterial, overrides: Dictionary) -> void:
	if not mat:
		return
	for key in overrides:
		mat.set_shader_parameter(key, overrides[key])
