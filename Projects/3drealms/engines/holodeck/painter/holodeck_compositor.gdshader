shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// -----------------------------------------------------------------------------
// Holodeck Compositor Shader (Procedural Substance Layering)
// Blends base FLUX procedural shaders with baked geometric mesh maps:
// - Curvature (Edge Scuffs & Ridge Wear)
// - Ambient Occlusion (Crevice Grime & Dust)
// - Material IDs (Semantic Region Masking)
// -----------------------------------------------------------------------------

// Baked Mesh Maps
uniform sampler2D map_curvature : hint_default_white, filter_linear_mipmap;
uniform sampler2D map_ambient_occlusion : hint_default_white, filter_linear_mipmap;
uniform sampler2D map_thickness : hint_default_black, filter_linear_mipmap;
uniform sampler2D map_material_id : hint_default_black, filter_nearest;

// Target Slot Color (for Semantic Region Masking)
uniform vec4 target_slot_color : source_color = vec4(1.0, 0.0, 0.0, 1.0);
uniform float slot_tolerance : hint_range(0.0, 0.5) = 0.15;

// Layer 1: Base FLUX Surface
uniform vec4 base_albedo : source_color = vec4(0.8, 0.8, 0.8, 1.0);
uniform float base_roughness : hint_range(0.0, 1.0) = 0.4;
uniform float base_metallic : hint_range(0.0, 1.0) = 0.8;

// Layer 2: Edge Wear (Curvature Masked)
uniform vec4 wear_albedo : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float wear_roughness : hint_range(0.0, 1.0) = 0.2;
uniform float wear_metallic : hint_range(0.0, 1.0) = 1.0;
uniform float wear_threshold : hint_range(0.0, 1.0) = 0.6;
uniform float wear_softness : hint_range(0.01, 0.5) = 0.1;
uniform float wear_intensity : hint_range(0.0, 2.0) = 1.0;

// Layer 3: Crevice Grime (AO Masked)
uniform vec4 grime_albedo : source_color = vec4(0.12, 0.10, 0.08, 1.0);
uniform float grime_roughness : hint_range(0.0, 1.0) = 0.95;
uniform float grime_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float grime_threshold : hint_range(0.0, 1.0) = 0.45;
uniform float grime_softness : hint_range(0.01, 0.5) = 0.2;
uniform float grime_intensity : hint_range(0.0, 2.0) = 1.0;

void fragment() {
    // 1. Semantic Slot Isolation
    vec4 id_sample = texture(map_material_id, UV);
    float slot_match = 1.0 - smoothstep(0.0, slot_tolerance, distance(id_sample.rgb, target_slot_color.rgb));
    
    // If not matching target slot and slot is active, fallback
    float region_mask = (target_slot_color.a > 0.0) ? slot_match : 1.0;
    
    // 2. Sample Baked Maps
    float curve = texture(map_curvature, UV).r;
    float ao = texture(map_ambient_occlusion, UV).r;
    
    // 3. Compute Procedural Masks
    float wear_mask = smoothstep(wear_threshold - wear_softness, wear_threshold + wear_softness, curve) * wear_intensity;
    float grime_mask = (1.0 - smoothstep(grime_threshold - grime_softness, grime_threshold + grime_softness, ao)) * grime_intensity;
    
    // 4. Layer Blending Stack
    // Start with Base Surface
    vec3 final_albedo = base_albedo.rgb;
    float final_roughness = base_roughness;
    float final_metallic = base_metallic;
    
    // Blend Edge Wear over Base
    final_albedo = mix(final_albedo, wear_albedo.rgb, wear_mask);
    final_roughness = mix(final_roughness, wear_roughness, wear_mask);
    final_metallic = mix(final_metallic, wear_metallic, wear_mask);
    
    // Blend Crevice Grime on top of everything in recessed pockets
    final_albedo = mix(final_albedo, grime_albedo.rgb, grime_mask);
    final_roughness = mix(final_roughness, grime_roughness, grime_mask);
    final_metallic = mix(final_metallic, grime_metallic, grime_mask);
    
    // Apply final properties with region mask
    ALBEDO = mix(base_albedo.rgb, final_albedo, region_mask);
    ROUGHNESS = mix(base_roughness, final_roughness, region_mask);
    METALLIC = mix(base_metallic, final_metallic, region_mask);
    AO = mix(1.0, ao, region_mask);
    AO_LIGHT_AFFECT = 0.8;
}
