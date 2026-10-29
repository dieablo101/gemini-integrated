# engines/lod: Quadric Error Metric (QEM) & Geometric Simplification Engine

`engines/lod/` is the core mathematical geometry engine for continuous Level of Detail (LOD) generation, surface decimation, and screen-space geometric error calculation in 3DRealms.

## Architecture

1. **`qem_solver.gd`**:
   - Computes fundamental Quadric Error Matrices ($K_p = p \cdot p^T$) for every triangle plane.
   - Accumulates vertex quadrics ($Q_v = \sum K_p$).
   - Calculates the optimal contraction target $\mathbf{v}^*$ and minimum quadratic cost for collapsing any edge $(v_1, v_2) \to \mathbf{v}^*$.

2. **`edge_collapser.gd`**:
   - Manages progressive mesh simplification.
   - Enforces topology preservation, normal flip rejection, and UV seam protection.
   - Generates discrete LOD steps or continuous progressive mesh streams.

3. **`error_metric.gd`**:
   - Unreal/Nanite-style screen-space geometric error calculations.
   - Evaluates whether object-space geometric error $(\delta)$ projects to less than the target screen error threshold $(\tau_{\text{pixels}})$:
     $$\epsilon_{\text{screen}} = \frac{\delta \cdot \text{viewport\_height}}{2 \cdot d \cdot \tan(\text{FOV} / 2)}$$
   - Computes exact hysteresis transition distances to eliminate LOD popping.

4. **`lod_orchestrator.gd`**:
   - Facade for external engines (`holodeck`, `destruction`, `eco`).
   - Accepts raw `ArrayMesh`, generates LOD cascades with baked normal/tangent alignment.
