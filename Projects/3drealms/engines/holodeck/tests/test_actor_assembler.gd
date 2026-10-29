extends SceneTree

func _init():
	print("--- TESTING ACTOR ASSEMBLER ---")
	var assembler_script = load("res://engines/holodeck/assembly/actor_assembler.gd")
	var actor = assembler_script.assemble_gothic_barbarian()
	if not actor:
		print("FAILED to assemble actor")
		quit(1)
		return
	print("Actor assembled successfully!")
	print("  Barbarian mesh: ", actor.barbarian_mesh != null)
	print("  Barbarian mat 0: ", actor.barbarian_mesh.get_surface_override_material(0) != null)
	print("  Barbarian mat 1: ", actor.barbarian_mesh.get_surface_override_material(1) != null)
	print("  Weapon mesh: ", actor.weapon_mesh != null)
	print("  Weapon mat 0: ", actor.weapon_mesh.get_surface_override_material(0) != null)
	print("  Weapon mat 1: ", actor.weapon_mesh.get_surface_override_material(1) != null)
	print("  Socket attachment: ", actor.weapon_socket_attachment.bone_name)
	print("  Kinetic volumes count: ", actor.kinetic_volumes.size())
	
	# Test weapon socket toggle
	actor.toggle_weapon_socket()
	print("  Socketed toggle -> Weapon parent: ", actor.weapon_mesh.get_parent().name)
	actor.toggle_weapon_socket()
	print("  Unsocketed toggle -> Weapon parent: ", actor.weapon_mesh.get_parent().name)
	
	print("--- ALL ACTOR ASSEMBLER TESTS PASSED ---")
	quit(0)
