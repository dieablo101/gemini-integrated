# CollisionShapeGenerator [PLACEHOLDER]
# Utility script: inspects 3D mesh AABBs and generates fitted CollisionShape3D capsules/boxes.
class_name CollisionShapeGenerator
extends RefCounted

static func create_capsule_from_aabb(aabb: AABB) -> CapsuleShape3D:
	var shape = CapsuleShape3D.new()
	var radius = max(aabb.size.x, aabb.size.z) * 0.5
	var height = max(aabb.size.y, radius * 2.0)
	shape.radius = radius
	shape.height = height
	return shape
