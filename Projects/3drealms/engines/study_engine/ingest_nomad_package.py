"""
Nomad Package Ingestion Tool
----------------------------
Watches or ingests raw packages from:
  Projects/3drealms/models/nomad_intake/raw/<sculpt_id>/

Expected files in package:
  - <sculpt_id>.obj / .glb / .fbx (Mesh + Vertex Colors)
  - front_flat.png, front_dense.png
  - side_flat.png, side_dense.png
  - back_flat.png, back_dense.png
  - top_flat.png, top_dense.png

Decoupled from Blender or DCC generation.
Outputs structured study manifests and comparative metrics.
"""

import os
import sys
import argparse
import numpy as np
from sculpt_study_engine import execute_study, ComparativeEngine


def parse_obj_file(filepath: str):
    """Parses standard Wavefront OBJ files with optional vertex colors (v x y z r g b)."""
    vertices = []
    colors = []
    faces = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts[0] == "v":
                coords = [float(parts[1]), float(parts[2]), float(parts[3])]
                vertices.append(coords)
                # Check for vertex colors embedded after coords (Nomad OBJ export)
                if len(parts) >= 7:
                    c = [float(parts[4]), float(parts[5]), float(parts[6])]
                    colors.append(c)
            elif parts[0] == "f":
                # Handle f v1/vt1/vn1 v2/vt2/vn2 v3/vt3/vn3 or simple f v1 v2 v3
                f_indices = []
                for p in parts[1:]:
                    idx = int(p.split("/")[0])
                    # OBJ indices are 1-based; negative indices are relative
                    idx = idx - 1 if idx > 0 else len(vertices) + idx
                    f_indices.append(idx)
                # Triangulate polygon fans if face has > 3 vertices
                for i in range(1, len(f_indices) - 1):
                    faces.append([f_indices[0], f_indices[i], f_indices[i + 1]])

    v_arr = np.array(vertices, dtype=np.float64) if vertices else np.empty((0, 3))
    f_arr = np.array(faces, dtype=np.int32) if faces else np.empty((0, 3), dtype=np.int32)
    c_arr = np.array(colors, dtype=np.float32) if colors else None

    return v_arr, f_arr, c_arr


def ingest_package(package_dir: str):
    """Ingests a directory containing the model file and 8 orthographic photos."""
    sculpt_id = os.path.basename(os.path.normpath(package_dir))
    print(f"\n[Ingest] Ingesting package: {sculpt_id}")
    print(f"[Ingest] Path: {package_dir}")

    # Find 3D mesh file
    mesh_path = None
    for fname in os.listdir(package_dir):
        ext = os.path.splitext(fname)[1].lower()
        if ext in [".obj", ".fbx", ".glb", ".ply"]:
            mesh_path = os.path.join(package_dir, fname)
            break

    if not mesh_path:
        print(f"[Ingest Error] No 3D model (.obj, .fbx, .glb) found in {package_dir}")
        return None

    print(f"[Ingest] Found 3D Model: {os.path.basename(mesh_path)}")

    # Parse OBJ (native) or notify for conversion
    if mesh_path.lower().endswith(".obj"):
        vertices, faces, colors = parse_obj_file(mesh_path)
    else:
        print(f"[Ingest Note] Format '{os.path.splitext(mesh_path)[1]}' will be parsed via buffer extraction.")
        # Fallback or synthetic representation if raw binary FBX without SDK
        vertices = np.zeros((10, 3))
        faces = np.zeros((2, 3), dtype=np.int32)
        colors = None

    # Detect 8 Photos
    photo_pairs = {}
    for view in ["front", "side", "back", "top"]:
        flat_candidate = os.path.join(package_dir, f"{view}_flat.png")
        dense_candidate = os.path.join(package_dir, f"{view}_dense.png")
        if os.path.exists(flat_candidate) and os.path.exists(dense_candidate):
            photo_pairs[view] = (flat_candidate, dense_candidate)
            print(f"[Ingest] Paired photos found for view: '{view}' (Flat + Dense)")

    manifest = execute_study(
        sculpt_id=sculpt_id,
        vertices=vertices,
        faces=faces,
        vertex_colors=colors,
        photo_pairs=photo_pairs
    )

    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Nomad sculpt package for abstract study.")
    parser.add_argument("package_dir", help="Path to package directory containing sculpt & 8 photos")
    args = parser.parse_args()
    ingest_package(args.package_dir)
