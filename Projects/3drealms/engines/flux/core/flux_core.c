#include "flux_core.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

#define FLUX_PI 3.14159265358979323846f

uint32_t flux_hash32(uint32_t x) {
    x ^= x >> 16;
    x *= 0x7feb352dU;
    x ^= x >> 15;
    x *= 0x846ca68bU;
    x ^= x >> 16;
    return x;
}

float flux_hash2d(float x, float y, uint32_t seed) {
    union { float f; uint32_t u; } ux = {x}, uy = {y};
    uint32_t h = flux_hash32(ux.u ^ flux_hash32(uy.u ^ seed));
    return (float)(h & 0x00FFFFFF) / (float)0x01000000;
}

FluxVec2 flux_hash2d_vec(float x, float y, uint32_t seed) {
    float a = flux_hash2d(x, y, seed) * 2.0f * FLUX_PI;
    FluxVec2 v = { cosf(a), sinf(a) };
    return v;
}

static inline float flux_lerp(float a, float b, float t) {
    return a + t * (b - a);
}

static inline float flux_smoothstep(float edge0, float edge1, float x) {
    float t = (x - edge0) / (edge1 - edge0);
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    return t * t * (3.0f - 2.0f * t);
}

float flux_simplex2d(float x, float y, uint32_t seed) {
    const float F2 = 0.366025403784439f; // 0.5*(sqrt(3.0)-1.0)
    const float G2 = 0.211324865405187f; // (3.0-sqrt(3.0))/6.0

    float s = (x + y) * F2;
    int i = (int)floorf(x + s);
    int j = (int)floorf(y + s);

    float t = (float)(i + j) * G2;
    float X0 = (float)i - t;
    float Y0 = (float)j - t;
    float x0 = x - X0;
    float y0 = y - Y0;

    int i1, j1;
    if (x0 > y0) { i1 = 1; j1 = 0; }
    else { i1 = 0; j1 = 1; }

    float x1 = x0 - (float)i1 + G2;
    float y1 = y0 - (float)j1 + G2;
    float x2 = x0 - 1.0f + 2.0f * G2;
    float y2 = y0 - 1.0f + 2.0f * G2;

    float n0, n1, n2;

    float t0 = 0.5f - x0 * x0 - y0 * y0;
    if (t0 < 0.0f) n0 = 0.0f;
    else {
        t0 *= t0;
        FluxVec2 g0 = flux_hash2d_vec((float)i, (float)j, seed);
        n0 = t0 * t0 * (g0.x * x0 + g0.y * y0);
    }

    float t1 = 0.5f - x1 * x1 - y1 * y1;
    if (t1 < 0.0f) n1 = 0.0f;
    else {
        t1 *= t1;
        FluxVec2 g1 = flux_hash2d_vec((float)(i + i1), (float)(j + j1), seed);
        n1 = t1 * t1 * (g1.x * x1 + g1.y * y1);
    }

    float t2 = 0.5f - x2 * x2 - y2 * y2;
    if (t2 < 0.0f) n2 = 0.0f;
    else {
        t2 *= t2;
        FluxVec2 g2 = flux_hash2d_vec((float)(i + 1), (float)(j + 1), seed);
        n2 = t2 * t2 * (g2.x * x2 + g2.y * y2);
    }

    return 70.0f * (n0 + n1 + n2);
}

float flux_fbm2d(float x, float y, int octaves, float lacunarity, float gain, uint32_t seed) {
    float sum = 0.0f;
    float amp = 1.0f;
    float freq = 1.0f;
    float max_amp = 0.0f;

    for (int i = 0; i < octaves; i++) {
        sum += amp * flux_simplex2d(x * freq, y * freq, seed + (uint32_t)i * 1013U);
        max_amp += amp;
        freq *= lacunarity;
        amp *= gain;
    }
    return sum / max_amp;
}

float flux_worley2d(float x, float y, float jitter, uint32_t seed, float *out_f2_minus_f1) {
    int xi = (int)floorf(x);
    int yi = (int)floorf(y);
    float xf = x - (float)xi;
    float yf = y - (float)yi;

    float f1 = 999.0f;
    float f2 = 999.0f;

    for (int dy = -1; dy <= 1; dy++) {
        for (int dx = -1; dx <= 1; dx++) {
            float rx = (float)dx + jitter * flux_hash2d((float)(xi + dx), (float)(yi + dy), seed);
            float ry = (float)dy + jitter * flux_hash2d((float)(xi + dx), (float)(yi + dy), seed + 4999U);
            float dist = sqrtf((rx - xf) * (rx - xf) + (ry - yf) * (ry - yf));

            if (dist < f1) {
                f2 = f1;
                f1 = dist;
            } else if (dist < f2) {
                f2 = dist;
            }
        }
    }

    if (out_f2_minus_f1) {
        *out_f2_minus_f1 = f2 - f1;
    }
    return f1;
}

FluxSurfaceOutput flux_evaluate_surface(FluxVec2 uv, const FluxRecipe *recipe) {
    FluxSurfaceOutput out;
    float f2_minus_f1 = 0.0f;
    float scale = (recipe->cell_scale > 0.001f) ? recipe->cell_scale : 4.0f;
    
    /* Evaluate Cell / Mortar structure */
    float w = flux_worley2d(uv.x * scale, uv.y * scale, recipe->cell_jitter, recipe->seed, &f2_minus_f1);
    
    /* Mortar mask based on F2 - F1 boundary distance */
    float mortar_mask = 1.0f - flux_smoothstep(0.0f, recipe->mortar_width, f2_minus_f1);
    
    /* Weathering / micro-porosity */
    float micro_rough = flux_fbm2d(uv.x * scale * 4.0f, uv.y * scale * 4.0f, 4, 2.0f, 0.5f, recipe->seed + 77U);
    
    /* Calculate Height */
    float stone_height = (1.0f - w * 0.7f) * (1.0f - mortar_mask * recipe->mortar_depth);
    out.height = stone_height + micro_rough * 0.08f * recipe->weathering_intensity;
    
    /* Derive Analytical Normals via Finite Differences */
    float eps = 0.005f;
    float h_r = 1.0f - flux_worley2d((uv.x + eps) * scale, uv.y * scale, recipe->cell_jitter, recipe->seed, NULL);
    float h_u = 1.0f - flux_worley2d(uv.x * scale, (uv.y + eps) * scale, recipe->cell_jitter, recipe->seed, NULL);
    
    float dx = (h_r - stone_height) / eps;
    float dy = (h_u - stone_height) / eps;
    
    out.normal_offset.x = -dx * 0.5f;
    out.normal_offset.y = -dy * 0.5f;
    out.normal_offset.z = 1.0f;
    
    /* Cavity Ambient Occlusion derived from mortar depth & Worley cell gradient */
    out.cavity_ao = flux_smoothstep(0.02f, 0.25f, f2_minus_f1);
    
    /* Albedo interpolation: Mortar -> Primary Tint -> Weathering Highlights */
    float tint_mix = flux_smoothstep(0.1f, 0.8f, stone_height);
    out.albedo.x = flux_lerp(recipe->mortar_tint.x, flux_lerp(recipe->primary_tint.x, recipe->secondary_tint.x, tint_mix), 1.0f - mortar_mask);
    out.albedo.y = flux_lerp(recipe->mortar_tint.y, flux_lerp(recipe->primary_tint.y, recipe->secondary_tint.y, tint_mix), 1.0f - mortar_mask);
    out.albedo.z = flux_lerp(recipe->mortar_tint.z, flux_lerp(recipe->primary_tint.z, recipe->secondary_tint.z, tint_mix), 1.0f - mortar_mask);
    
    /* Physical parameters */
    out.roughness = recipe->base_roughness + (1.0f - out.cavity_ao) * 0.2f + micro_rough * 0.15f;
    if (out.roughness > 1.0f) out.roughness = 1.0f;
    if (out.roughness < 0.0f) out.roughness = 0.0f;
    
    out.metallic = recipe->base_metallic;
    return out;
}

int flux_compile_godot_shader(const FluxRecipe *recipe, const char *material_name, char *out_buffer, size_t max_len) {
    const char *template = 
        "shader_type spatial;\n"
        "render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;\n\n"
        "// FLUX Procedural Surface Shader: %s\n"
        "// Generated dynamically by FLUX Engine (Pure Math, No Raster Textures)\n\n"
        "uniform uint u_seed = %u;\n"
        "uniform float u_scale = %.3f;\n"
        "uniform float u_mortar_width = %.3f;\n"
        "uniform float u_mortar_depth = %.3f;\n"
        "uniform vec3 u_primary_color : source_color = vec3(%.3f, %.3f, %.3f);\n"
        "uniform vec3 u_secondary_color : source_color = vec3(%.3f, %.3f, %.3f);\n"
        "uniform vec3 u_mortar_color : source_color = vec3(%.3f, %.3f, %.3f);\n"
        "uniform float u_roughness = %.3f;\n"
        "uniform float u_metallic = %.3f;\n\n"
        "float flux_hash2d(vec2 p, uint s) {\n"
        "    uvec2 u = uvec2(floatBitsToUint(p.x), floatBitsToUint(p.y));\n"
        "    uint h = u.x * 374761393u + u.y * 668265263u + s;\n"
        "    h = (h ^ (h >> 13u)) * 1274126177u;\n"
        "    return float(h & 0x00FFFFFFu) / float(0x01000000u);\n"
        "}\n\n"
        "vec2 flux_worley2d(vec2 uv, uint s) {\n"
        "    vec2 p = floor(uv);\n"
        "    vec2 f = fract(uv);\n"
        "    float f1 = 8.0;\n"
        "    float f2 = 8.0;\n"
        "    for (int j = -1; j <= 1; j++) {\n"
        "        for (int i = -1; i <= 1; i++) {\n"
        "            vec2 b = vec2(float(i), float(j));\n"
        "            vec2 r = b - f + vec2(\n"
        "                flux_hash2d(p + b, s),\n"
        "                flux_hash2d(p + b, s + 3141u)\n"
        "            );\n"
        "            float d = length(r);\n"
        "            if (d < f1) {\n"
        "                f2 = f1;\n"
        "                f1 = d;\n"
        "            } else if (d < f2) {\n"
        "                f2 = d;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "    return vec2(f1, f2 - f1);\n"
        "}\n\n"
        "void fragment() {\n"
        "    vec2 st = UV * u_scale;\n"
        "    vec2 w = flux_worley2d(st, u_seed);\n"
        "    float f1 = w.x;\n"
        "    float f2_minus_f1 = w.y;\n"
        "    \n"
        "    // Mortar groove calculation\n"
        "    float mortar = 1.0 - smoothstep(0.0, u_mortar_width, f2_minus_f1);\n"
        "    \n"
        "    // Analytical normal via dFdx / dFdy (Zero texture samplers!)\n"
        "    float height = (1.0 - f1 * 0.7) * (1.0 - mortar * u_mortar_depth);\n"
        "    vec3 normal_analytical = normalize(vec3(-dFdx(height) * 4.0, -dFdy(height) * 4.0, 1.0));\n"
        "    \n"
        "    // Cavity occlusion in cracks\n"
        "    float cavity = smoothstep(0.02, 0.25, f2_minus_f1);\n"
        "    \n"
        "    // Albedo blending\n"
        "    vec3 stone = mix(u_primary_color, u_secondary_color, smoothstep(0.2, 0.8, height));\n"
        "    vec3 final_albedo = mix(stone, u_mortar_color, mortar);\n"
        "    \n"
        "    ALBEDO = final_albedo * cavity;\n"
        "    ROUGHNESS = clamp(u_roughness + (1.0 - cavity) * 0.35, 0.0, 1.0);\n"
        "    METALLIC = u_metallic;\n"
        "    NORMAL = (VIEW_MATRIX * vec4(normal_analytical, 0.0)).xyz;\n"
        "    AO = cavity;\n"
        "}\n";

    return snprintf(out_buffer, max_len, template,
        material_name ? material_name : "Flux_Procedural",
        recipe->seed,
        recipe->cell_scale,
        recipe->mortar_width,
        recipe->mortar_depth,
        recipe->primary_tint.x, recipe->primary_tint.y, recipe->primary_tint.z,
        recipe->secondary_tint.x, recipe->secondary_tint.y, recipe->secondary_tint.z,
        recipe->mortar_tint.x, recipe->mortar_tint.y, recipe->mortar_tint.z,
        recipe->base_roughness,
        recipe->base_metallic
    );
}
