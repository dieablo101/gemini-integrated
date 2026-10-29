import bpy
import bmesh
import math
import json
import os

def analyze_and_decimate():
    glb_path = "/home/kidlucrid/Projects/3drealms/models/characters/male/highpoly/gothic_barbarian.glb"
    
    # Reset blender scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    # Import original GLB
    bpy.ops.import_scene.gltf(filepath=glb_path)
    
    # Find mesh objects
    mesh_objs = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    
    baseline_stats = {}
    total_orig_verts = 0
    total_orig_edges = 0
    total_orig_faces = 0
    total_orig_tris = 0
    
    for obj in mesh_objs:
        me = obj.data
        me.calc_loop_triangles()
        tri_count = len(me.loop_triangles)
        v_count = len(me.vertices)
        e_count = len(me.edges)
        f_count = len(me.polygons)
        
        total_orig_verts += v_count
        total_orig_edges += e_count
        total_orig_faces += f_count
        total_orig_tris += tri_count
        
        baseline_stats[obj.name] = {
            "vertices": v_count,
            "edges": e_count,
            "faces": f_count,
            "triangles": tri_count,
            "v_to_f_ratio": round(v_count / max(f_count, 1), 4)
        }
        
    print("=== BASELINE HIGH-POLY TOPOLOGY ===")
    print(json.dumps(baseline_stats, indent=2))
    print(f"Total Base Vertices: {total_orig_verts}, Faces: {total_orig_faces}, Tris: {total_orig_tris}")
    
    # Planar Decimation Tests across angles: 1.0 deg, 2.5 deg, 5.0 deg, 10.0 deg
    angles = [1.0, 2.5, 5.0, 10.0]
    planar_results = {}
    
    for angle in angles:
        # Clone or re-evaluate with Decimate Modifier
        planar_results[f"{angle}_deg"] = {}
        combined_verts = 0
        combined_faces = 0
        combined_tris = 0
        
        for obj in mesh_objs:
            # Add decimate modifier
            mod = obj.modifiers.new(name=f"Decimate_Planar_{angle}", type='DECIMATE')
            mod.decimate_type = 'DISSOLVE'
            mod.angle_limit = math.radians(angle)
            mod.delimit = {'NORMAL', 'MATERIAL'} # Protect UV & Material boundaries
            
            # Evaluate dependency graph to get resulting mesh
            depsgraph = bpy.context.evaluated_depsgraph_get()
            eval_obj = obj.evaluated_get(depsgraph)
            eval_mesh = eval_obj.data
            eval_mesh.calc_loop_triangles()
            
            ev_v = len(eval_mesh.vertices)
            ev_e = len(eval_mesh.edges)
            ev_f = len(eval_mesh.polygons)
            ev_t = len(eval_mesh.loop_triangles)
            
            combined_verts += ev_v
            combined_faces += ev_f
            combined_tris += ev_t
            
            planar_results[f"{angle}_deg"][obj.name] = {
                "vertices": ev_v,
                "faces": ev_f,
                "triangles": ev_t,
                "vert_reduction_pct": round((1.0 - (ev_v / max(baseline_stats[obj.name]["vertices"], 1))) * 100, 2),
                "face_reduction_pct": round((1.0 - (ev_f / max(baseline_stats[obj.name]["faces"], 1))) * 100, 2),
                "v_to_f_ratio": round(ev_v / max(ev_f, 1), 4)
            }
            
            # Remove modifier
            obj.modifiers.remove(mod)
            
        planar_results[f"{angle}_deg"]["TOTAL"] = {
            "vertices": combined_verts,
            "faces": combined_faces,
            "triangles": combined_tris,
            "vert_reduction_pct": round((1.0 - (combined_verts / total_orig_verts)) * 100, 2),
            "face_reduction_pct": round((1.0 - (combined_faces / total_orig_faces)) * 100, 2),
            "v_to_f_ratio": round(combined_verts / max(combined_faces, 1), 4)
        }
        
    print("\n=== PLANAR DECIMATION TEST RESULTS ===")
    print(json.dumps(planar_results, indent=2))
    
    # Save a permanent 5.0 deg Planar Decimated model
    for obj in mesh_objs:
        mod = obj.modifiers.new(name="Decimate_Planar_5deg", type='DECIMATE')
        mod.decimate_type = 'DISSOLVE'
        mod.angle_limit = math.radians(5.0)
        mod.delimit = {'NORMAL', 'MATERIAL'}
        
    decimated_export_path = "/home/kidlucrid/Projects/3drealms/models/characters/male/highpoly/gothic_barbarian_decimated_planar.glb"
    bpy.ops.export_scene.gltf(
        filepath=decimated_export_path,
        export_format='GLB',
        export_apply=True
    )
    print(f"\n>>> Decimated model saved to {decimated_export_path}")
    
    # Output report JSON for docket
    docket_data = {
        "baseline": baseline_stats,
        "planar_decimation": planar_results
    }
    with open("/home/kidlucrid/Projects/3drealms/renders/decimation_audit.json", "w") as f:
        json.dump(docket_data, f, indent=2)

analyze_and_decimate()
