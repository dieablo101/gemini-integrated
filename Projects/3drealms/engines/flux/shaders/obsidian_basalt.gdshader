shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// FLUX Procedural Surface Shader: Obsidian_Gothic_Basalt
// Generated dynamically by FLUX Engine (Pure Math, No Raster Textures)

uniform uint u_seed = 3735928559;
uniform float u_scale = 3.500;
uniform float u_mortar_width = 0.080;
uniform float u_mortar_depth = 0.180;
uniform vec3 u_primary_color : source_color = vec3(0.050, 0.040, 0.060);
uniform vec3 u_secondary_color : source_color = vec3(0.140, 0.120, 0.180);
uniform vec3 u_mortar_color : source_color = vec3(0.020, 0.015, 0.025);
uniform float u_roughness = 0.320;
uniform float u_metallic = 0.150;

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
    vec2 st = UV * u_scale;
    vec2 w = flux_worley2d(st, u_seed);
    float f1 = w.x;
    float f2_minus_f1 = w.y;
    
    // Mortar groove calculation
    float mortar = 1.0 - smoothstep(0.0, u_mortar_width, f2_minus_f1);
    
    // Analytical normal via dFdx / dFdy (Zero texture samplers!)
    float height = (1.0 - f1 * 0.7) * (1.0 - mortar * u_mortar_depth);
    vec3 normal_analytical = normalize(vec3(-dFdx(height) * 4.0, -dFdy(height) * 4.0, 1.0));
    
    // Cavity occlusion in cracks
    float cavity = smoothstep(0.02, 0.25, f2_minus_f1);
    
    // Albedo blending
    vec3 stone = mix(u_primary_color, u_secondary_color, smoothstep(0.2, 0.8, height));
    vec3 final_albedo = mix(stone, u_mortar_color, mortar);
    
    ALBEDO = final_albedo * cavity;
    ROUGHNESS = clamp(u_roughness + (1.0 - cavity) * 0.35, 0.0, 1.0);
    METALLIC = u_metallic;
    NORMAL = (VIEW_MATRIX * vec4(normal_analytical, 0.0)).xyz;
    AO = cavity;
}
