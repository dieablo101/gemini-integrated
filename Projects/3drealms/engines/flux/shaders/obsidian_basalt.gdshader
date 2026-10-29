shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// FLUX Procedural Surface Shader: Obsidian_Gothic_Basalt
// World-space triplanar projection: perfect scaling for tall monoliths, steps, and ramps.
// Zero raster textures, zero VRAM overhead.

uniform int u_seed = 373592855;
uniform float u_scale = 0.8;
uniform float u_mortar_width = 0.06;
uniform float u_mortar_depth = 0.35;
uniform vec3 u_primary_color : source_color = vec3(0.12, 0.13, 0.17);
uniform vec3 u_secondary_color : source_color = vec3(0.22, 0.24, 0.30);
uniform vec3 u_mortar_color : source_color = vec3(0.04, 0.04, 0.05);
uniform float u_roughness = 0.35;
uniform float u_metallic = 0.12;

varying vec3 v_world_pos;
varying vec3 v_world_normal;

void vertex() {
    v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    v_world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float flux_hash2d(vec2 p, uint s) {
    uvec2 u = uvec2(floatBitsToUint(p.x), floatBitsToUint(p.y));
    uint h = u.x * 374761393u + u.y * 668265263u + s;
    h = (h ^ (h >> 13u)) * 1274126177u;
    return float(h & 0x00FFFFFFu) / float(0x01000000u);
}

vec2 flux_worley2d(vec2 uv, uint s) {
    vec2 p = floor(uv);
    vec2 f = fract(uv);
    float f1 = 8.0;
    float f2 = 8.0;
    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 b = vec2(float(i), float(j));
            vec2 r = b - f + vec2(
                flux_hash2d(p + b, s),
                flux_hash2d(p + b, s + 3141u)
            );
            float d = length(r);
            if (d < f1) {
                f2 = f1;
                f1 = d;
            } else if (d < f2) {
                f2 = d;
            }
        }
    }
    return vec2(f1, f2 - f1);
}

void fragment() {
    uint seed_u = uint(abs(u_seed));
    
    // Triplanar projection weights based on absolute world normal
    vec3 blend = abs(v_world_normal);
    blend /= (blend.x + blend.y + blend.z + 0.0001);
    
    // Sample planar coordinates across XZ (top), XY (front/back), ZY (sides)
    vec2 uv_top = v_world_pos.xz * u_scale;
    vec2 uv_front = v_world_pos.xy * u_scale;
    vec2 uv_side = v_world_pos.zy * u_scale;
    
    vec2 w_top = flux_worley2d(uv_top, seed_u);
    vec2 w_front = flux_worley2d(uv_front, seed_u + 101u);
    vec2 w_side = flux_worley2d(uv_side, seed_u + 202u);
    
    float f1 = w_top.x * blend.y + w_front.x * blend.z + w_side.x * blend.x;
    float f2_f1 = w_top.y * blend.y + w_front.y * blend.z + w_side.y * blend.x;
    
    // Mortar groove calculation
    float mortar = 1.0 - smoothstep(0.01, u_mortar_width, f2_f1);
    
    // Surface height and screen-space analytical derivatives
    float height = (1.0 - f1 * 0.5) * (1.0 - mortar * u_mortar_depth);
    
    // Cavity occlusion in cracks and joints
    float cavity = smoothstep(0.02, 0.22, f2_f1);
    
    // Color blending: obsidian core to basalt highlight
    vec3 stone = mix(u_primary_color, u_secondary_color, smoothstep(0.2, 0.8, height));
    vec3 final_albedo = mix(stone, u_mortar_color, mortar);
    
    ALBEDO = final_albedo * cavity;
    ROUGHNESS = clamp(u_roughness + (1.0 - cavity) * 0.45, 0.05, 0.95);
    METALLIC = u_metallic;
    AO = cavity;
    
    // Screen-space normal perturbation
    NORMAL = normalize(NORMAL + vec3(-dFdx(height) * 3.5, -dFdy(height) * 3.5, 0.0));
}
