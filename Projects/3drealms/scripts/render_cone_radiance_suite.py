"""
render_cone_radiance_suite.py
Tests the 'Cone Type' Radiance primitive (Cape of Radiance, Gaussian brassing aura,
point-of-source path origin bounce) on the Gothic Barbarian asset.
Renders two cinematic GIFs:
1. cone_radiance_turntable.gif (360° orbital turntable)
2. cone_radiance_auric_pulse.gif (Hero close-up demonstrating dynamic brassing pulse and color exchange)
"""

import bpy
import math
import os
import shutil

def stitch_gif_standalone():
    pass

def build_cone_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    glb_path = "/home/kidlucrid/Projects/3drealms/models/characters/male/highpoly/gothic_barbarian.glb"
    bpy.ops.import_scene.gltf(filepath=glb_path)
    
    # Root container for character & mantle
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    hero_root = bpy.context.active_object
    hero_root.name = "Hero_Root"
    
    for obj in list(bpy.context.scene.objects):
        if obj != hero_root and obj.type in ['MESH', 'ARMATURE']:
            obj.parent = hero_root
            
    # Pedestal (Fixed world ground)
    bpy.ops.mesh.primitive_cylinder_add(radius=1.8, depth=0.15, location=(0, 0, -0.075))
    ped = bpy.context.active_object
    ped.name = "Pedestal"
    mat_ped = bpy.data.materials.new("Mat_Ped")
    mat_ped.use_nodes = True
    bsdf = mat_ped.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.04, 0.04, 0.06, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.35
        bsdf.inputs['Metallic'].default_value = 0.3
    ped.data.materials.append(mat_ped)

    # World & Atmospheric Volumetrics
    world = bpy.data.worlds.new("ConeWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    wnodes = world.node_tree.nodes
    wlinks = world.node_tree.links
    bg = wnodes.get("Background")
    if bg:
        bg.inputs['Color'].default_value = (0.008, 0.010, 0.018, 1.0)
        bg.inputs['Strength'].default_value = 0.22
    
    w_out = wnodes.get("World Output")
    vol_node = wnodes.new(type="ShaderNodeVolumePrincipled")
    vol_node.inputs['Density'].default_value = 0.026
    vol_node.inputs['Anisotropy'].default_value = 0.72
    vol_node.inputs['Color'].default_value = (0.75, 0.85, 1.0, 1.0)
    wlinks.new(vol_node.outputs['Volume'], w_out.inputs['Volume'])

    # Scene Base Lighting (Key Sun + Cool Rim)
    bpy.ops.object.light_add(type='SUN', location=(3.5, -3.0, 4.5))
    sun = bpy.context.active_object
    sun.data.energy = 2.4
    sun.data.color = (0.75, 0.88, 1.0)
    sun.rotation_euler = (math.radians(48), math.radians(18), math.radians(-32))
    
    bpy.ops.object.light_add(type='SPOT', location=(-2.2, 1.8, 2.5))
    rim = bpy.context.active_object
    rim.data.energy = 260.0
    rim.data.color = (0.55, 0.80, 1.0)
    rim.data.spot_size = math.radians(55)
    rim.rotation_euler = (math.radians(-38), math.radians(-30), math.radians(140))

    # --- THE CONE TYPE RADIANCE MANTLE ---
    # Apex Spot at C7 nape pointing down the spine
    bpy.ops.object.light_add(type='SPOT', location=(0.0, 0.22, 1.72))
    cone_light = bpy.context.active_object
    cone_light.name = "Light_ConeType_Apex"
    cone_light.parent = hero_root
    cone_light.data.energy = 720.0
    cone_light.data.color = (1.0, 0.62, 0.16) # Molten amber / brassing core
    cone_light.data.spot_size = math.radians(72)
    cone_light.data.spot_blend = 0.55 # Smooth Gaussian boundary
    cone_light.rotation_euler = (math.radians(-32), 0, math.radians(180))

    # Floor crescent bounce light
    bpy.ops.object.light_add(type='POINT', location=(0.0, 0.55, 0.25))
    bounce_pt = bpy.context.active_object
    bounce_pt.name = "Light_ConeType_FloorBounce"
    bounce_pt.parent = hero_root
    bounce_pt.data.energy = 140.0
    bounce_pt.data.color = (1.0, 0.52, 0.12)

    # Procedural Volumetric Mantle Mesh (Cape of Radiance geometry)
    mesh = bpy.data.meshes.new("Cone_Radiance_Mantle")
    mantle_obj = bpy.data.objects.new("Cone_Radiance_Mantle", mesh)
    mantle_obj.parent = hero_root
    bpy.context.scene.collection.objects.link(mantle_obj)
    
    verts = []
    faces = []
    rows = 18
    cols = 14
    for r in range(rows):
        v = r / float(rows - 1)
        z = 1.65 * (1.0 - v) + 0.08 * v
        half_w = (0.22 * (1.0 - v) + 0.72 * v)
        y_center = 0.15 + 0.40 * (v ** 1.25)
        for c in range(cols):
            u = c / float(cols - 1)
            x = -half_w + 2.0 * half_w * u
            arc_bow = 0.08 * (1.0 - (2.0 * u - 1.0) ** 2)
            y = y_center + arc_bow
            verts.append((x, y, z))
            
    for r in range(rows - 1):
        for c in range(cols - 1):
            i0 = r * cols + c
            i1 = r * cols + (c + 1)
            i2 = (r + 1) * cols + (c + 1)
            i3 = (r + 1) * cols + c
            faces.append((i0, i1, i2, i3))
            
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    
    # Auric Gaussian glow shader
    mat_mantle = bpy.data.materials.new("Mat_Cone_Radiance")
    mat_mantle.use_nodes = True
    mnodes = mat_mantle.node_tree.nodes
    mlinks = mat_mantle.node_tree.links
    mnodes.clear()
    
    output = mnodes.new(type="ShaderNodeOutputMaterial")
    mix_shader = mnodes.new(type="ShaderNodeMixShader")
    transparent = mnodes.new(type="ShaderNodeBsdfTransparent")
    emission = mnodes.new(type="ShaderNodeEmission")
    emission.name = "Mantle_Emission"
    emission.inputs['Color'].default_value = (1.0, 0.68, 0.22, 1.0)
    emission.inputs['Strength'].default_value = 5.5
    
    fresnel = mnodes.new(type="ShaderNodeLayerWeight")
    fresnel.inputs['Blend'].default_value = 0.35
    
    ramp = mnodes.new(type="ShaderNodeValToRGB")
    ramp.name = "Mantle_Ramp"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.2, 0.6, 1.0, 1.0) # Steel rim
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (1.0, 0.65, 0.15, 1.0) # Brassing amber
    
    mlinks.new(fresnel.outputs['Facing'], ramp.inputs['Fac'])
    mlinks.new(ramp.outputs['Color'], emission.inputs['Color'])
    mlinks.new(fresnel.outputs['Facing'], mix_shader.inputs['Fac'])
    mlinks.new(transparent.outputs['BSDF'], mix_shader.inputs[1])
    mlinks.new(emission.outputs['Emission'], mix_shader.inputs[2])
    mlinks.new(mix_shader.outputs['Shader'], output.inputs['Surface'])
    
    mantle_obj.data.materials.append(mat_mantle)
    
    # Engine Settings
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_samples = 4
    scene.eevee.use_volumetric_shadows = True
    scene.eevee.volumetric_tile_size = '4'
    scene.eevee.volumetric_samples = 32
    scene.render.resolution_x = 540
    scene.render.resolution_y = 540
    
    return hero_root, cone_light, bounce_pt, emission, ramp, mat_mantle

def render_cone_turntable():
    print(">>> [SUITE 1/2] Rendering Cone Type Radiance Turntable (24 frames)...", flush=True)
    hero_root, cone_light, bounce_pt, emission, ramp, mat_mantle = build_cone_scene()
    scene = bpy.context.scene
    
    # Setup Camera
    bpy.ops.object.camera_add(location=(0, -2.85, 1.35))
    cam = bpy.context.active_object
    cam.data.lens = 48
    scene.camera = cam
    
    # Pivot for turntable
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 1.15))
    pivot = bpy.context.active_object
    cam.parent = pivot
    cam.rotation_euler = (math.radians(82), 0, 0)
    
    out_dir = "/tmp/cone_turntable_frames"
    os.makedirs(out_dir, exist_ok=True)
    num_frames = 24
    frame_paths = []
    
    for f in range(num_frames):
        angle = (f / float(num_frames)) * (2.0 * math.pi)
        pivot.rotation_euler = (0, 0, angle)
        frame_file = os.path.join(out_dir, f"frame_{f:03d}.png")
        scene.render.filepath = frame_file
        bpy.ops.render.render(write_still=True)
        frame_paths.append(frame_file)
        print(f"  Turntable frame {f+1}/{num_frames} done", flush=True)
        
    print(f">>> [SUCCESS] Rendered all {num_frames} turntable frames to {out_dir}")

def render_cone_pulse():
    print(">>> [SUITE 2/2] Rendering Auric Pulse & Brassing Color Exchange (18 frames)...", flush=True)
    hero_root, cone_light, bounce_pt, emission, ramp, mat_mantle = build_cone_scene()
    scene = bpy.context.scene
    
    # Rear-three-quarter hero camera angle
    bpy.ops.object.camera_add(location=(1.75, 2.15, 1.50))
    cam = bpy.context.active_object
    cam.data.lens = 52
    cam.rotation_euler = (math.radians(-66), math.radians(0), math.radians(142))
    scene.camera = cam
    
    out_dir = "/tmp/cone_pulse_frames"
    os.makedirs(out_dir, exist_ok=True)
    num_frames = 18
    frame_paths = []
    
    for f in range(num_frames):
        phase = (f / float(num_frames)) * (2.0 * math.pi)
        sine_val = (math.sin(phase) + 1.0) * 0.5 # 0.0 to 1.0
        
        # Modulate radiance mantle emission & spot intensity
        emission.inputs['Strength'].default_value = 3.5 + 4.5 * sine_val
        cone_light.data.energy = 550.0 + 350.0 * sine_val
        bounce_pt.data.energy = 100.0 + 80.0 * sine_val
        
        # Modulate Gaussian brassing aura color ramp (expanding & contracting amber core)
        ramp.color_ramp.elements[1].position = 0.50 + 0.25 * sine_val
        
        frame_file = os.path.join(out_dir, f"frame_{f:03d}.png")
        scene.render.filepath = frame_file
        bpy.ops.render.render(write_still=True)
        frame_paths.append(frame_file)
        print(f"  Pulse frame {f+1}/{num_frames} done", flush=True)
        
    print(f">>> [SUCCESS] Rendered all {num_frames} pulse frames to {out_dir}")

if __name__ == "__main__":
    render_cone_turntable()
    render_cone_pulse()
