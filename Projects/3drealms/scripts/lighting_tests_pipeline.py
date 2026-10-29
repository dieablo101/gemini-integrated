"""
lighting_tests_pipeline.py
EEVEE-Next Lighting & Raybounce Test Suite for Gothic Barbarian:
- Pass 1: Direct Lighting Only (0 Bounces)
- Pass 2: Screen-Space Raytracing (1 Diffuse Bounce)
- Pass 3: Fast GI Multi-Bounce Global Illumination (3 Bounces)
- Pass 4: Light Probe Irradiance Grid (Volume Light Flood)
- Pass 5: Atmospheric Fog & Volumetric God Rays
"""

import bpy
import math
import os
import time
import json
import sys

def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    glb_path = "/home/kidlucrid/Projects/3drealms/models/characters/male/highpoly/gothic_barbarian.glb"
    bpy.ops.import_scene.gltf(filepath=glb_path)
    
    # Create Pedestal
    bpy.ops.mesh.primitive_cylinder_add(radius=1.8, depth=0.15, location=(0, 0, -0.075))
    pedestal = bpy.context.active_object
    pedestal.name = "Studio_Pedestal"
    mat_ped = bpy.data.materials.new("Mat_Pedestal")
    mat_ped.use_nodes = True
    bsdf = mat_ped.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.05, 0.05, 0.07, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.35
        bsdf.inputs['Metallic'].default_value = 0.2
    pedestal.data.materials.append(mat_ped)
    
    # Camera setup (Heroic chest angle)
    bpy.ops.object.camera_add(location=(1.85, -2.55, 1.55))
    cam = bpy.context.active_object
    cam.name = "LightingCamera"
    cam.data.lens = 52
    cam.rotation_euler = (math.radians(72), math.radians(0), math.radians(35))
    bpy.context.scene.camera = cam
    
    # Resolution: 1280x720
    scene = bpy.context.scene
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    
    # Scene Engine: EEVEE
    scene.render.engine = 'BLENDER_EEVEE'
    eevee = scene.eevee
    eevee.taa_samples = 16 # Fast clean preview sampling for benchmarking
    
    # 1. Cold Steel Key Light (Sun)
    bpy.ops.object.light_add(type='SUN', location=(3, -3, 4.5))
    key = bpy.context.active_object
    key.name = "Key_ColdSteel"
    key.data.energy = 3.8
    key.data.color = (0.75, 0.88, 1.0)
    key.rotation_euler = (math.radians(45), math.radians(20), math.radians(-30))
    
    # 2. Warm Amber Torch Fill Light (Point)
    bpy.ops.object.light_add(type='POINT', location=(-2.0, -1.6, 1.35))
    fill = bpy.context.active_object
    fill.name = "Fill_AmberTorch"
    fill.data.energy = 220.0
    fill.data.color = (1.0, 0.52, 0.12)
    
    # 3. High-Intensity Sharp Rim Kicker (Spot)
    bpy.ops.object.light_add(type='SPOT', location=(-1.4, 2.8, 2.4))
    rim = bpy.context.active_object
    rim.name = "Rim_Kicker"
    rim.data.energy = 550.0
    rim.data.color = (0.65, 0.85, 1.0)
    rim.data.spot_size = math.radians(65)
    rim.rotation_euler = (math.radians(-42), math.radians(-22), math.radians(160))
    
    # World background setup
    world = bpy.data.worlds.new("LightingWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs['Color'].default_value = (0.015, 0.015, 0.022, 1.0)
        bg.inputs['Strength'].default_value = 0.35
        
    return cam, key, fill, rim, world

def run_pass(pass_idx):
    output_dir = "/home/kidlucrid/Projects/3drealms/renders/lighting_tests"
    os.makedirs(output_dir, exist_ok=True)
    
    cam, key, fill, rim, world = setup_scene()
    scene = bpy.context.scene
    eevee = scene.eevee
    
    if pass_idx == 1:
        print(">>> [PASS 1] Direct Lighting Only (0 Bounces)...", flush=True)
        eevee.use_raytracing = False
        eevee.use_fast_gi = False
        eevee.indirect_light_intensity = 0.0
        eevee.direct_light_intensity = 1.0
        eevee.gi_diffuse_bounces = 0
        p_file = os.path.join(output_dir, "pass1_direct_zero_bounce.png")
        
    elif pass_idx == 2:
        print(">>> [PASS 2] Screen-Space Raytracing (1 Bounce)...", flush=True)
        eevee.use_raytracing = True
        eevee.ray_tracing_method = 'SCREEN'
        eevee.indirect_light_intensity = 1.0
        eevee.gi_diffuse_bounces = 1
        eevee.use_fast_gi = False
        p_file = os.path.join(output_dir, "pass2_screen_raytracing_one_bounce.png")
        
    elif pass_idx == 3:
        print(">>> [PASS 3] Global Illumination Fast GI (3 Bounces)...", flush=True)
        eevee.use_raytracing = True
        eevee.use_fast_gi = True
        eevee.fast_gi_method = 'GLOBAL_ILLUMINATION'
        eevee.fast_gi_ray_count = 4
        eevee.gi_diffuse_bounces = 3
        eevee.indirect_light_intensity = 1.6
        p_file = os.path.join(output_dir, "pass3_multi_bounce_fast_gi.png")
        
    elif pass_idx == 4:
        print(">>> [PASS 4] Light Probe Volume (Area Flood Bounce Data)...", flush=True)
        eevee.use_raytracing = True
        eevee.ray_tracing_method = 'PROBE'
        eevee.gi_diffuse_bounces = 3
        eevee.indirect_light_intensity = 2.0
        bpy.ops.object.lightprobe_add(type='VOLUME', location=(0, 0, 1.15))
        probe = bpy.context.active_object
        probe.name = "Probe_Volume_AreaFlood"
        probe.scale = (2.2, 2.2, 2.4)
        p_file = os.path.join(output_dir, "pass4_irradiance_probe_volume_flood.png")
        
    elif pass_idx == 5:
        print(">>> [PASS 5] Atmospheric Fog & Volumetric God Rays...", flush=True)
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        world_output = nodes.get("World Output")
        vol_node = nodes.new(type="ShaderNodeVolumePrincipled")
        vol_node.inputs['Density'].default_value = 0.025
        vol_node.inputs['Anisotropy'].default_value = 0.70
        vol_node.inputs['Color'].default_value = (0.75, 0.85, 1.0, 1.0)
        links.new(vol_node.outputs['Volume'], world_output.inputs['Volume'])
        eevee.use_volumetric_shadows = True
        eevee.volumetric_tile_size = '4'
        eevee.volumetric_samples = 32
        p_file = os.path.join(output_dir, "pass5_volumetric_fog_godrays.png")
        
    scene.render.filepath = p_file
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    dt = time.time() - t0
    print(f">>> Rendered {p_file} in {dt:.2f} seconds.", flush=True)
    return dt

if __name__ == "__main__":
    target = int(sys.argv[-1]) if len(sys.argv) > 1 and sys.argv[-1].isdigit() else 0
    if target > 0:
        run_pass(target)
    else:
        for p in [1, 2, 3, 4, 5]:
            run_pass(p)
