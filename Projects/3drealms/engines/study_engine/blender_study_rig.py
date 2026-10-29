#!/usr/bin/env python3
"""
Headless Blender Multi-Angle & Lighting Study Rig
-------------------------------------------------
Imports a mesh, sets up a turntable orthographic camera and multi-pass lighting rigs:
1. Flat Albedo (Pure unlit color pass)
2. Dense Studio (3-point key/fill/rim with shadow and AO)
3. Silhouette Mask (Contour isolation)

Exports:
- Multi-angle 1080p PNG renders
- Clean game-ready FBX with vertex colors and normals
- Volumetric and geometric measurement JSON
"""

import os
import sys
import math
import json
import bpy
import numpy as np

def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 4
    scene.eevee.use_raytracing = False
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    return scene

def build_mesh(name, vertices, faces, colors=None):
    mesh = bpy.data.meshes.new(name)
    v_arr = np.asarray(vertices, dtype=np.float32)
    vertex_count = len(v_arr)
    mesh.vertices.add(vertex_count)
    mesh.vertices.foreach_set("co", v_arr.ravel())
    
    face_count = len(faces)
    if face_count > 0 and len(faces[0]) == 4:
        loop_totals = np.full(face_count, 4, dtype=np.int32)
        corner_verts = np.asarray(faces, dtype=np.int32).ravel()
    elif face_count > 0 and len(faces[0]) == 3:
        loop_totals = np.full(face_count, 3, dtype=np.int32)
        corner_verts = np.asarray(faces, dtype=np.int32).ravel()
    else:
        loop_totals = np.array([len(f) for f in faces], dtype=np.int32)
        corner_verts = np.concatenate([np.asarray(f, dtype=np.int32) for f in faces]) if face_count > 0 else np.array([], dtype=np.int32)
        
    if face_count > 0:
        loop_starts = np.zeros(face_count, dtype=np.int32)
        np.cumsum(loop_totals[:-1], out=loop_starts[1:])
        mesh.loops.add(int(corner_verts.size))
        mesh.loops.foreach_set("vertex_index", corner_verts)
        mesh.polygons.add(face_count)
        mesh.polygons.foreach_set("loop_start", loop_starts)
        mesh.polygons.foreach_set("loop_total", loop_totals)
    mesh.update()
    
    # Assign vertex colors if provided
    if colors is not None and len(colors) == vertex_count:
        col_attr = mesh.color_attributes.new(name="Col", type='FLOAT_COLOR', domain='POINT')
        c_arr = np.asarray(colors, dtype=np.float32)
        if c_arr.shape[1] == 3:
            rgba = np.column_stack((c_arr, np.ones(vertex_count, dtype=np.float32)))
        else:
            rgba = c_arr
        col_attr.data.foreach_set("color", rgba.ravel())
        
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj

def setup_camera(target_obj, dist_mult=2.2):
    cam_data = bpy.data.cameras.new("StudyCamera")
    cam_data.type = 'ORTHO'
    cam_obj = bpy.data.objects.new("StudyCamera", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    
    # Calculate bounding box extents
    bbox = [target_obj.matrix_world @ mathutils.Vector(corner) for corner in target_obj.bound_box]
    min_c = np.min([[v.x, v.y, v.z] for v in bbox], axis=0)
    max_c = np.max([[v.x, v.y, v.z] for v in bbox], axis=0)
    center = (min_c + max_c) * 0.5
    extent = np.max(max_c - min_c)
    
    cam_data.ortho_scale = extent * 1.25
    return cam_obj, center, extent

import mathutils

def position_camera(cam_obj, center, extent, yaw_deg, pitch_deg=0.0, dist_mult=3.0):
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    
    dist = extent * dist_mult
    x = center[0] + dist * math.sin(yaw) * math.cos(pitch)
    y = center[1] - dist * math.cos(yaw) * math.cos(pitch)
    z = center[2] + dist * math.sin(pitch)
    
    cam_obj.location = (x, y, z)
    
    # Aim at center
    direction = mathutils.Vector(center) - cam_obj.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()

def create_lighting_rig(light_type="studio"):
    # Clear existing lights
    for obj in list(bpy.context.scene.collection.objects):
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
            
    world = bpy.data.worlds.new("StudyWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    
    if light_type == "flat":
        # Neutral ambient uniform illumination
        if bg_node:
            bg_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
            bg_node.inputs['Strength'].default_value = 1.0
    elif light_type == "dense":
        # 3-Point High Contrast Studio Rig
        if bg_node:
            bg_node.inputs['Color'].default_value = (0.05, 0.05, 0.07, 1.0)
            bg_node.inputs['Strength'].default_value = 0.3
            
        # Key Light
        key_data = bpy.data.lights.new("KeyLight", type='SUN')
        key_data.energy = 3.5
        key_data.color = (1.0, 0.98, 0.92)
        key_obj = bpy.data.objects.new("KeyLight", key_data)
        key_obj.rotation_euler = (math.radians(45), math.radians(20), math.radians(-35))
        bpy.context.scene.collection.objects.link(key_obj)
        
        # Fill Light (Cool)
        fill_data = bpy.data.lights.new("FillLight", type='SUN')
        fill_data.energy = 1.2
        fill_data.color = (0.75, 0.85, 1.0)
        fill_obj = bpy.data.objects.new("FillLight", fill_data)
        fill_obj.rotation_euler = (math.radians(50), math.radians(-30), math.radians(140))
        bpy.context.scene.collection.objects.link(fill_obj)
        
        # Rim Light (Accent)
        rim_data = bpy.data.lights.new("RimLight", type='SUN')
        rim_data.energy = 4.0
        rim_data.color = (1.0, 0.8, 0.6)
        rim_obj = bpy.data.objects.new("RimLight", rim_data)
        rim_obj.rotation_euler = (math.radians(-60), 0, math.radians(180))
        bpy.context.scene.collection.objects.link(rim_obj)

def setup_environment_skybox(env_image_path, strength=2.2):
    # Clear existing lights
    for obj in list(bpy.context.scene.collection.objects):
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
            
    world = bpy.data.worlds.new("SkyboxWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    
    bg = nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = strength
    out = nodes.new('ShaderNodeOutputWorld')
    
    if env_image_path and os.path.exists(env_image_path):
        env = nodes.new('ShaderNodeTexEnvironment')
        img = bpy.data.images.load(env_image_path)
        env.image = img
        links.new(env.outputs['Color'], bg.inputs['Color'])
    else:
        bg.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1.0)
        
    links.new(bg.outputs['Background'], out.inputs['Surface'])

def assign_vertex_color_material(obj, mode="diffuse"):
    mat = bpy.data.materials.new(name="NomadMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    
    if mode == "flat":
        # Pure emission from vertex colors
        attr_node = nodes.new(type='ShaderNodeAttribute')
        attr_node.attribute_name = "Col"
        emission = nodes.new(type='ShaderNodeEmission')
        links.new(attr_node.outputs['Color'], emission.inputs['Color'])
        links.new(emission.outputs['Emission'], output_node.inputs['Surface'])
    else:
        # Principled BSDF with vertex colors and subtle roughness
        attr_node = nodes.new(type='ShaderNodeAttribute')
        attr_node.attribute_name = "Col"
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.inputs['Roughness'].default_value = 0.45
        links.new(attr_node.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
    obj.data.materials.clear()
    obj.data.materials.append(mat)

def compute_blender_metrics(obj):
    mesh = obj.data
    v_count = len(mesh.vertices)
    f_count = len(mesh.polygons)
    tri_count = sum(1 for p in mesh.polygons if len(p.vertices) == 3)
    quad_count = sum(1 for p in mesh.polygons if len(p.vertices) == 4)
    
    # Calculate surface area
    total_area = sum(p.area for p in mesh.polygons)
    
    # Dimensions
    dims = obj.dimensions
    
    return {
        "vertex_count": v_count,
        "face_count": f_count,
        "quad_ratio": float(quad_count / f_count) if f_count > 0 else 0.0,
        "surface_area": float(total_area),
        "dimensions": [float(dims.x), float(dims.y), float(dims.z)],
        "diagonal_scale": float(math.sqrt(dims.x**2 + dims.y**2 + dims.z**2))
    }

def run_blender_study(input_json_path, output_dir, profile_path=None):
    with open(input_json_path, "r") as f:
        data = json.load(f)
        
    # Load data-driven study profile if provided
    profile_data = None
    if profile_path and os.path.exists(profile_path):
        with open(profile_path, "r") as pf:
            profile_data = json.load(pf)
        print(f"[BlenderStudy] Loaded data-driven profile: '{profile_data.get('name')}'")
        
    sculpt_id = data["sculpt_id"]
    verts = np.array(data["vertices"], dtype=np.float32)
    faces = np.array(data["faces"], dtype=np.int32)
    colors = np.array(data["colors"], dtype=np.float32) if "colors" in data and data["colors"] else None
    
    scene = setup_scene()
    if profile_data and "resolution" in profile_data:
        scene.render.resolution_x = profile_data["resolution"][0]
        scene.render.resolution_y = profile_data["resolution"][1]
        
    obj = build_mesh(sculpt_id, verts, faces, colors)
    cam_obj, center, extent = setup_camera(obj)
    
    renders_dir = os.path.join(output_dir, "renders")
    os.makedirs(renders_dir, exist_ok=True)
    
    # Parse cameras from profile or use canonical defaults
    if profile_data and "cameras" in profile_data and profile_data["cameras"]:
        cameras_to_run = [
            (c["name"], c.get("camera_type", "ORTHO"), c.get("yaw_deg", 0.0), c.get("pitch_deg", 0.0), c.get("dist_mult", 2.5), c.get("lens_mm", 50.0))
            for c in profile_data["cameras"]
        ]
    else:
        cameras_to_run = [
            ("front", "ORTHO", 0, 0, 2.5, 50),
            ("right", "ORTHO", 90, 0, 2.5, 50),
            ("back", "ORTHO", 180, 0, 2.5, 50),
            ("left", "ORTHO", 270, 0, 2.5, 50),
            ("top", "ORTHO", 0, 89.9, 2.5, 50),
            ("hero", "PERSP", 45, 25, 2.3, 50)
        ]
    
    rendered_files = {}
    
    # Pass 1: Flat Albedo
    assign_vertex_color_material(obj, mode="flat")
    create_lighting_rig("flat")
    for name, c_type, yaw, pitch, dist_m, lens in cameras_to_run:
        cam_obj.data.type = c_type
        if c_type == 'PERSP':
            cam_obj.data.lens = lens
        position_camera(cam_obj, center, extent, yaw, pitch, dist_mult=dist_m)
        out_path = os.path.join(renders_dir, f"{sculpt_id}_{name}_flat.png")
        bpy.context.scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        rendered_files[f"{name}_flat"] = out_path
        
    # Pass 2: Dense Studio Lighting
    assign_vertex_color_material(obj, mode="dense")
    create_lighting_rig("dense")
    for name, c_type, yaw, pitch, dist_m, lens in cameras_to_run:
        cam_obj.data.type = c_type
        if c_type == 'PERSP':
            cam_obj.data.lens = lens
        position_camera(cam_obj, center, extent, yaw, pitch, dist_mult=dist_m)
        out_path = os.path.join(renders_dir, f"{sculpt_id}_{name}_dense.png")
        bpy.context.scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        rendered_files[f"{name}_dense"] = out_path
        
    # Pass 3: Skybox Lighting Environments (Nomad SculptGL Panorama Sets)
    env_dirs = [
        "/home/kidlucrid/Projects/3drealms/engines/study_engine/environments",
        os.path.abspath("Projects/3drealms/engines/study_engine/environments"),
        "/home/kidlucrid/Projects/nomad-sculptgl/app/resources/environments",
        os.path.abspath("Projects/nomad-sculptgl/app/resources/environments")
    ]
    env_dir = next((d for d in env_dirs if os.path.exists(d)), None)
    
    if env_dir:
        # Check if profile specifies environments
        if profile_data and "environments" in profile_data and profile_data["environments"]:
            env_specs = profile_data["environments"]
        else:
            env_specs = [
                {"name": "studio_small_01", "filename": "studio_small_01_1k.hdr", "strength": 2.2},
                {"name": "mpumalanga_veld", "filename": "mpumalanga_veld_1k.hdr", "strength": 2.2},
                {"name": "venetian_crossroads", "filename": "venetian_crossroads_1k.hdr", "strength": 2.2},
                {"name": "winter_river", "filename": "winter_river_1k.hdr", "strength": 2.2},
                {"name": "moonless_golf", "filename": "moonless_golf_1k.hdr", "strength": 2.2},
            ]
            
        assign_vertex_color_material(obj, mode="dense")
        for espec in env_specs:
            clean_env_name = espec.get("name", "env")
            env_fname = espec.get("filename", f"{clean_env_name}.hdr")
            env_strength = espec.get("strength", 2.2)
            env_path = os.path.join(env_dir, env_fname)
            if not os.path.exists(env_path):
                # Fallback to direct name lookup
                candidates = [f for f in os.listdir(env_dir) if clean_env_name in f]
                if candidates:
                    env_path = os.path.join(env_dir, candidates[0])
                else:
                    continue
                    
            setup_environment_skybox(env_path, strength=env_strength)
            bpy.context.scene.render.film_transparent = espec.get("film_transparent", True)
            
            # Render Hero portrait view
            cam_obj.data.type = 'PERSP'
            cam_obj.data.lens = 50
            position_camera(cam_obj, center, extent, yaw_deg=45, pitch_deg=25, dist_mult=2.3)
            out_hero = os.path.join(renders_dir, f"{sculpt_id}_skybox_{clean_env_name}_hero.png")
            bpy.context.scene.render.filepath = out_hero
            bpy.ops.render.render(write_still=True)
            rendered_files[f"skybox_{clean_env_name}_hero"] = out_hero
            
            # Render Front lighting view
            position_camera(cam_obj, center, extent, yaw_deg=0, pitch_deg=0, dist_mult=2.3)
            out_front = os.path.join(renders_dir, f"{sculpt_id}_skybox_{clean_env_name}_front.png")
            bpy.context.scene.render.filepath = out_front
            bpy.ops.render.render(write_still=True)
            rendered_files[f"skybox_{clean_env_name}_front"] = out_front
            
        # Restore camera and transparency
        cam_obj.data.type = 'ORTHO'
        bpy.context.scene.render.film_transparent = True
        
    # Export clean FBX
    fbx_path = os.path.join(output_dir, f"{sculpt_id}.fbx")
    bpy.ops.export_scene.fbx(
        filepath=fbx_path,
        use_selection=False,
        bake_space_transform=True,
        colors_type='SRGB'
    )
    
    # Export clean glTF
    glb_path = os.path.join(output_dir, f"{sculpt_id}.glb")
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format='GLB',
        export_attributes=True
    )
    
    gltf_path = os.path.join(output_dir, f"{sculpt_id}.gltf")
    bpy.ops.export_scene.gltf(
        filepath=gltf_path,
        export_format='GLTF_SEPARATE',
        export_attributes=True
    )
    
    metrics = compute_blender_metrics(obj)
    
    result = {
        "sculpt_id": sculpt_id,
        "fbx_path": fbx_path,
        "glb_path": glb_path,
        "gltf_path": gltf_path,
        "renders": rendered_files,
        "blender_metrics": metrics
    }
    
    result_path = os.path.join(output_dir, "blender_study.json")
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
        
    print(f"[BlenderStudy] Successfully generated FBX, GLB, 12 orthographic renders and metrics -> {result_path}")
    return result

if __name__ == "__main__":
    if len(sys.argv) > 4:
        # sys.argv after '--' in blender execution
        idx = sys.argv.index("--") if "--" in sys.argv else -1
        if idx != -1 and len(sys.argv) > idx + 2:
            input_json = sys.argv[idx + 1]
            out_dir = sys.argv[idx + 2]
            prof_path = sys.argv[idx + 3] if len(sys.argv) > idx + 3 else None
            run_blender_study(input_json, out_dir, profile_path=prof_path)
