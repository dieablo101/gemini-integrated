#!/usr/bin/env python3
"""
Nomad Link PC Study Bridge (Multi-Engine & Multi-Format Intake Daemon)
---------------------------------------------------------------------
Connects to Nomad Sculpt over Wi-Fi (Nomad Link TCP protocol), streams active sculpts,
and routes geometry through:
1. Multi-Format Omni-Exporter:
   - .fbx (Autodesk FBX via Blender)
   - .glb (glTF 2.0 Binary via Blender)
   - .gltf (glTF 2.0 JSON + bin via Blender)
   - .obj (Wavefront OBJ with extended vertex color channels)
   - .stl (Watertight binary stereolithography for 3D printing & solid volume)
   - .ply (Stanford Polygon format with per-vertex RGBA)
   - .json (Nomad Link full layer, roughness, metalness, and transform metadata)
2. Blender Headless Studio Rig:
   - Automated 6-angle Orthographic Renders (Flat Albedo & Dense Studio Lighting)
   - Blender Volumetric & Geometric analysis
3. Godot Headless Engine:
   - GLB Ingestion & Physics Convex Collision Hull reduction
   - Kinetic strike envelopes and reach estimation
4. 3DRealms Perception Study Engine:
   - Medial axis mass decomposition
   - Discrete surface curvature & ridge analysis
   - Photometric shadow inversion & bilateral symmetry index
"""

import os
import sys
import time
import json
import struct
import subprocess
import argparse
import numpy as np

# Path configurations
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "nomad-link", "examples")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "engines", "study_engine")))
try:
    import transport
except ImportError:
    import sys
    sys.path.insert(0, "/opt/gemini/Projects/nomad-link/examples")
    import transport

from sculpt_study_engine import execute_study

DEFAULT_HOST = "192.168.1.38"
DEFAULT_PORT = 48312
DEFAULT_TOKEN = "80973ade-840f-459d-a21c-c5803939249e41e487e0-e5fa-4126-885c-7239b6881241"
BLENDER_BIN = "/home/kidlucrid/.local/bin/blender"
GODOT_BIN = "/home/kidlucrid/.local/bin/godot"

def decode_mesh(header, binary):
    vcount = int(header["vertex_count"])
    fcount = int(header["face_count"])
    pos_offset = int(header["position_offset"])
    face_offset = int(header["face_offset"])
    
    positions = np.frombuffer(binary, "<f4", vcount * 3, pos_offset).reshape(-1, 3).copy()
    faces = np.frombuffer(binary, "<i4", fcount * 4, face_offset).reshape(-1, 4).copy()
    
    # World matrix transform
    matrix_raw = header.get("world_matrix")
    if matrix_raw and len(matrix_raw) == 16:
        matrix = np.array(matrix_raw, dtype=np.float32).reshape(4, 4, order="F")
        positions = positions @ matrix[:3, :3].T + matrix[:3, 3]
        
    colors = None
    if "color_offset" in header:
        c_off = int(header["color_offset"])
        packed = np.frombuffer(binary, dtype=np.uint8, count=vcount * 4, offset=c_off).reshape(-1, 4).astype(np.float32)
        rgb = packed[:, :3] * (packed[:, 3:4] / 65025.0)
        colors = rgb
        
    return {
        "name": header.get("name", "NomadSculpt"),
        "positions": positions,
        "faces": faces,
        "colors": colors,
        "vertex_count": vcount,
        "face_count": fcount,
        "raw_header": header
    }

def export_obj(filepath, positions, faces, colors=None):
    """Exports clean Wavefront OBJ with per-vertex color encoding."""
    with open(filepath, "w") as f:
        f.write("# 3DRealms Nomad Omni-Exporter - Wavefront OBJ\n")
        f.write(f"# Vertices: {len(positions)}, Faces: {len(faces)}\n")
        
        if colors is not None and len(colors) == len(positions):
            for (x, y, z), (r, g, b) in zip(positions, colors):
                f.write(f"v {x:.6f} {y:.6f} {z:.6f} {r:.4f} {g:.4f} {b:.4f}\n")
        else:
            for x, y, z in positions:
                f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
                
        for face in faces:
            if len(face) == 4 and face[3] != -1:
                f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1} {face[3]+1}\n")
            else:
                f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")

def export_stl_binary(filepath, positions, faces):
    """Exports watertight binary STL for 3D printing and volumetric testing."""
    tris = []
    for f in faces:
        if len(f) == 4 and f[3] != -1:
            tris.append([f[0], f[1], f[2]])
            tris.append([f[0], f[2], f[3]])
        else:
            tris.append([f[0], f[1], f[2]])
    tris = np.array(tris, dtype=np.int32)
    v_tris = positions[tris]
    
    # Compute normals
    v0, v1, v2 = v_tris[:, 0], v_tris[:, 1], v_tris[:, 2]
    normals = np.cross(v1 - v0, v2 - v0)
    norm_lens = np.linalg.norm(normals, axis=1, keepdims=True)
    norm_lens[norm_lens == 0] = 1.0
    normals = normals / norm_lens
    
    num_tris = len(tris)
    header = b"Exported by 3DRealms Nomad Omni-Exporter".ljust(80, b"\x00")
    
    dtype = np.dtype([
        ("normal", "<f4", (3,)),
        ("v0", "<f4", (3,)),
        ("v1", "<f4", (3,)),
        ("v2", "<f4", (3,)),
        ("attr", "<u2")
    ])
    
    data = np.empty(num_tris, dtype=dtype)
    data["normal"] = normals
    data["v0"] = v0
    data["v1"] = v1
    data["v2"] = v2
    data["attr"] = 0
    
    with open(filepath, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", num_tris))
        data.tofile(f)

def export_ply_binary(filepath, positions, faces, colors=None):
    """Exports binary PLY with per-vertex RGBA."""
    num_verts = len(positions)
    num_faces = len(faces)
    
    header = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {num_verts}",
        "property float x",
        "property float y",
        "property float z"
    ]
    has_colors = colors is not None and len(colors) == num_verts
    if has_colors:
        header.extend([
            "property uchar red",
            "property uchar green",
            "property uchar blue",
            "property uchar alpha"
        ])
    header.extend([
        f"element face {num_faces}",
        "property list uchar uint vertex_indices",
        "end_header\n"
    ])
    header_bytes = "\n".join(header).encode("ascii")
    
    if has_colors:
        c_bytes = np.clip(colors * 255.0, 0, 255).astype(np.uint8)
        if c_bytes.shape[1] == 3:
            alpha = np.full((num_verts, 1), 255, dtype=np.uint8)
            c_bytes = np.hstack([c_bytes, alpha])
        v_dtype = np.dtype([
            ("pos", "<f4", (3,)),
            ("color", "u1", (4,))
        ])
        v_data = np.empty(num_verts, dtype=v_dtype)
        v_data["pos"] = positions.astype(np.float32)
        v_data["color"] = c_bytes
    else:
        v_dtype = np.dtype([("pos", "<f4", (3,))])
        v_data = np.empty(num_verts, dtype=v_dtype)
        v_data["pos"] = positions.astype(np.float32)
        
    with open(filepath, "wb") as f:
        f.write(header_bytes)
        v_data.tofile(f)
        for face in faces:
            if len(face) == 4 and face[3] != -1:
                f.write(b"\x04" + face.astype("<u4").tobytes())
            else:
                f.write(b"\x03" + face[:3].astype("<u4").tobytes())

def fetch_nomad_mesh(host, port, token, timeout=12.0):
    print(f"[NomadBridge] Connecting to Nomad Link at {host}:{port}...")
    conn = transport.Connection(
        client_name="Architect Node Studio",
        capabilities=["scene_transfer", "selection_transfer", "mesh_full", "mesh_attributes", "object_state", "camera", "camera_object", "light", "material"]
    )
    conn.connect(host, port, token, transport.VERSION, 1)
    
    start = time.time()
    mesh_data = None
    sent = False
    
    while time.time() - start < timeout:
        for header, binary in conn.poll():
            kind = header.get("type")
            if kind == "hello" and not sent:
                print(f"[NomadBridge] Connected! Nomad version {header.get('nomad_version')}. Requesting scene...")
                conn.send({"type": "request_scene"})
                sent = True
            elif kind == "mesh_full":
                print(f"[NomadBridge] Captured mesh: '{header.get('name')}' ({len(binary):,} bytes payload)")
                mesh_data = decode_mesh(header, binary)
                break
        if mesh_data:
            break
        time.sleep(0.05)
        
    conn.disconnect()
    return mesh_data

def run_blender_pipeline(input_json, out_dir):
    blender_script = os.path.abspath("Projects/3drealms/engines/study_engine/blender_study_rig.py")
    cmd = [
        BLENDER_BIN,
        "--background",
        "--python", blender_script,
        "--",
        input_json,
        out_dir
    ]
    print(f"[NomadBridge] Executing Blender Headless Study Rig (FBX, GLB, GLTF, 12 Renders)...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("[NomadBridge] Blender error:\n", proc.stderr)
        return False
    print("[NomadBridge] Blender processing complete.")
    return True

def run_godot_pipeline(glb_path, out_dir):
    godot_script = os.path.abspath("Projects/3drealms/engines/study_engine/godot_study_rig.gd")
    cmd = [
        GODOT_BIN,
        "--headless",
        "-s", godot_script,
        "--",
        "--glb", glb_path,
        "--out", out_dir
    ]
    print(f"[NomadBridge] Executing Godot Headless Study Rig (Kinetic Envelope)...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("[NomadBridge] Godot error:\n", proc.stderr)
        return False
    print("[NomadBridge] Godot processing complete.")
    return True

def ingest_sculpt(sculpt_name_override=None, from_json_path=None, host=DEFAULT_HOST, port=DEFAULT_PORT, token=DEFAULT_TOKEN):
    if from_json_path and os.path.exists(from_json_path):
        print(f"[NomadBridge] Ingesting from existing sculpt JSON payload: {from_json_path}")
        with open(from_json_path, "r") as f:
            jdata = json.load(f)
        sculpt_id = sculpt_name_override or jdata.get("sculpt_id", "alien")
        mesh_data = {
            "name": sculpt_id,
            "positions": np.array(jdata["vertices"], dtype=np.float32),
            "faces": np.array(jdata["faces"], dtype=np.int32),
            "colors": np.array(jdata["colors"], dtype=np.float32) if jdata.get("colors") else None,
            "vertex_count": len(jdata["vertices"]),
            "face_count": len(jdata["faces"]),
            "raw_header": {"name": sculpt_id, "vertex_count": len(jdata["vertices"]), "face_count": len(jdata["faces"])}
        }
    else:
        # Step 1: Capture live from Nomad
        mesh_data = fetch_nomad_mesh(host, port, token)
        if not mesh_data:
            print("[NomadBridge] ERROR: Could not capture sculpt from Nomad. Check that Link is turned ON.")
            return None
        sculpt_id = sculpt_name_override or mesh_data["name"].replace(" ", "_").lower()
        
    target_dir = os.path.abspath(f"Projects/3drealms/models/nomad_intake/{sculpt_id}")
    os.makedirs(target_dir, exist_ok=True)
    
    print(f"\n[NomadBridge] Beginning Multi-Format Omni-Export for '{sculpt_id}'...")
    
    # Step 2: Export OBJ, STL, PLY directly
    obj_path = os.path.join(target_dir, f"{sculpt_id}.obj")
    stl_path = os.path.join(target_dir, f"{sculpt_id}.stl")
    ply_path = os.path.join(target_dir, f"{sculpt_id}.ply")
    meta_path = os.path.join(target_dir, f"{sculpt_id}_nomad_meta.json")
    
    export_obj(obj_path, mesh_data["positions"], mesh_data["faces"], mesh_data["colors"])
    print(f" • Wavefront OBJ:   {obj_path} ({os.path.getsize(obj_path):,} bytes)")
    
    export_stl_binary(stl_path, mesh_data["positions"], mesh_data["faces"])
    print(f" • 3D Print STL:   {stl_path} ({os.path.getsize(stl_path):,} bytes)")
    
    export_ply_binary(ply_path, mesh_data["positions"], mesh_data["faces"], mesh_data["colors"])
    print(f" • Stanford PLY:   {ply_path} ({os.path.getsize(ply_path):,} bytes)")
    
    # Save raw Nomad packet metadata
    with open(meta_path, "w") as f:
        json.dump(mesh_data["raw_header"], f, indent=2)
    print(f" • Nomad Metadata: {meta_path}")
    
    # Step 3: Write payload for Blender pipeline
    temp_json = os.path.join(target_dir, f"{sculpt_id}_input.json")
    payload = {
        "sculpt_id": sculpt_id,
        "vertices": mesh_data["positions"].tolist(),
        "faces": mesh_data["faces"].tolist(),
        "colors": mesh_data["colors"].tolist() if mesh_data["colors"] is not None else None
    }
    with open(temp_json, "w") as f:
        json.dump(payload, f)
        
    # Step 4: Blender Headless Processing (FBX, GLB, GLTF, Multi-angle Renders)
    success = run_blender_pipeline(temp_json, target_dir)
    if not success:
        print("[NomadBridge] Blender execution failed.")
        return None
        
    # Step 5: Godot Headless Processing (GLB Ingestion, Collision Hulls, Kinetic Envelope)
    glb_path = os.path.join(target_dir, f"{sculpt_id}.glb")
    gltf_path = os.path.join(target_dir, f"{sculpt_id}.gltf")
    fbx_path = os.path.join(target_dir, f"{sculpt_id}.fbx")
    run_godot_pipeline(glb_path, target_dir)
    
    # Step 6: Perception Study Engine Execution
    tris = []
    for f in mesh_data["faces"]:
        if len(f) == 4 and f[3] != -1:
            tris.append([f[0], f[1], f[2]])
            tris.append([f[0], f[2], f[3]])
        else:
            tris.append([f[0], f[1], f[2]])
    tris = np.array(tris, dtype=np.int32)
    
    renders_dir = os.path.join(target_dir, "renders")
    photo_pairs = {
        "front": (
            os.path.join(renders_dir, f"{sculpt_id}_front_flat.png"),
            os.path.join(renders_dir, f"{sculpt_id}_front_dense.png")
        ),
        "right": (
            os.path.join(renders_dir, f"{sculpt_id}_right_flat.png"),
            os.path.join(renders_dir, f"{sculpt_id}_right_dense.png")
        ),
        "back": (
            os.path.join(renders_dir, f"{sculpt_id}_back_flat.png"),
            os.path.join(renders_dir, f"{sculpt_id}_back_dense.png")
        ),
        "left": (
            os.path.join(renders_dir, f"{sculpt_id}_left_flat.png"),
            os.path.join(renders_dir, f"{sculpt_id}_left_dense.png")
        ),
        "top": (
            os.path.join(renders_dir, f"{sculpt_id}_top_flat.png"),
            os.path.join(renders_dir, f"{sculpt_id}_top_dense.png")
        ),
        "hero": (
            os.path.join(renders_dir, f"{sculpt_id}_hero_flat.png"),
            os.path.join(renders_dir, f"{sculpt_id}_hero_dense.png")
        )
    }
    
    print("[NomadBridge] Launching Analytical Study Engine...")
    study_manifest = execute_study(
        sculpt_id=sculpt_id,
        vertices=mesh_data["positions"],
        faces=tris,
        vertex_colors=mesh_data["colors"],
        photo_pairs=photo_pairs,
        output_dir="Projects/3drealms/models/nomad_intake/studies"
    )
    
    # Step 7: Load Blender & Godot JSON to create Master Comprehensive Manifest
    blender_json_path = os.path.join(target_dir, "blender_study.json")
    godot_json_path = os.path.join(target_dir, "godot_study.json")
    
    blender_data = {}
    if os.path.exists(blender_json_path):
        with open(blender_json_path, "r") as f:
            blender_data = json.load(f)
            
    godot_data = {}
    if os.path.exists(godot_json_path):
        with open(godot_json_path, "r") as f:
            godot_data = json.load(f)
            
    master_report = {
        "sculpt_id": sculpt_id,
        "timestamp": time.time(),
        "source": f"Nomad Link ({host}:{port})",
        "all_formats": {
            "fbx": fbx_path,
            "glb": glb_path,
            "gltf": gltf_path,
            "obj": obj_path,
            "stl": stl_path,
            "ply": ply_path,
            "nomad_meta": meta_path
        },
        "renders_dir": renders_dir,
        "blender_study": blender_data,
        "godot_study": godot_data,
        "perception_study": study_manifest
    }
    
    master_report_path = os.path.join(target_dir, "master_study_report.json")
    with open(master_report_path, "w") as f:
        json.dump(master_report, f, indent=2)
        
    print(f"\n========================================================")
    print(f"      ALL FORMATS & STUDY COMPLETE: {sculpt_id.upper()}")
    print(f"========================================================")
    print(f"• FBX:              {fbx_path}")
    print(f"• GLB (Binary):     {glb_path}")
    print(f"• glTF (Separate):  {gltf_path}")
    print(f"• OBJ (Wavefront):  {obj_path}")
    print(f"• STL (3D Print):   {stl_path}")
    print(f"• PLY (Stanford):   {ply_path}")
    print(f"• Nomad Meta:       {meta_path}")
    print(f"• Renders:          12 Calibrated Orthographic PNGs in renders/")
    print(f"• Vertices:         {mesh_data['vertex_count']:,}")
    print(f"• Faces:            {mesh_data['face_count']:,}")
    vol = study_manifest.get('mold', {}).get('total_volume_approx', 0)
    print(f"• Approx Volume:    {vol:.4f} m³")
    print(f"• Kinetic Reach:    {godot_data.get('kinetic_envelope', {}).get('estimated_strike_reach', 0):.2f}m")
    print(f"• Master Report:    {master_report_path}")
    print(f"========================================================\n")
    
    return master_report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nomad Link Multi-Format & Multi-Engine Ingest Daemon")
    parser.add_argument("--name", type=str, default=None, help="Override sculpt name (e.g. alien)")
    parser.add_argument("--from-json", type=str, default=None, help="Process from existing sculpt input JSON")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Nomad host IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Nomad port")
    args = parser.parse_args()
    
    ingest_sculpt(sculpt_name_override=args.name, from_json_path=args.from_json, host=args.host, port=args.port)
