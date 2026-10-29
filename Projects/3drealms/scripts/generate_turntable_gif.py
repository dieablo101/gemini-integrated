"""
generate_turntable_gif.py
Renders a 24-frame 360-degree rotation of the Gothic Barbarian and Greatsword,
then packages it into an animated GIF and MP4 for easy desktop inspection.
"""

import bpy
import math
import os

def render_turntable():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    glb_path = "/home/kidlucrid/Projects/3drealms/models/characters/male/highpoly/gothic_barbarian.glb"
    bpy.ops.import_scene.gltf(filepath=glb_path)
    
    # Pedestal
    bpy.ops.mesh.primitive_cylinder_add(radius=1.8, depth=0.15, location=(0, 0, -0.075))
    ped = bpy.context.active_object
    mat_ped = bpy.data.materials.new("Mat_Ped")
    mat_ped.use_nodes = True
    bsdf = mat_ped.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.05, 0.05, 0.07, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.4
    ped.data.materials.append(mat_ped)
    
    # Lighting
    bpy.ops.object.light_add(type='SUN', location=(3, -3, 4.5))
    sun = bpy.context.active_object
    sun.data.energy = 3.5
    sun.data.color = (0.8, 0.9, 1.0)
    
    bpy.ops.object.light_add(type='POINT', location=(-2.0, -1.6, 1.35))
    fill = bpy.context.active_object
    fill.data.energy = 200.0
    fill.data.color = (1.0, 0.6, 0.2)
    
    bpy.ops.object.light_add(type='SPOT', location=(-1.4, 2.8, 2.4))
    rim = bpy.context.active_object
    rim.data.energy = 450.0
    rim.data.color = (0.6, 0.8, 1.0)
    rim.data.spot_size = math.radians(65)
    rim.rotation_euler = (math.radians(-42), math.radians(-22), math.radians(160))
    
    # Camera
    bpy.ops.object.camera_add(location=(0, -2.8, 1.35))
    cam = bpy.context.active_object
    cam.data.lens = 50
    bpy.context.scene.camera = cam
    
    # Setup Turntable Empty
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 1.15))
    pivot = bpy.context.active_object
    pivot.name = "Turntable_Pivot"
    cam.parent = pivot
    cam.rotation_euler = (math.radians(82), 0, 0)
    
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_samples = 4 # Blazing fast render per frame
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    
    frames_dir = "/tmp/turntable_frames"
    os.makedirs(frames_dir, exist_ok=True)
    
    num_frames = 24
    frame_files = []
    
    for f in range(num_frames):
        angle = (f / float(num_frames)) * (2.0 * math.pi)
        pivot.rotation_euler = (0, 0, angle)
        frame_path = os.path.join(frames_dir, f"frame_{f:03d}.png")
        scene.render.filepath = frame_path
        bpy.ops.render.render(write_still=True)
        frame_files.append(frame_path)
    print(f">>> Rendered {num_frames} frames to {frames_dir}")

if __name__ == "__main__":
    render_turntable()
