# @tool
class_name QEMSolver
extends RefCounted

## Quadric Error Metric (Garland-Heckbert Formulation)
## Solves fundamental error quadrics Kp = p * p^T for 3D triangle planes and finds
## optimal contraction points v* minimizing delta(v*) = v*^T * (Q1 + Q2) * v*.

## Symmetric 4x4 matrix representation stored as 10 unique floats:
## [ a00 a01 a02 a03 ]
## [ a01 a11 a12 a13 ]
## [ a02 a12 a22 a23 ]
## [ a03 a13 a23 a33 ]
class SymQuadric:
	var a00: float = 0.0
	var a01: float = 0.0
	var a02: float = 0.0
	var a03: float = 0.0
	var a11: float = 0.0
	var a12: float = 0.0
	var a13: float = 0.0
	var a22: float = 0.0
	var a23: float = 0.0
	var a33: float = 0.0

	func _init(p_a00: float = 0.0, p_a01: float = 0.0, p_a02: float = 0.0, p_a03: float = 0.0,
			   p_a11: float = 0.0, p_a12: float = 0.0, p_a13: float = 0.0,
			   p_a22: float = 0.0, p_a23: float = 0.0, p_a33: float = 0.0) -> void:
		a00 = p_a00; a01 = p_a01; a02 = p_a02; a03 = p_a03
		a11 = p_a11; a12 = p_a12; a13 = p_a13
		a22 = p_a22; a23 = p_a23; a33 = p_a33

	func add(other: SymQuadric) -> SymQuadric:
		return SymQuadric.new(
			a00 + other.a00, a01 + other.a01, a02 + other.a02, a03 + other.a03,
			a11 + other.a11, a12 + other.a12, a13 + other.a13,
			a22 + other.a22, a23 + other.a23, a33 + other.a33
		)

	func add_in_place(other: SymQuadric) -> void:
		a00 += other.a00; a01 += other.a01; a02 += other.a02; a03 += other.a03
		a11 += other.a11; a12 += other.a12; a13 += other.a13
		a22 += other.a22; a23 += other.a23; a33 += other.a33

	## Evaluate quadratic error delta(v) = v^T * Q * v
	func evaluate(v: Vector3) -> float:
		var x: float = v.x
		var y: float = v.y
		var z: float = v.z
		return (
			a00 * x * x + 2.0 * a01 * x * y + 2.0 * a02 * x * z + 2.0 * a03 * x +
			a11 * y * y + 2.0 * a12 * y * z + 2.0 * a13 * y +
			a22 * z * z + 2.0 * a23 * z +
			a33
		)

## Construct fundamental quadric Kp from triangle vertices
static func compute_plane_quadric(p1: Vector3, p2: Vector3, p3: Vector3) -> SymQuadric:
	var edge1: Vector3 = p2 - p1
	var edge2: Vector3 = p3 - p1
	var normal: Vector3 = edge1.cross(edge2)
	var area: float = normal.length()
	
	if area < 1e-9:
		return SymQuadric.new()
	
	normal /= area
	var d: float = -normal.dot(p1)
	var a: float = normal.x
	var b: float = normal.y
	var c: float = normal.z
	
	# Scale by triangle area to weight larger triangles more heavily
	var w: float = area * 0.5
	return SymQuadric.new(
		w * a * a, w * a * b, w * a * c, w * a * d,
		w * b * b, w * b * c, w * b * d,
		w * c * c, w * c * d,
		w * d * d
	)

## Find optimal contraction point v* for edge (v1, v2) that minimizes quadric error
static func find_optimal_contraction(q: SymQuadric, v1: Vector3, v2: Vector3) -> Dictionary:
	# Solve system:
	# [ a00 a01 a02 ] [ x ]   [ -a03 ]
	# [ a01 a11 a12 ] [ y ] = [ -a13 ]
	# [ a02 a12 a22 ] [ z ]   [ -a23 ]
	var det: float = (
		q.a00 * (q.a11 * q.a22 - q.a12 * q.a12) -
		q.a01 * (q.a01 * q.a22 - q.a12 * q.a02) +
		q.a02 * (q.a01 * q.a12 - q.a11 * q.a02)
	)

	if abs(det) > 1e-6:
		var inv_det: float = 1.0 / det
		var b0: float = -q.a03
		var b1: float = -q.a13
		var b2: float = -q.a23

		var m00: float = q.a11 * q.a22 - q.a12 * q.a12
		var m01: float = q.a02 * q.a12 - q.a01 * q.a22
		var m02: float = q.a01 * q.a12 - q.a02 * q.a11

		var m10: float = m01
		var m11: float = q.a00 * q.a22 - q.a02 * q.a02
		var m12: float = q.a02 * q.a01 - q.a00 * q.a12

		var m20: float = m02
		var m21: float = m12
		var m22: float = q.a00 * q.a11 - q.a01 * q.a01

		var optimal: Vector3 = Vector3(
			(m00 * b0 + m01 * b1 + m02 * b2) * inv_det,
			(m10 * b0 + m11 * b1 + m12 * b2) * inv_det,
			(m20 * b0 + m21 * b1 + m22 * b2) * inv_det
		)

		var opt_cost: float = q.evaluate(optimal)
		return {"target": optimal, "cost": max(0.0, opt_cost)}

	# Degenerate matrix fallback: evaluate v1, v2, and midpoint (v1 + v2) * 0.5
	var midpoint: Vector3 = (v1 + v2) * 0.5
	var cost1: float = q.evaluate(v1)
	var cost2: float = q.evaluate(v2)
	var cost_mid: float = q.evaluate(midpoint)

	var best_target: Vector3 = midpoint
	var best_cost: float = cost_mid

	if cost1 < best_cost:
		best_target = v1
		best_cost = cost1
	if cost2 < best_cost:
		best_target = v2
		best_cost = cost2

	return {"target": best_target, "cost": max(0.0, best_cost)}
