"""
generate_gothic_barbarian.py
Procedurally builds a High-Poly Gothic Barbarian with Armature, Sockets,
UV Maps, Material Slots, and an Epic Gothic Greatsword resting beside him.
Designed for Blender 5.4.0 headless execution.
"""

import bpy
import bmesh
import math
from mathutils import Vector, Matrix, Euler

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.armatures:
        bpy.data.armatures.remove(block)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)

def create_armature():
    arm_data = bpy.data.armatures.new("Armature_Barbarian")
    arm_obj = bpy.data.objects.new("Armature", arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    eb = arm_data.edit_bones
    
    # Root & Hips
    root = eb.new("Root")
    root.head = Vector((0.0, 0.0, 0.0))
    root.tail = Vector((0.0, 0.0, 0.15))
    
    pelvis = eb.new("Pelvis")
    pelvis.head = Vector((0.0, 0.0, 1.0))
    pelvis.tail = Vector((0.0, 0.0, 1.15))
    pelvis.parent = root
    
    # Spine & Head
    spine = eb.new("Spine")
    spine.head = Vector((0.0, 0.0, 1.15))
    spine.tail = Vector((0.0, 0.0, 1.4))
    spine.parent = pelvis
    
    chest = eb.new("Chest")
    chest.head = Vector((0.0, 0.0, 1.4))
    chest.tail = Vector((0.0, 0.0, 1.7))
    chest.parent = spine
    
    neck = eb.new("Neck")
    neck.head = Vector((0.0, 0.0, 1.7))
    neck.tail = Vector((0.0, 0.0, 1.82))
    neck.parent = chest
    
    head = eb.new("Head")
    head.head = Vector((0.0, 0.0, 1.82))
    head.tail = Vector((0.0, 0.0, 2.05))
    head.parent = neck
    
    # Left Arm
    clav_l = eb.new("Clavicle.L")
    clav_l.head = Vector((0.05, 0.0, 1.68))
    clav_l.tail = Vector((0.28, 0.0, 1.68))
    clav_l.parent = chest
    
    uparm_l = eb.new("UpperArm.L")
    uparm_l.head = Vector((0.28, 0.0, 1.68))
    uparm_l.tail = Vector((0.62, 0.0, 1.35))
    uparm_l.parent = clav_l
    
    forearm_l = eb.new("Forearm.L")
    forearm_l.head = Vector((0.62, 0.0, 1.35))
    forearm_l.tail = Vector((0.88, 0.0, 1.05))
    forearm_l.parent = uparm_l
    
    hand_l = eb.new("Hand.L")
    hand_l.head = Vector((0.88, 0.0, 1.05))
    hand_l.tail = Vector((0.98, 0.0, 0.95))
    hand_l.parent = forearm_l
    
    sock_shield = eb.new("Socket.Shield.L")
    sock_shield.head = Vector((0.75, -0.05, 1.2))
    sock_shield.tail = Vector((0.75, -0.15, 1.2))
    sock_shield.parent = forearm_l
    
    # Right Arm
    clav_r = eb.new("Clavicle.R")
    clav_r.head = Vector((-0.05, 0.0, 1.68))
    clav_r.tail = Vector((-0.28, 0.0, 1.68))
    clav_r.parent = chest
    
    uparm_r = eb.new("UpperArm.R")
    uparm_r.head = Vector((-0.28, 0.0, 1.68))
    uparm_r.tail = Vector((-0.62, 0.0, 1.35))
    uparm_r.parent = clav_r
    
    forearm_r = eb.new("Forearm.R")
    forearm_r.head = Vector((-0.62, 0.0, 1.35))
    forearm_r.tail = Vector((-0.88, 0.0, 1.05))
    forearm_r.parent = uparm_r
    
    hand_r = eb.new("Hand.R")
    hand_r.head = Vector((-0.88, 0.0, 1.05))
    hand_r.tail = Vector((-0.98, 0.0, 0.95))
    hand_r.parent = forearm_r
    
    sock_weapon = eb.new("Socket.Weapon.R")
    sock_weapon.head = Vector((-0.93, 0.0, 1.0))
    sock_weapon.tail = Vector((-0.93, 0.0, 1.15))
    sock_weapon.parent = hand_r
    
    # Left Leg
    thigh_l = eb.new("Thigh.L")
    thigh_l.head = Vector((0.18, 0.0, 1.0))
    thigh_l.tail = Vector((0.22, 0.02, 0.52))
    thigh_l.parent = pelvis
    
    calf_l = eb.new("Calf.L")
    calf_l.head = Vector((0.22, 0.02, 0.52))
    calf_l.tail = Vector((0.24, -0.02, 0.12))
    calf_l.parent = thigh_l
    
    foot_l = eb.new("Foot.L")
    foot_l.head = Vector((0.24, -0.02, 0.12))
    foot_l.tail = Vector((0.24, 0.18, 0.0))
    foot_l.parent = calf_l
    
    # Right Leg
    thigh_r = eb.new("Thigh.R")
    thigh_r.head = Vector((-0.18, 0.0, 1.0))
    thigh_r.tail = Vector((-0.22, 0.02, 0.52))
    thigh_r.parent = pelvis
    
    calf_r = eb.new("Calf.R")
    calf_r.head = Vector((-0.22, 0.02, 0.52))
    calf_r.tail = Vector((-0.24, -0.02, 0.12))
    calf_r.parent = thigh_r
    
    foot_r = eb.new("Foot.R")
    foot_r.head = Vector((-0.24, -0.02, 0.12))
    foot_r.tail = Vector((-0.24, 0.18, 0.0))
    foot_r.parent = calf_r
    
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm_obj

def tag_faces(geom, mat_index):
    verts = geom.get('verts', [])
    faces = set(f for v in verts for f in v.link_faces)
    for f in faces:
        f.material_index = mat_index

def build_gothic_barbarian_mesh():
    mesh = bpy.data.meshes.new("Mesh_Gothic_Barbarian")
    obj = bpy.data.objects.new("Gothic_Barbarian", mesh)
    bpy.context.collection.objects.link(obj)
    
    bm = bmesh.new()
    
    # 1. Gothic Cuirass (Chest & Torso armor) - Mat 0
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0.0, 0.0, 1.45)) @ Matrix.Scale(0.7, 4, (1,0,0)) @ Matrix.Scale(0.48, 4, (0,1,0)) @ Matrix.Scale(0.65, 4, (0,0,1)))
    tag_faces(res, 0)
    
    # Fluted ridge down center chest - Mat 1 (Dark Iron)
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=8, radius1=0.25, radius2=0.02, depth=0.6,
                                matrix=Matrix.Translation((0.0, -0.25, 1.45)) @ Matrix.Rotation(math.radians(-90), 4, 'X'))
    tag_faces(res, 1)
                          
    # 2. Barbarian Gothic Great Helm / Visor - Mat 0
    res = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.18,
                                    matrix=Matrix.Translation((0.0, 0.02, 1.92)))
    tag_faces(res, 0)
    # Helmet Crest / Horns - Mat 1 (Dark Iron)
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=6, radius1=0.08, radius2=0.0, depth=0.22,
                                matrix=Matrix.Translation((0.0, 0.0, 2.12)))
    tag_faces(res, 1)
                          
    # 3. Massive Tiered Gothic Pauldrons (Shoulders)
    for side, sign in [("L", 1.0), ("R", -1.0)]:
        # Upper pauldron - Mat 0
        res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.24,
                                         matrix=Matrix.Translation((sign * 0.42, 0.0, 1.70)) @ Matrix.Scale(1.2, 4, (1,0,0)) @ Matrix.Scale(0.8, 4, (0,0,1)))
        tag_faces(res, 0)
        # Gothic spike blade on shoulder - Mat 1 (Dark Iron)
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=6, radius1=0.09, radius2=0.01, depth=0.35,
                                    matrix=Matrix.Translation((sign * 0.46, 0.0, 1.88)) @ Matrix.Rotation(math.radians(sign * -25), 4, 'Y'))
        tag_faces(res, 1)
                              
    # 4. Arms & Heavy Gauntlets
    for side, sign in [("L", 1.0), ("R", -1.0)]:
        # Upper arm plate - Mat 0
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.11, radius2=0.11, depth=0.35,
                                    matrix=Matrix.Translation((sign * 0.45, 0.0, 1.52)) @ Matrix.Rotation(math.radians(sign * -40), 4, 'Y'))
        tag_faces(res, 0)
        # Forearm vambrace & gauntlet - Mat 0
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.12, radius2=0.12, depth=0.35,
                                    matrix=Matrix.Translation((sign * 0.75, 0.0, 1.20)) @ Matrix.Rotation(math.radians(sign * -45), 4, 'Y'))
        tag_faces(res, 0)
        # Armored Fist - Mat 1 (Dark Iron knuckles)
        res = bmesh.ops.create_cube(bm, size=0.18,
                                    matrix=Matrix.Translation((sign * 0.93, 0.0, 1.00)) @ Matrix.Scale(0.9, 4, (1,0,0)))
        tag_faces(res, 1)
                              
    # 5. Faulds & Tassets (Gothic Hip Armor / Battle Skirt)
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.36, radius2=0.36, depth=0.30,
                                matrix=Matrix.Translation((0.0, 0.0, 1.05)))
    tag_faces(res, 0)
    # Front Hanging Tasset Plates - Mat 1 (Dark Iron)
    for sign in [1.0, -1.0]:
        res = bmesh.ops.create_cube(bm, size=0.25,
                                    matrix=Matrix.Translation((sign * 0.16, -0.22, 0.92)) @ Matrix.Scale(0.8, 4, (1,0,0)) @ Matrix.Scale(0.2, 4, (0,1,0)) @ Matrix.Scale(1.4, 4, (0,0,1)))
        tag_faces(res, 1)
                              
    # 6. Legs & Sabatons (Greaves & Armored Boots)
    for side, sign in [("L", 1.0), ("R", -1.0)]:
        # Thigh cuisse - Mat 0
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.16, radius2=0.16, depth=0.45,
                                    matrix=Matrix.Translation((sign * 0.20, 0.01, 0.75)))
        tag_faces(res, 0)
        # Knee poleyn - Mat 1 (Dark Iron)
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=8, radius1=0.14, radius2=0.03, depth=0.18,
                                    matrix=Matrix.Translation((sign * 0.20, -0.15, 0.52)) @ Matrix.Rotation(math.radians(-90), 4, 'X'))
        tag_faces(res, 1)
        # Shin greave - Mat 0
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.13, radius2=0.13, depth=0.40,
                                    matrix=Matrix.Translation((sign * 0.23, -0.01, 0.30)))
        tag_faces(res, 0)
        # Sabaton (gothic pointed armored boot) - Mat 1
        res = bmesh.ops.create_cube(bm, size=0.26,
                                    matrix=Matrix.Translation((sign * 0.23, 0.08, 0.08)) @ Matrix.Scale(0.65, 4, (1,0,0)) @ Matrix.Scale(1.5, 4, (0,1,0)) @ Matrix.Scale(0.6, 4, (0,0,1)))
        tag_faces(res, 1)

    # Subdivide for high-poly crispness
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(verbose=False)
    return obj

def build_gothic_greatsword():
    mesh = bpy.data.meshes.new("Mesh_Gothic_Greatsword")
    obj = bpy.data.objects.new("Gothic_Greatsword", mesh)
    bpy.context.collection.objects.link(obj)
    
    bm = bmesh.new()
    
    # Position: standing vertically at x = -1.2m, beside Barbarian's right hand
    base_pos = Vector((-1.20, 0.0, 0.0))
    
    # 1. Pommel - Mat 0
    res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.065,
                               matrix=Matrix.Translation(base_pos + Vector((0.0, 0.0, 0.06))))
    tag_faces(res, 0)
    
    # 2. Two-Handed Leather Grip - Mat 1 (Leather)
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16, radius1=0.032, radius2=0.032, depth=0.48,
                                matrix=Matrix.Translation(base_pos + Vector((0.0, 0.0, 0.32))))
    tag_faces(res, 1)
    
    # 3. Gothic Crossguard with Down-Curved Quillons - Mat 0
    res = bmesh.ops.create_cube(bm, size=0.1,
                          matrix=Matrix.Translation(base_pos + Vector((0.0, 0.0, 0.58))) @ Matrix.Scale(5.2, 4, (1,0,0)) @ Matrix.Scale(0.5, 4, (0,1,0)) @ Matrix.Scale(0.4, 4, (0,0,1)))
    tag_faces(res, 0)
    for q_sign in [1.0, -1.0]:
        res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=6, radius1=0.035, radius2=0.005, depth=0.12,
                              matrix=Matrix.Translation(base_pos + Vector((q_sign * 0.28, 0.0, 0.54))) @ Matrix.Rotation(math.radians(q_sign * 35), 4, 'Y'))
        tag_faces(res, 0)
        
    # 4. Fluted Ricasso (Thick blade base) - Mat 0
    res = bmesh.ops.create_cube(bm, size=0.15,
                          matrix=Matrix.Translation(base_pos + Vector((0.0, 0.0, 0.70))) @ Matrix.Scale(1.1, 4, (1,0,0)) @ Matrix.Scale(0.35, 4, (0,1,0)) @ Matrix.Scale(1.2, 4, (0,0,1)))
    tag_faces(res, 0)
    
    # 5. Colossal Gothic Double-Edged Blade (1.25m long) - Mat 0
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=4, radius1=0.13, radius2=0.005, depth=1.25,
                          matrix=Matrix.Translation(base_pos + Vector((0.0, 0.0, 1.40))) @ Matrix.Scale(1.0, 4, (1,0,0)) @ Matrix.Scale(0.18, 4, (0,1,0)) @ Matrix.Rotation(math.radians(45), 4, 'Z'))
    tag_faces(res, 0)
                          
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    bm.to_mesh(mesh)
    bm.free()
    mesh.validate(verbose=False)
    return obj

def create_materials():
    mat_steel = bpy.data.materials.new(name="Mat_Gothic_Steel")
    mat_steel.use_nodes = True
    bsdf = mat_steel.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.35, 0.38, 0.42, 1.0)
        bsdf.inputs['Metallic'].default_value = 0.95
        bsdf.inputs['Roughness'].default_value = 0.28
        
    mat_iron = bpy.data.materials.new(name="Mat_Dark_Iron")
    mat_iron.use_nodes = True
    bsdf = mat_iron.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.12, 0.12, 0.14, 1.0)
        bsdf.inputs['Metallic'].default_value = 0.85
        bsdf.inputs['Roughness'].default_value = 0.45
        
    mat_leather = bpy.data.materials.new(name="Mat_Grip_Leather")
    mat_leather.use_nodes = True
    bsdf = mat_leather.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.15, 0.08, 0.04, 1.0)
        bsdf.inputs['Metallic'].default_value = 0.0
        bsdf.inputs['Roughness'].default_value = 0.85
        
    return mat_steel, mat_iron, mat_leather

def main(output_gltf_path):
    print(">>> [BLENDER 5.4] Generating High-Poly Gothic Barbarian with Dual Materials...")
    clear_scene()
    
    armature = create_armature()
    barbarian = build_gothic_barbarian_mesh()
    greatsword = build_gothic_greatsword()
    
    mat_steel, mat_iron, mat_leather = create_materials()
    barbarian.data.materials.append(mat_steel)
    barbarian.data.materials.append(mat_iron)
    
    greatsword.data.materials.append(mat_steel)
    greatsword.data.materials.append(mat_leather)
    
    # Smart UV Unwrap on both meshes for FLUX PBR
    for obj in [barbarian, greatsword]:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
        bpy.ops.object.mode_set(mode='OBJECT')
        
    # Parent Barbarian Mesh to Armature with Automatic Weights
    barbarian.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    
    print(f">>> Barbarian Vertices: {len(barbarian.data.vertices)} | Greatsword Vertices: {len(greatsword.data.vertices)}")
    
    # Export glTF
    print(f">>> Exporting glTF to: {output_gltf_path}")
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(
        filepath=output_gltf_path,
        export_format='GLB',
        export_apply=False,
        export_skins=True,
        export_morph=False,
        export_yup=True
    )
    print(">>> glTF Export Successfully Completed.")

if __name__ == "__main__":
    import sys
    out_path = "/home/kidlucrid/Projects/3drealms/models/characters/male/highpoly/gothic_barbarian.glb"
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            out_path = sys.argv[i+1]
    main(out_path)
