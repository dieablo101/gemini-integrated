shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// FLUX Procedural Surface Shader: Worn Tanned Leather Wrap
// Organic cellular porosity, cross-wrap grooves, zero raster textures.

uniform vec3 u_leather_base : source_color = vec3(0.18, 0.09, 0.05);
uniform vec3 u_leather_worn : source_color = vec3(0.28, 0.16, 0.10);
uniform vec3 u_crease_color : source_color = vec3(0.06, 0.03, 0.02);
uniform float u_wrap_frequency = 18.0;

float flux_hash(vec2 p) {
    uvec2 u = uvec2(floatBitsToUint(p.x), floatBitsToUint(p.y));
    uint h = u.x * 374761393u + u.y * 668265263u + 314159265u;
    h = (h ^ (h >> 13u)) * 1274126177u;
    return float(h & 0x00FFFFFFu) / float(0x01000000u);
}

void fragment() {
    // Spiral grip wrap ridges
    float wrap = sin(UV.y * u_wrap_frequency * 6.28318 + UV.x * 3.14159);
    float wrap_crease = smoothstep(-0.8, -0.95, wrap);
    
    // Cellular micro-porosity
    vec2 cell_st = UV * 40.0;
    float pore = flux_hash(floor(cell_st));
    
    // Height perturbation
    float height = wrap * 0.1 + pore * 0.02;
    vec3 n_mod = normalize(vec3(-dFdx(height) * 8.0, -dFdy(height) * 8.0, 1.0));
    
    // Color blend
    vec3 col = mix(u_leather_base, u_leather_worn, clamp(wrap * 0.5 + 0.5, 0.0, 1.0));
    col = mix(col, u_crease_color, wrap_crease);
    
    ALBEDO = col;
    METALLIC = 0.0;
    ROUGHNESS = clamp(0.72 - wrap * 0.15 + pore * 0.08, 0.3, 0.95);
    NORMAL = (VIEW_MATRIX * vec4(n_mod, 0.0)).xyz;
}
