"""
Sculpt Study Engine (Abstract Perception & Decomposition Framework)
-------------------------------------------------------------------
A pure analytical framework for studying 3D sculpted models and calibrated
orthographic photo sets (4 flat + 4 dense).

Decoupled completely from Blender or any DCC generation tool.
Focused exclusively on extracting:
  1. Mold Data  (Mass, volume, medial axis spheres, inertia)
  2. Shape Data (Curvatures, crease/ridge graphs, planar vs organic zones)
  3. Paint Data (Vertex palette clusters, curvature-pigment coupling, photometric AO)
  4. Comparative Synthesis (Cross-sculpt proportional and stylistic invariants)
"""

import os
import sys
import json
import math
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

# Try importing image libraries if available
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ---------------------------------------------------------------------------
# Tier 1: Mold Extractor (Volumetric Scaffold & Mass Properties)
# ---------------------------------------------------------------------------
class MoldExtractor:
    """Extracts bounding mass, volume distribution, inertia, and medial core."""

    @staticmethod
    def analyze_mesh_mold(vertices: np.ndarray, faces: np.ndarray) -> Dict[str, Any]:
        """
        Computes volumetric and structural mass metrics from vertices (N, 3)
        and triangular faces (M, 3).
        """
        min_b = np.min(vertices, axis=0)
        max_b = np.max(vertices, axis=0)
        dimensions = max_b - min_b
        center = (min_b + max_b) * 0.5
        centroid = np.mean(vertices, axis=0)

        # Approximate signed volume via divergence theorem on tetrahedra
        v0 = vertices[faces[:, 0]]
        v1 = vertices[faces[:, 1]]
        v2 = vertices[faces[:, 2]]
        cross_prod = np.cross(v1, v2)
        signed_volumes = np.sum(v0 * cross_prod, axis=1) / 6.0
        total_volume = float(np.abs(np.sum(signed_volumes)))

        # Normalized coordinates relative to centroid
        centered = vertices - centroid
        
        # 3D Covariance / Inertia Tensor approximation
        cov = np.dot(centered.T, centered) / len(vertices)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        
        # Sort principal inertia axes descending
        sort_idx = np.argsort(eigenvalues)[::-1]
        sorted_eigenvalues = eigenvalues[sort_idx]
        sorted_eigenvectors = eigenvectors[:, sort_idx]

        # Cranial vs Facial partition along Y (vertical) or Z axis
        # Assuming Y is up, top 40% is cranium, bottom 60% is facial/mandible
        y_split = min_b[1] + dimensions[1] * 0.6
        cranial_mask = vertices[:, 1] >= y_split
        facial_mask = vertices[:, 1] < y_split

        cranial_pts = vertices[cranial_mask]
        facial_pts = vertices[facial_mask]

        cranial_vol_approx = float(len(cranial_pts) / max(len(vertices), 1) * total_volume)
        facial_vol_approx = float(len(facial_pts) / max(len(vertices), 1) * total_volume)
        cranial_to_facial_ratio = cranial_vol_approx / max(facial_vol_approx, 1e-6)

        # Medial Axis Spine: Sample 10 slices along vertical height
        slices = []
        num_slices = 10
        y_steps = np.linspace(min_b[1], max_b[1], num_slices + 2)[1:-1]
        for y_lvl in y_steps:
            dy = dimensions[1] / (num_slices * 2)
            band_mask = np.abs(vertices[:, 1] - y_lvl) <= dy
            band_pts = vertices[band_mask]
            if len(band_pts) >= 4:
                slice_center = np.mean(band_pts, axis=0)
                # Inscribed radius estimate: average distance to band points
                radii = np.linalg.norm(band_pts - slice_center, axis=1)
                medial_radius = float(np.mean(radii))
                slices.append({
                    "height_y": float(y_lvl),
                    "center": [float(c) for c in slice_center],
                    "mean_radius": medial_radius,
                    "point_count": int(len(band_pts))
                })

        return {
            "bounding_box": {
                "min": [float(x) for x in min_b],
                "max": [float(x) for x in max_b],
                "dimensions": [float(x) for x in dimensions],
                "aspect_ratio_xyz": [float(d / max(dimensions[1], 1e-6)) for d in dimensions]
            },
            "centroid": [float(c) for c in centroid],
            "center": [float(c) for c in center],
            "total_volume_approx": total_volume,
            "cranial_to_facial_ratio": float(cranial_to_facial_ratio),
            "inertia_eigenvalues": [float(ev) for ev in sorted_eigenvalues],
            "medial_spine_slices": slices
        }


# ---------------------------------------------------------------------------
# Tier 2: Shape Extractor (Differential Geometry & Feature Lines)
# ---------------------------------------------------------------------------
class ShapeExtractor:
    """Extracts curvature fields, crease paths, and planar vs organic zones."""

    @staticmethod
    def compute_vertex_curvatures(vertices: np.ndarray, faces: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Approximates mean curvature (H) and Gaussian curvature (K) per vertex.
        """
        num_v = len(vertices)
        v_normals = np.zeros((num_v, 3), dtype=np.float64)
        
        # Calculate face normals
        v0 = vertices[faces[:, 0]]
        v1 = vertices[faces[:, 1]]
        v2 = vertices[faces[:, 2]]
        fn = np.cross(v1 - v0, v2 - v0)
        fn_len = np.linalg.norm(fn, axis=1, keepdims=True)
        fn_len[fn_len == 0] = 1.0
        fn_normalized = fn / fn_len

        # Accumulate to vertices
        for i in range(3):
            np.add.at(v_normals, faces[:, i], fn_normalized)
        
        vn_len = np.linalg.norm(v_normals, axis=1, keepdims=True)
        vn_len[vn_len == 0] = 1.0
        v_normals = v_normals / vn_len

        # One-ring adjacency estimation for mean curvature
        # H ≈ 0.5 * ||Δv|| where Δv is the graph Laplacian
        # Fast sparse neighbor approximation
        edge_diffs = np.zeros((num_v, 3), dtype=np.float64)
        neighbor_counts = np.zeros(num_v, dtype=np.int32)
        
        for i in range(3):
            j = (i + 1) % 3
            e_from = faces[:, i]
            e_to = faces[:, j]
            diff = vertices[e_to] - vertices[e_from]
            np.add.at(edge_diffs, e_from, diff)
            np.add.at(neighbor_counts, e_from, 1)

        neighbor_counts[neighbor_counts == 0] = 1
        laplacian = edge_diffs / neighbor_counts[:, None]
        
        # Mean curvature sign: positive for convex peaks, negative for concave valleys
        # relative to normal
        mean_curv = np.sum(laplacian * v_normals, axis=1)

        # Estimate Gaussian curvature proxy through variance of neighbor normals
        norm_diffs = np.zeros(num_v, dtype=np.float64)
        for i in range(3):
            j = (i + 1) % 3
            e_from = faces[:, i]
            e_to = faces[:, j]
            ndiff = 1.0 - np.sum(v_normals[e_from] * v_normals[e_to], axis=1)
            np.add.at(norm_diffs, e_from, ndiff)
        gauss_curv_proxy = norm_diffs / neighbor_counts

        # Shape Index S = (2 / pi) * arctan( (k1 + k2) / (k1 - k2) )
        # Proxy approximation using normalized mean curvature
        shape_index = np.clip(np.arctan(mean_curv * 10.0) / (0.5 * math.pi), -1.0, 1.0)

        return {
            "mean_curvature": mean_curv,
            "gauss_curv_proxy": gauss_curv_proxy,
            "shape_index": shape_index,
            "vertex_normals": v_normals
        }

    @classmethod
    def extract_shape_metrics(cls, vertices: np.ndarray, faces: np.ndarray) -> Dict[str, Any]:
        curv_data = cls.compute_vertex_curvatures(vertices, faces)
        mean_c = curv_data["mean_curvature"]
        shape_idx = curv_data["shape_index"]

        # Classification of surface patches:
        # High convex: crests/horns (mean_c > 75th percentile)
        # Deep concave: sockets/creases (mean_c < 25th percentile)
        # Planar: low absolute curvature (|mean_c| < threshold)
        abs_c = np.abs(mean_c)
        planar_thresh = np.percentile(abs_c, 20)
        planar_mask = abs_c <= planar_thresh
        planar_percentage = float(np.mean(planar_mask) * 100.0)

        # Crease feature vertices (valleys: strongly negative curvature)
        crease_thresh = np.percentile(mean_c, 8)
        crease_mask = mean_c <= crease_thresh
        crease_points = vertices[crease_mask]

        # Ridge feature vertices (crests: strongly positive curvature)
        ridge_thresh = np.percentile(mean_c, 92)
        ridge_mask = mean_c >= ridge_thresh
        ridge_points = vertices[ridge_mask]

        return {
            "planar_surface_percentage": planar_percentage,
            "mean_curvature_stats": {
                "min": float(np.min(mean_c)),
                "max": float(np.max(mean_c)),
                "mean": float(np.mean(mean_c)),
                "std": float(np.std(mean_c))
            },
            "shape_distribution": {
                "dome_percentage": float(np.mean(shape_idx > 0.5) * 100.0),
                "cavity_percentage": float(np.mean(shape_idx < -0.5) * 100.0),
                "saddle_planar_percentage": float(np.mean(np.abs(shape_idx) <= 0.5) * 100.0)
            },
            "feature_counts": {
                "detected_crease_nodes": int(len(crease_points)),
                "detected_ridge_nodes": int(len(ridge_points))
            }
        }


# ---------------------------------------------------------------------------
# Tier 3: Paint Extractor (Vertex Colors & Inversion Optics)
# ---------------------------------------------------------------------------
class PaintExtractor:
    """Extracts vertex color clusters, curvature-pigment coupling, and photo AO."""

    @staticmethod
    def analyze_vertex_colors(colors: np.ndarray, mean_curvatures: np.ndarray) -> Dict[str, Any]:
        """
        colors: (N, 3) or (N, 4) in [0, 1] range.
        mean_curvatures: (N,) corresponding per-vertex curvature.
        """
        rgb = colors[:, :3]
        num_pts = len(rgb)

        # Average luminance Y = 0.299 R + 0.587 G + 0.114 B
        lum = 0.299 * rgb[:, 0] + 0.587 * rgb[:, 1] + 0.114 * rgb[:, 2]

        # Pearson correlation between luminance and curvature
        # Measures whether the artist paints highlights on ridges and shadows in cavities
        curv_norm = (mean_curvatures - np.mean(mean_curvatures)) / (np.std(mean_curvatures) + 1e-8)
        lum_norm = (lum - np.mean(lum)) / (np.std(lum) + 1e-8)
        coupling = float(np.mean(curv_norm * lum_norm))

        # Basic K-Means clustering (K=3: Primary, Secondary, Accent)
        # Using a deterministic centroid split
        sorted_indices = np.argsort(lum)
        idx_low = sorted_indices[: num_pts // 3]
        idx_mid = sorted_indices[num_pts // 3 : 2 * num_pts // 3]
        idx_high = sorted_indices[2 * num_pts // 3 :]

        c_low = np.mean(rgb[idx_low], axis=0) if len(idx_low) > 0 else np.zeros(3)
        c_mid = np.mean(rgb[idx_mid], axis=0) if len(idx_mid) > 0 else np.zeros(3)
        c_high = np.mean(rgb[idx_high], axis=0) if len(idx_high) > 0 else np.zeros(3)

        return {
            "pigment_coupling_to_curvature": coupling,
            "palette_triad": {
                "cavity_tone_rgb": [round(float(c), 3) for c in c_low],
                "base_flesh_rgb": [round(float(c), 3) for c in c_mid],
                "ridge_highlight_rgb": [round(float(c), 3) for c in c_high]
            },
            "mean_saturation": float(np.mean(np.max(rgb, axis=1) - np.min(rgb, axis=1)))
        }

    @staticmethod
    def analyze_photo_pair(flat_photo_path: str, dense_photo_path: str) -> Dict[str, Any]:
        """
        Computes 2D silhouette area from flat photo, and calculates
        photometric AO ratio from the flat vs dense lighting pair.
        """
        if not HAS_PIL:
            return {"status": "skipped", "reason": "Pillow not installed"}
        if not (os.path.exists(flat_photo_path) and os.path.exists(dense_photo_path)):
            return {"status": "missing_files"}

        try:
            im_flat = Image.open(flat_photo_path).convert("RGB")
            im_dense = Image.open(dense_photo_path).convert("RGB")

            arr_flat = np.array(im_flat, dtype=np.float32) / 255.0
            arr_dense = np.array(im_dense, dtype=np.float32) / 255.0

            # Flat photo silhouette detection (assuming non-pure-white or non-pure-black background)
            lum_flat = 0.299 * arr_flat[:, :, 0] + 0.587 * arr_flat[:, :, 1] + 0.114 * arr_flat[:, :, 2]
            # Background estimate from 4 corner pixels
            corner_lum = [lum_flat[0, 0], lum_flat[0, -1], lum_flat[-1, 0], lum_flat[-1, -1]]
            bg_val = float(np.mean(corner_lum))
            foreground_mask = np.abs(lum_flat - bg_val) > 0.08
            sil_fill_pct = float(np.mean(foreground_mask) * 100.0)

            # Photometric AO Ratio: Dense / Flat inside foreground
            lum_dense = 0.299 * arr_dense[:, :, 0] + 0.587 * arr_dense[:, :, 1] + 0.114 * arr_dense[:, :, 2]
            ratio = np.zeros_like(lum_dense)
            valid = foreground_mask & (lum_flat > 0.05)
            ratio[valid] = lum_dense[valid] / lum_flat[valid]

            # Deep cavity regions: valid foreground where dense light drops to < 25% of flat
            cavity_pixels = np.sum(valid & (ratio < 0.25))
            total_fg_pixels = np.sum(valid)
            cavity_density_pct = float((cavity_pixels / max(total_fg_pixels, 1)) * 100.0)

            return {
                "status": "success",
                "silhouette_fill_percentage": sil_fill_pct,
                "cavity_density_percentage": cavity_density_pct,
                "mean_shading_contrast": float(np.std(ratio[valid])) if total_fg_pixels > 0 else 0.0
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Tier 4: Comparative Engine (Alien 1 vs Alien 2 vs Alien N)
# ---------------------------------------------------------------------------
class ComparativeEngine:
    """Cross-references study records to find anatomical and stylistic invariants."""

    @staticmethod
    def compare_studies(study_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Takes N study records and calculates:
          - Proportional invariants (mean cranial ratio, variance)
          - Structural consistency (planar percentage consistency)
          - Material painting signature invariants
        """
        if not study_records:
            return {"error": "No study records provided"}

        ids = [rec.get("sculpt_id", f"item_{i}") for i, rec in enumerate(study_records)]
        cranial_ratios = [rec["mold"]["cranial_to_facial_ratio"] for rec in study_records]
        planar_pcts = [rec["shape"]["planar_surface_percentage"] for rec in study_records]
        pigment_couplings = [rec["paint"]["pigment_coupling_to_curvature"] for rec in study_records]

        return {
            "compared_sculpt_ids": ids,
            "sample_count": len(study_records),
            "proportional_invariants": {
                "mean_cranial_facial_ratio": float(np.mean(cranial_ratios)),
                "std_cranial_facial_ratio": float(np.std(cranial_ratios)),
                "is_ratio_invariant": bool(np.std(cranial_ratios) < 0.15)
            },
            "surface_style_invariants": {
                "mean_planar_percentage": float(np.mean(planar_pcts)),
                "std_planar_percentage": float(np.std(planar_pcts)),
                "style_class": "chiseled_planar" if np.mean(planar_pcts) > 25.0 else "organic_sculpted"
            },
            "paint_instinct_invariants": {
                "mean_curvature_pigment_coupling": float(np.mean(pigment_couplings)),
                "description": "Accentuated cavities & crests" if np.mean(pigment_couplings) > 0.3 else "Uniform / bioluminescent"
            }
        }


# ---------------------------------------------------------------------------
# Study Runner / Manifest Exporter
# ---------------------------------------------------------------------------
def execute_study(
    sculpt_id: str,
    vertices: np.ndarray,
    faces: np.ndarray,
    vertex_colors: Optional[np.ndarray] = None,
    photo_pairs: Optional[Dict[str, Tuple[str, str]]] = None,
    output_dir: str = "Projects/3drealms/models/nomad_intake/studies"
) -> Dict[str, Any]:
    """
    Executes a complete 3-Tier study on a sculpt and exports structured JSON manifest.
    """
    print(f"[StudyEngine] Digesting sculpt '{sculpt_id}' ({len(vertices)} vertices, {len(faces)} faces)...")

    # Tier 1: Mold
    mold_data = MoldExtractor.analyze_mesh_mold(vertices, faces)
    
    # Tier 2: Shape
    shape_data = ShapeExtractor.extract_shape_metrics(vertices, faces)
    
    # Tier 3: Paint
    curv_info = ShapeExtractor.compute_vertex_curvatures(vertices, faces)
    if vertex_colors is None:
        # Default neutral grey
        vertex_colors = np.full((len(vertices), 3), 0.7, dtype=np.float32)
    paint_data = PaintExtractor.analyze_vertex_colors(vertex_colors, curv_info["mean_curvature"])

    # Photo Analysis
    photo_results = {}
    if photo_pairs:
        for view_name, (flat_path, dense_path) in photo_pairs.items():
            print(f"[StudyEngine] Analyzing photo pair '{view_name}'...")
            photo_results[view_name] = PaintExtractor.analyze_photo_pair(flat_path, dense_path)

    study_manifest = {
        "sculpt_id": sculpt_id,
        "mold": mold_data,
        "shape": shape_data,
        "paint": paint_data,
        "photo_inversion": photo_results
    }

    # Export to disk
    target_path = os.path.join(output_dir, sculpt_id)
    os.makedirs(target_path, exist_ok=True)
    manifest_file = os.path.join(target_path, "study_manifest.json")
    with open(manifest_file, "w") as f:
        json.dump(study_manifest, f, indent=2)

    print(f"[StudyEngine] Study manifest written successfully -> {manifest_file}")
    return study_manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="3DRealms Sculpt Study Perception Engine")
    parser.add_argument("--json", help="Path to raw sculpt JSON payload")
    parser.add_argument("--out", default="Projects/3drealms/models/nomad_intake/studies", help="Output directory")
    args = parser.parse_args()

    if args.json and os.path.exists(args.json):
        with open(args.json) as f:
            data = json.load(f)
        sculpt_id = data.get("sculpt_id", "sculpt")
        v = np.asarray(data["vertices"], dtype=np.float32)
        f_list = data["faces"]
        f = np.asarray(f_list)
        c = np.asarray(data["colors"], dtype=np.float32) if data.get("colors") else None
        
        # Check if renders exist in output dir
        photo_pairs = {}
        renders_dir = os.path.join(args.out, "renders")
        if os.path.exists(renders_dir):
            for angle in ["front", "right", "back", "left", "hero"]:
                flat = os.path.join(renders_dir, f"{sculpt_id}_{angle}_flat.png")
                dense = os.path.join(renders_dir, f"{sculpt_id}_{angle}_dense.png")
                if os.path.exists(flat) and os.path.exists(dense):
                    photo_pairs[angle] = (flat, dense)
                    
        execute_study(sculpt_id, v, f, c, photo_pairs, args.out)
    else:
        print("[StudyEngine] Module compiled and initialized cleanly.")
