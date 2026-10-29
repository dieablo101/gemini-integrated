#version 450
layout(local_size_x = 64, local_size_y = 1, local_size_z = 1) in;

// Inbound plant state from biophysical simulation
struct PlantData {
    vec4 position_scale;         // xyz = position, w = trunk scale
    vec4 biophysical_properties; // x = LAI, y = wind_deflection_x, z = wind_deflection_z, w = transpiration
    vec4 physiological_state;   // x = solar_occlusion, y = glucose_reserve, z = unused, w = unused
    vec4 padding;
};

layout(std430, binding = 0) readonly buffer PlantInputBuffer {
    PlantData plants[];
};

// Output GPU indirect draw instance buffer for MultiMesh foliage render pass
struct FoliageGPUInstance {
    mat4 modelMatrix;            // Transform matrix with dynamic wind deformation
    vec4 colorFactor;            // RGB = Chlorophyll green modulated by glucose, A = LAI opacity
    vec4 microclimateFactor;     // x = cooling, y = shadow occlusion, zw = reserved
};

layout(std430, binding = 1) writeonly buffer FoliageInstanceOutput {
    FoliageGPUInstance instances[];
};

// Push constants / uniforms
layout(push_constant) uniform PushConstants {
    uint totalPlantCount;
    float globalWindTime;
} pc;

void main() {
    uint idx = gl_GlobalInvocationID.x;
    if (idx >= pc.totalPlantCount) return;

    PlantData p = plants[idx];

    vec3 basePos = p.position_scale.xyz;
    float trunkScale = p.position_scale.w;
    float lai = p.biophysical_properties.x;
    vec2 wind = p.biophysical_properties.yz;
    float transpiration = p.biophysical_properties.w;
    float occlusion = p.physiological_state.x;
    float glucose = p.physiological_state.y;

    // Real-time wind gust flutter (Euler angle perturbation)
    float flutter = sin(pc.globalWindTime * 3.0 + basePos.x * 0.5 + basePos.z * 0.5) * 0.08;
    vec2 dynamicWind = wind + vec2(flutter, flutter * 0.7);

    // Build transformation matrix with wind shear
    mat4 transform = mat4(1.0);
    // Scale
    transform[0][0] = trunkScale;
    transform[1][1] = trunkScale;
    transform[2][2] = trunkScale;
    // Wind bending shear (higher canopy bends further: y affects x and z)
    transform[1][0] = dynamicWind.x;
    transform[1][2] = dynamicWind.y;
    // Position translation
    transform[3] = vec4(basePos, 1.0);

    // Dynamic Chlorophyll Green modulation based on photon harvesting and glucose
    // Healthier plants with high glucose & light have vibrant emerald foliage; starved plants yellow/fade
    vec3 baseLeafColor = vec3(0.12, 0.48, 0.16); // Healthy chlorophyll
    vec3 stressLeafColor = vec3(0.55, 0.45, 0.15); // Carotenoid yellow under drought/starvation
    vec3 foliageColor = mix(stressLeafColor, baseLeafColor, clamp(glucose * 1.5, 0.1, 1.0));

    // Fill output instance
    instances[idx].modelMatrix = transform;
    instances[idx].colorFactor = vec4(foliageColor, clamp(lai / 3.0, 0.2, 1.0));
    instances[idx].microclimateFactor = vec4(transpiration, occlusion, 0.0, 0.0);
}
