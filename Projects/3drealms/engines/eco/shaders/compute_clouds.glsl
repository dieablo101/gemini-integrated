#version 450
layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;

// Output 2D render target (HDR color)
layout(binding = 0, rgba16f) uniform writeonly image2D outColor;

// 3D Volumetric atmospheric voxel texture (R: liquid water, G: vapor, B: Temp, A: Pressure)
layout(binding = 1) uniform sampler3D uAtmosphereVoxel;

// Simulation & camera uniform buffer
layout(binding = 2, std140) uniform UBO {
    vec4 sunDirection;          // xyz = unit vector to sun, w = unused
    vec4 sunColorPAR;           // rgb = incident color, w = PPFD
    vec4 sunColorNIR;           // rgb = NIR color, w = NIR flux
    vec4 cameraPos;             // xyz = eye position
    mat4 invView;               // Inverse view matrix
    mat4 invProj;               // Inverse projection matrix
    float planetRadius;
    float atmosphereRadius;
    float henyeyGreensteinG;    // Asymmetry parameter (0.75 for clouds)
    float raymarchStepSize;
    float magnetopauseRadius;
    float solarWindSpeed;
    float auroralIntensity;
    float elapsedTime;
} ubo;

// Henyey-Greenstein phase function for realistic forward Mie scattering of solar photons
float henyeyGreenstein(float cosTheta, float g) {
    float g2 = g * g;
    float denom = 1.0 + g2 - 2.0 * g * cosTheta;
    return (1.0 / (4.0 * 3.14159265)) * ((1.0 - g2) / pow(max(denom, 0.0001), 1.5));
}

// Ray-box intersection for chunk voxel bounds
bool intersectBox(vec3 ro, vec3 rd, vec3 boxMin, vec3 boxMax, out float tNear, out float tFar) {
    vec3 invD = 1.0 / rd;
    vec3 t0 = (boxMin - ro) * invD;
    vec3 t1 = (boxMax - ro) * invD;
    vec3 tSmall = min(t0, t1);
    vec3 tBig = max(t0, t1);
    tNear = max(max(tSmall.x, tSmall.y), tSmall.z);
    tFar = min(min(tBig.x, tBig.y), tBig.z);
    return tNear <= tFar && tFar > 0.0;
}

// Sample cloud water density in world-space coordinates
float sampleCloudDensity(vec3 p, vec3 boxMin, vec3 boxMax) {
    vec3 uvw = (p - boxMin) / (boxMax - boxMin);
    if (any(lessThan(uvw, vec3(0.0))) || any(greaterThan(uvw, vec3(1.0)))) {
        return 0.0;
    }
    // R channel = cloud liquid water content (g/m^3)
    vec4 atmoSample = texture(uAtmosphereVoxel, uvw);
    return atmoSample.r;
}

void main() {
    ivec2 pixelCoord = ivec2(gl_GlobalInvocationID.xy);
    ivec2 screenSize = imageSize(outColor);
    if (pixelCoord.x >= screenSize.x || pixelCoord.y >= screenSize.y) {
        return;
    }

    // Normalized Device Coordinates (-1.0 to 1.0)
    vec2 uv = (vec2(pixelCoord) + 0.5) / vec2(screenSize);
    vec2 ndc = uv * 2.0 - 1.0;

    // Reconstruct camera view ray
    vec4 target = ubo.invProj * vec4(ndc.x, ndc.y, 1.0, 1.0);
    vec3 rayDir = normalize((ubo.invView * vec4(target.xyz / target.w, 0.0)).xyz);
    vec3 rayOrigin = ubo.cameraPos.xyz;

    // Chunk world boundaries (16x8x16 chunks * 2m scale = 32m x 16m x 32m)
    vec3 boxMin = vec3(0.0, 0.0, 0.0);
    vec3 boxMax = vec3(32.0, 16.0, 32.0);

    float tNear, tFar;
    if (!intersectBox(rayOrigin, rayDir, boxMin, boxMax, tNear, tFar)) {
        // Background sky model: Rayleigh gradient
        float sunCos = dot(rayDir, normalize(ubo.sunDirection.xyz));
        vec3 skyColor = mix(vec3(0.25, 0.45, 0.85), vec3(0.65, 0.75, 0.95), max(rayDir.y, 0.0));
        vec3 sunDisk = ubo.sunColorPAR.rgb * pow(max(sunCos, 0.0), 256.0) * 5.0;
        imageStore(outColor, pixelCoord, vec4(skyColor + sunDisk, 1.0));
        return;
    }

    tNear = max(tNear, 0.0);

    // Volumetric raymarching setup
    float stepSize = max(ubo.raymarchStepSize, 0.25);
    float t = tNear;
    vec3 accumColor = vec3(0.0);
    float transmittance = 1.0;

    float cosAngle = dot(rayDir, normalize(ubo.sunDirection.xyz));
    float phase = henyeyGreenstein(cosAngle, ubo.henyeyGreensteinG);

    // March through the atmospheric voxel grid
    while (t < tFar && transmittance > 0.01) {
        vec3 p = rayOrigin + rayDir * t;
        float density = sampleCloudDensity(p, boxMin, boxMax);

        if (density > 0.001) {
            // Secondary light ray towards the sun to compute optical depth / cloud shadows
            float lightStep = 0.5;
            float lightOpticalDepth = 0.0;
            vec3 lightPos = p;
            vec3 sunDir = normalize(ubo.sunDirection.xyz);

            for (int s = 0; s < 6; ++s) {
                lightPos += sunDir * lightStep;
                lightOpticalDepth += sampleCloudDensity(lightPos, boxMin, boxMax) * lightStep;
            }

            // Beer-Lambert light attenuation from direct solar beam
            float lightTransmittance = exp(-lightOpticalDepth * 1.5);
            vec3 sunLight = ubo.sunColorPAR.rgb * lightTransmittance;

            // Ambient skylight term
            vec3 ambientLight = vec3(0.2, 0.3, 0.5) * 0.4;

            // Total in-scattered radiance
            vec3 S = (sunLight * phase + ambientLight) * density;

            // Integration along view ray
            float stepOpticalDepth = density * stepSize * 1.5;
            float stepTransmittance = exp(-stepOpticalDepth);

            accumColor += transmittance * (S - S * stepTransmittance);
            transmittance *= stepTransmittance;
        }

        t += stepSize;
    }

    // Blend with atmospheric background sky
    vec3 skyColor = mix(vec3(0.25, 0.45, 0.85), vec3(0.65, 0.75, 0.95), max(rayDir.y, 0.0));
    vec3 finalColor = accumColor + skyColor * transmittance;

    imageStore(outColor, pixelCoord, vec4(finalColor, 1.0));
}
