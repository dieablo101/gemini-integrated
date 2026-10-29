# Holodeck Engine (3DRealms)

**Holodeck** is the synthesis engine that bridges creative assets (meshes, FLUX procedural shaders) and physical engine simulations. 

At its core, Holodeck operates like a headless **Substance Painter** tailored for AI programmatic access, while maintaining clean, serializable data structures for future user-facing UI integration.

---

## Architecture Overview

```text
engines/holodeck/
├── holodeck_engine.gd                 # Core API & Orchestrator Facade
├── painter/
│   ├── holodeck_baker.gd              # Headless Mesh Baker (Curvature, AO, Thickness, IDs)
│   ├── semantic_segmenter.gd          # Surface Semantic Dissector (Named regions / slots)
│   ├── layer_compositor.gd            # Procedural Layer & Mask Compositor (Smart Materials)
│   ├── holodeck_compositor.gdshader   # Spatial shader executing multi-layer mask math
│   └── viewport_bridge.gd             # Offscreen 3D Godot Viewport harness & snapshot capture
└── recipes/
    ├── painter_recipe.gd              # Pure Resource / JSON data schema
    └── samples/
        └── weathered_cutlass.json     # Concrete multi-layer recipe manifest
```

---

## The Four Core Painter Components

### 1. Headless Mesh Map Baker (`holodeck_baker.gd`)
Substance Painter's procedural intelligence relies on baked geometric maps. Holodeck extracts these headlessly directly from Godot `ArrayMesh` geometry without external DCC tools:
* **Curvature Map:** High-frequency edge detection and surface concavity.
* **Ambient Occlusion Map:** Crevice depth and recessed pocket accumulation.
* **Thickness Map:** Volumetric depth for subsurface scattering (skin, wax, fabric).
* **Material ID Map:** Segmented color codes isolating mesh parts.

### 2. Semantic Segmenter (`semantic_segmenter.gd`)
Inspects mesh surface arrays, material slots, and UV coordinate clusters to map numeric indices to semantic labels (e.g. `Slot 0 -> "blade"`, `Slot 1 -> "crossguard"`, `Slot 2 -> "grip"`).

### 3. Layer Compositor (`layer_compositor.gd` & `.gdshader`)
Stacks base FLUX procedural shaders with dynamic weathering masks:
* **Curvature Mask:** Automatically scratches, chips, or shines high ridges.
* **AO Mask:** Accumulates dirt, mud, blood, and patina inside crevices.
* **FLUX Parameters:** Seamlessly modulates roughness, metallic, and albedo uniforms.

### 4. Viewport Bridge (`viewport_bridge.gd`)
Spins up a headless, offscreen `SubViewport` with studio lighting (Key, Fill, HDRI tone mapping) and an orbiting camera. Renders high-fidelity PNG snapshots for autonomous AI visual evaluation or UI streaming.

---

## AI Execution Example

```gdscript
var mesh_inst = $CutlassInstance
var recipe = PainterRecipe.from_json_dict(json_data)

# 1. Execute full painting & baking pipeline headlessly
var result = HolodeckEngine.execute_recipe(mesh_inst, recipe, 1024)

# 2. Capture multi-angle visual audit snapshots
HolodeckEngine.capture_preview(mesh_inst, "user://cutlass_preview.png", 45.0, 20.0)
```
