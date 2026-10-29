class_name PainterRecipe
extends Resource

## PainterRecipe (Holodeck Substance Painter Pipeline)
## Defines a completely serializable painting manifest for an entity or prop.
## Decouples creative/material specifications from physical engine rendering.

@export var recipe_name: String = "Untitled Recipe"
@export var target_mesh_path: String = ""
@export var bake_resolution: int = 1024

## Semantic slot mapping: ID / surface index -> semantic label
## e.g. { 0: "blade", 1: "crossguard", 2: "grip" }
@export var semantic_slots: Dictionary = {}

## Layer definitions per semantic slot
## Dictionary structured as:
## {
##   "blade": [
##     {
##       "name": "Base Steel",
##       "flux_shader": "res://Projects/3drealms/engines/flux/shaders/obsidian_basalt.gdshader",
##       "blend_mode": "mix",
##       "uniforms": { "roughness": 0.25, "metallic": 0.95, "albedo_tint": Color(0.85, 0.88, 0.92) }
##     },
##     {
##       "name": "Edge Scuffs",
##       "mask_type": "curvature",
##       "mask_threshold": 0.65,
##       "mask_softness": 0.15,
##       "uniforms": { "roughness": 0.6, "metallic": 0.8, "albedo_tint": Color(1.0, 1.0, 1.0) }
##     },
##     {
##       "name": "Crevice Grime",
##       "mask_type": "ambient_occlusion",
##       "mask_threshold": 0.4,
##       "mask_softness": 0.25,
##       "uniforms": { "roughness": 0.95, "metallic": 0.05, "albedo_tint": Color(0.12, 0.10, 0.08) }
##     }
##   ]
## }
@export var layers_by_slot: Dictionary = {}

## Exports recipe state to a pure JSON string for AI manifest exchange or remote caching
func to_json_dict() -> Dictionary:
	return {
		"recipe_name": recipe_name,
		"target_mesh_path": target_mesh_path,
		"bake_resolution": bake_resolution,
		"semantic_slots": semantic_slots,
		"layers_by_slot": layers_by_slot
	}

## Hydrates recipe from a JSON dictionary
static func from_json_dict(data: Dictionary) -> PainterRecipe:
	var r = PainterRecipe.new()
	r.recipe_name = data.get("recipe_name", "Untitled Recipe")
	r.target_mesh_path = data.get("target_mesh_path", "")
	r.bake_resolution = int(data.get("bake_resolution", 1024))
	r.semantic_slots = data.get("semantic_slots", {})
	r.layers_by_slot = data.get("layers_by_slot", {})
	return r
