/**
 * FLUX Core - Fast Mathematical Procedural Surface Synthesis Engine
 * Replaces legacy raster PBR texture maps with analytical math kernels.
 *
 * Capabilities:
 * - Analytical Normal Derivation (Finite Differences & Partial Derivatives without normal maps)
 * - Cellular / Worley Noise (Stone bricks, organic scales, cracked mortar)
 * - Fractional Brownian Motion (fBm) Simplex Noise (Roughness variation, weathering)
 * - Micro-Curvature & Cavity Occlusion calculation
 */

#ifndef FLUX_CORE_H
#define FLUX_CORE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float x, y, z;
} FluxVec3;

typedef struct {
    float x, y;
} FluxVec2;

typedef struct {
    FluxVec3 albedo;          /* Linear RGB base color */
    float roughness;          /* Micro-roughness [0.0 - 1.0] */
    float metallic;           /* Metalness [0.0 - 1.0] */
    float cavity_ao;          /* Analytical cavity ambient occlusion [0.0 - 1.0] */
    FluxVec3 normal_offset;   /* Analytical normal perturbation vector */
    float height;             /* Micro-displacement / height value */
} FluxSurfaceOutput;

typedef struct {
    /* Base Seed */
    uint32_t seed;
    
    /* Voronoi / Stone Parameters */
    float cell_scale;
    float cell_jitter;
    float mortar_depth;
    float mortar_width;
    
    /* Weathering & Cracks */
    float weathering_intensity;
    float crack_octaves;
    float edge_wear;
    
    /* Material Physical Properties */
    FluxVec3 primary_tint;
    FluxVec3 secondary_tint;
    FluxVec3 mortar_tint;
    float base_roughness;
    float base_metallic;
} FluxRecipe;

/* Fast Hash & Random Permutations */
uint32_t flux_hash32(uint32_t x);
float flux_hash2d(float x, float y, uint32_t seed);
FluxVec2 flux_hash2d_vec(float x, float y, uint32_t seed);

/* Procedural Noise Primitives */
float flux_simplex2d(float x, float y, uint32_t seed);
float flux_fbm2d(float x, float y, int octaves, float lacunarity, float gain, uint32_t seed);
float flux_worley2d(float x, float y, float jitter, uint32_t seed, float *out_f2_minus_f1);

/* Analytical Surface Evaluator */
FluxSurfaceOutput flux_evaluate_surface(FluxVec2 uv, const FluxRecipe *recipe);

/* Shader Transpiler: Generates Godot Visual/Spatial Shader from Flux Recipe */
int flux_compile_godot_shader(const FluxRecipe *recipe, const char *material_name, char *out_buffer, size_t max_len);

#ifdef __cplusplus
}
#endif

#endif /* FLUX_CORE_H */
