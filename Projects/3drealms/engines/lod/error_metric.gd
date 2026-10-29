# @tool
class_name ScreenErrorMetric
extends RefCounted

## Screen-Space Geometric Error Evaluator (Unreal / Nanite Style)
## Translates continuous 3D geometric deviation (in world meters) to projected screen pixels.
## Used by Holodeck and Runtime Streamers to compute pop-free LOD thresholds.

## Screen error in pixels:
## epsilon_screen = (delta * viewport_height) / (2.0 * distance * tan(fov / 2.0))
static func calculate_screen_error_pixels(
	object_geometric_error: float,
	distance_to_camera: float,
	fov_degrees: float = 75.0,
	viewport_height_pixels: float = 1080.0
) -> float:
	if distance_to_camera <= 0.001:
		return 999999.0
	
	var half_fov_rad: float = deg_to_rad(fov_degrees * 0.5)
	var tan_half_fov: float = tan(half_fov_rad)
	
	var error_pixels: float = (object_geometric_error * viewport_height_pixels) / (2.0 * distance_to_camera * tan_half_fov)
	return max(0.0, error_pixels)

## Calculates the exact camera distance where geometric error drops below target pixel threshold
static func calculate_lod_switch_distance(
	object_geometric_error: float,
	target_max_pixel_error: float = 1.0,
	fov_degrees: float = 75.0,
	viewport_height_pixels: float = 1080.0
) -> float:
	if target_max_pixel_error <= 0.0001:
		return 99999.0
	
	var half_fov_rad: float = deg_to_rad(fov_degrees * 0.5)
	var tan_half_fov: float = tan(half_fov_rad)
	
	var distance: float = (object_geometric_error * viewport_height_pixels) / (2.0 * target_max_pixel_error * tan_half_fov)
	return max(0.1, distance)

## Generates smooth hysteresis bounds for switching LODs without rapid oscillating/popping
static func calculate_hysteresis_range(
	switch_distance: float,
	hysteresis_ratio: float = 0.10
) -> Dictionary:
	var delta: float = switch_distance * hysteresis_ratio
	return {
		"distance": switch_distance,
		"drop_to_lower_lod_distance": switch_distance + delta,  # Camera moving further away
		"promote_to_higher_lod_distance": max(0.1, switch_distance - delta) # Camera moving closer
	}
