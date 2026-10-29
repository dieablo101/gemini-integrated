shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// FLUX Procedural Surface Shader: Blackened Cast Iron Trim
// Deep gothic charcoal iron with pitted corrosion and micro-grain.

uniform vec3 u_albedo_base : source_color = vec3(0.12, 0.12, 0.14);
uniform vec3 u_albedo_pitting : source_color = vec3(0.06, 0.05, 0.06);
uniform float u_scale = 16.0;
uniform float u_roughness = 0.55;
uniform float u_metallic = 0.88;

float flux_hash(vec2 p) {
    uvec2 u = uvec2(floatBitsToUint(p.x), floatBitsToUint(p.y));
    uint h = u.x * 2246822519u + u.y * 3266489917u + 668265263u;
    h = (h ^ (h >> 15u)) * 2147483647u;
    return float(h & 0x00FFFFFFu) / float(0x01000000u);
}

float flux_fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(vec2(0.8, 0.6), vec2(-0.6, 0.8));
    for (int i = 0; i < 3; i++) {
        vec2 i_pos = floor(p);
        vec2 f = fract(p);
        vec2 u = f * f * (3.0 - 2.0 * f);
        float n = mix(mix(flux_hash(i_pos + vec2(0.0, 0.0)), flux_hash(i_pos + vec2(1.0, 0.0)), u.x),
                      mix(flux_hash(i_pos + vec2(0.0, 1.0)), flux_hash(i_pos + vec2(1.0, 1.0)), u.x), u.y);
        v += a * n;
        p = rot * p * 2.0;
        a *= 0.5;
    }
    return v;
}

void fragment() {
    vec2 st = UV * u_scale;
    float pit = flux_fbm(st);
    
    // Height & analytical normal calculation
    float height = pit * 0.15;
    vec3 n_mod = normalize(vec3(-dFdx(height) * 6.0, -dFdy(height) * 6.0, 1.0));
    
    // Albedo pitting
    vec3 col = mix(u_albedo_pitting, u_albedo_base, smoothstep(0.3, 0.7, pit));
    
    ALBEDO = col;
    METALLIC = u_metallic;
    ROUGHNESS = clamp(u_roughness + (1.0 - pit) * 0.25, 0.1, 0.95);
    NORMAL = (VIEW_MATRIX * vec4(n_mod, 0.0)).xyz;
}
