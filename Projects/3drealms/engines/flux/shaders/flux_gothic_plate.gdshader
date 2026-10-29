shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// FLUX Procedural Surface Shader: Gothic Tempered Plate Steel
// Pure GPU Math, zero raster textures, zero VRAM overhead.

uniform vec3 u_albedo_base : source_color = vec3(0.38, 0.40, 0.44);
uniform vec3 u_albedo_edge : source_color = vec3(0.65, 0.68, 0.72);
uniform vec3 u_cavity_color : source_color = vec3(0.08, 0.08, 0.10);
uniform float u_scale = 12.0;
uniform float u_roughness_base = 0.28;
uniform float u_metallic = 0.96;

float flux_hash(vec2 p) {
    uvec2 u = uvec2(floatBitsToUint(p.x), floatBitsToUint(p.y));
    uint h = u.x * 374761393u + u.y * 668265263u + 1013904223u;
    h = (h ^ (h >> 13u)) * 1274126177u;
    return float(h & 0x00FFFFFFu) / float(0x01000000u);
}

float flux_noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(flux_hash(i + vec2(0.0, 0.0)), flux_hash(i + vec2(1.0, 0.0)), u.x),
               mix(flux_hash(i + vec2(0.0, 1.0)), flux_hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

void fragment() {
    vec2 st = UV * u_scale;
    
    // Anisotropic brushed striations (cold-rolled steel)
    float brush = flux_noise(vec2(st.x * 32.0, st.y * 1.5));
    // Fine micro-scratches
    float scratches = flux_noise(st * 48.0);
    
    // Analytical normal micro-detail via screen-space derivatives
    float micro_height = (brush * 0.4 + scratches * 0.6) * 0.08;
    
    // Curvature / edge detection from geometric normals
    vec3 geom_norm = normalize(cross(dFdx(VERTEX), dFdy(VERTEX)));
    float edge_factor = clamp(length(fwidth(geom_norm)) * 5.0, 0.0, 1.0);
    
    // Dark gothic cavity ambient occlusion in crevices
    float cavity = clamp(1.0 - edge_factor * 0.5, 0.25, 1.0);
    
    // Color blending
    vec3 surface_color = mix(u_albedo_base, u_albedo_edge, edge_factor * 0.6);
    surface_color = mix(u_cavity_color, surface_color, cavity);
    
    ALBEDO = surface_color;
    METALLIC = u_metallic;
    ROUGHNESS = clamp(u_roughness_base + (1.0 - edge_factor) * 0.12 - brush * 0.05, 0.08, 0.95);
    NORMAL = normalize(NORMAL + vec3(-dFdx(micro_height) * 8.0, -dFdy(micro_height) * 8.0, 0.0));
    AO = cavity;
}
