shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// FLUX Procedural Surface Shader: Honed High-Carbon Steel Blade
// Mirror-finished razor bevels with longitudinal grinding marks.

uniform vec3 u_blade_bright : source_color = vec3(0.85, 0.88, 0.92);
uniform vec3 u_blade_body : source_color = vec3(0.58, 0.62, 0.68);
uniform vec3 u_fuller_dark : source_color = vec3(0.20, 0.22, 0.25);
uniform float u_roughness_edge = 0.10;
uniform float u_roughness_body = 0.22;

float flux_hash(vec2 p) {
    uvec2 u = uvec2(floatBitsToUint(p.x), floatBitsToUint(p.y));
    uint h = u.x * 1274126177u + u.y * 374761393u + 982451653u;
    h = (h ^ (h >> 13u)) * 668265263u;
    return float(h & 0x00FFFFFFu) / float(0x01000000u);
}

void fragment() {
    // Longitudinal whetstone grind lines along the blade (stretched heavily on Y)
    vec2 grind_uv = vec2(UV.x * 64.0, UV.y * 2.0);
    float grind = flux_hash(floor(grind_uv));
    
    // Geometric edge sharpness detection
    vec3 geom_norm = normalize(cross(dFdx(VERTEX), dFdy(VERTEX)));
    float edge = clamp(length(fwidth(geom_norm)) * 8.0, 0.0, 1.0);
    
    // Blade gradient: bright edge vs tempered body
    vec3 col = mix(u_blade_body, u_blade_bright, edge * 0.7);
    col += (grind - 0.5) * 0.06;
    
    // Micro-groove normal perturbation
    float groove = grind * 0.03;
    
    ALBEDO = col;
    METALLIC = 0.98;
    ROUGHNESS = clamp(mix(u_roughness_body, u_roughness_edge, edge) + (grind - 0.5) * 0.04, 0.05, 0.8);
    NORMAL = normalize(NORMAL + vec3(-dFdx(groove) * 12.0, -dFdy(groove) * 12.0, 0.0));
}
