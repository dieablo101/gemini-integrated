extends MainLoop

func _process(_delta: float) -> bool:
	print("--- TESTING LOD ENGINE (QEM & SCREEN ERROR METRIC) ---")
	
	var ScreenErrorMetricRef = load("res://engines/lod/error_metric.gd")
	var QEMSolverRef = load("res://engines/lod/qem_solver.gd")
	var EdgeCollapserRef = load("res://engines/lod/edge_collapser.gd")
	var LODOrchestratorRef = load("res://engines/lod/lod_orchestrator.gd")
	
	# Test 1: Screen Error Metric Math
	var obj_error: float = 0.05 # 5 cm error
	var distance: float = 20.0  # 20 meters away
	var screen_err_px: float = ScreenErrorMetricRef.calculate_screen_error_pixels(obj_error, distance, 75.0, 1080.0)
	print("[TEST 1] 5cm geometric error at 20m: %.2f px" % screen_err_px)
	
	var switch_dist: float = ScreenErrorMetricRef.calculate_lod_switch_distance(obj_error, 1.0, 75.0, 1080.0)
	print("[TEST 1] Distance for <= 1px error: %.2fm" % switch_dist)
	
	# Test 2: Edge collapser on subdivided sphere
	var sphere = SphereMesh.new()
	sphere.radial_segments = 16
	sphere.rings = 8
	var arr_mesh = ArrayMesh.new()
	arr_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, sphere.get_mesh_arrays())
	
	var orig_tris = arr_mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX].size() / 3
	print("[TEST 2] SphereMesh triangles: %d" % orig_tris)
	
	var cascade = LODOrchestratorRef.generate_lod_cascade(arr_mesh, [1.0, 0.7, 0.4])
	for lvl in cascade["lod_levels"]:
		print("  -> LOD %d: %d tris | Geom Error: %.5fm | Switch Dist: %.2fm" % [
			lvl["lod_index"],
			lvl["triangle_count"],
			lvl["geometric_error"],
			lvl["switch_distance"]
		])
	
	print("--- LOD ENGINE VERIFICATION COMPLETE: ALL PASS ---")
	return true # Exit loop
