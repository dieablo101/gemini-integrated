#version 450
layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;

// Output 2D render target (HDR additive bloom)
layout(binding = 0, rgba16f) uniform image2D outAuroraColor;

// Electrodynamic Magnetosphere UBO
layout(binding = 1, std140) uniform AuroraUBO {
    vec4 sunDirection;
    vec4 sunColorPAR;
    vec4 sunColorNIR;
    vec4 cameraPos;
    mat4 invView;
    mat4 invProj;
    float planetRadius;
    float atmosphereRadius;
    float henyeyGreensteinG;
    float raymarchStepSize;
    float magnetopauseRadius;
    float solarWindSpeed;
    float auroralIntensity;
    float elapsedTime;
} ubo;

// Simple 3D noise for field line curtain turbulence
float hash(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i + vec3(0,0,0)), hash(i + vec3(1,0,0)), f.x),
                   mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
                   mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
}

// Planetary Dipole magnetic field lines excitation
// Ionization lines: Emerald Green (557.7 nm Atomic Oxygen O(1S)) at 100-200 km altitude
// Upper Violet/Purple (630.0 nm Atomic Oxygen O(1D) + N2+ first negative) at 200-400 km
vec3 evaluateAuroralEmission(vec3 p, float time) {
    // Curtains oscillate along field lines
    float t = time * 0.4;
    vec3 q = p * 0.05 + vec3(0.0, 0.0, t * 0.2);
    
    // Multi-octave curtain ribbons
    float f = 0.5 * noise(q);
    f += 0.25 * noise(q * 2.03 + vec3(t * 0.1));
    f += 0.125 * noise(q * 4.01);

    // High vertical curtain fold frequency
    float curtain = sin(p.x * 0.3 + f * 5.0) * cos(p.z * 0.3 + f * 4.0);
    curtain = smoothstep(0.4, 0.95, abs(curtain));

    // Vertical altitude distribution (lower boundary emerald, upper boundary violet)
    float heightNorm = clamp(p.y / 20.0, 0.0, 1.0);
    vec3 atomicOxygenGreen = vec3(0.08, 0.98, 0.32); // 557.7 nm line
    vec3 molecularNitrogenViolet = vec3(0.65, 0.15, 0.85); // N2+ excitation

    vec3 emissionColor = mix(atomicOxygenGreen, molecularNitrogenViolet, heightNorm);
    return emissionColor * curtain * (1.0 - heightNorm * 0.5);
}

void main() {
    ivec2 pixelCoord = ivec2(gl_GlobalInvocationID.xy);
    ivec2 screenSize = imageSize(outAuroraColor);
    if (pixelCoord.x >= screenSize.x || pixelCoord.y >= screenSize.y) {
        return;
    }

    vec2 uv = (vec2(pixelCoord) + 0.5) / vec2(screenSize);
    vec2 ndc = uv * 2.0 - 1.0;

    // View ray in camera space
    vec4 target = ubo.invProj * vec4(ndc.x, ndc.y, 1.0, 1.0);
    vec3 rayDir = normalize((ubo.invView * vec4(target.xyz / target.w, 0.0)).xyz);
    vec3 rayOrigin = ubo.cameraPos.xyz;

    // Only render aurora when looking towards high latitudes / upper sky
    if (rayDir.y <= 0.05 || ubo.auroralIntensity <= 0.01) {
        return;
    }

    // Auroral layer slab bounds (y = 5.0m to 25.0m in scaled chunk coordinates)
    float tBottom = (5.0 - rayOrigin.y) / rayDir.y;
    float tTop = (25.0 - rayOrigin.y) / rayDir.y;

    float tNear = max(min(tBottom, tTop), 0.0);
    float tFar = max(tBottom, tTop);

    if (tNear >= tFar) return;

    // Raymarch the auroral curtain
    float stepSize = 0.5;
    float t = tNear;
    vec3 accumAurora = vec3(0.0);

    for (int i = 0; i < 40; ++i) {
        if (t >= tFar) break;
        vec3 p = rayOrigin + rayDir * t;
        vec3 emission = evaluateAuroralEmission(p, ubo.elapsedTime);
        accumAurora += emission * stepSize * ubo.auroralIntensity * 0.15;
        t += stepSize;
    }

    // Read underlying image color and additively blend aurora
    vec4 existing = imageLoad(outAuroraColor, pixelCoord);
    vec4 finalColor = vec4(existing.rgb + accumAurora, 1.0);
    imageStore(outAuroraColor, pixelCoord, finalColor);
}
