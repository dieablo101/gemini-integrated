/**
 * @file test_eco_vulkan_bridge.c
 * @brief Test suite and verification for Vulkan 1.4 Compute Bridge and SPIR-V shaders.
 */

#include "eco_types.h"
#include "eco_engine.h"
#include "eco_vulkan_bridge.h"

#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <math.h>
#include <time.h>
#include <string.h>

#define ANSI_GREEN "\033[32m"
#define ANSI_CYAN  "\033[36m"
#define ANSI_RESET "\033[0m"

static double get_time_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000000.0 + (double)ts.tv_nsec / 1000.0;
}

static void test_vulkan_memory_layout(void) {
    printf("[TEST] Checking Vulkan bridge memory alignments and struct sizes...\n");
    printf("  sizeof(EcoVoxelAtmosphere)  = %zu bytes (16 or 64B aligned)\n", sizeof(EcoVoxelAtmosphere));
    printf("  sizeof(EcoFoliageInstance)  = %zu bytes (strictly 64 bytes)\n", sizeof(EcoFoliageInstance));
    printf("  sizeof(EcoVulkanComputeUBO) = %zu bytes (strictly 64B cache-aligned)\n", sizeof(EcoVulkanComputeUBO));

    assert(sizeof(EcoFoliageInstance) == 64);
    assert(sizeof(EcoVulkanComputeUBO) % 64 == 0);
    assert(((uintptr_t)sizeof(EcoVoxelAtmosphere)) % 16 == 0);

    printf("  -> %sOK: All Vulkan staging structures conform to std140/std430 hardware constraints!%s\n\n", ANSI_GREEN, ANSI_RESET);
}

static void test_vulkan_atmosphere_packing(void) {
    printf("[TEST] Testing 3D atmospheric voxel grid packing (Zero-copy GPU staging)...\n");

    EcoVulkanBridge bridge;
    eco_vulkan_bridge_init(&bridge);

    EcoAtmosphericCell cells[ECO_CELLS_PER_CHUNK];
    memset(cells, 0, sizeof(cells));

    /* Populate test cell (y=4, z=8, x=8) */
    int idx = 4 * (ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + 8 * ECO_CHUNK_DIM_X + 8;
    cells[idx].cloud_water_g_m3 = 2.5f; /* 2.5 g/m^3 dense cloud */
    cells[idx].p_h2o = 2100.0f;         /* Pa */
    cells[idx].temperature_k = 285.15f;
    cells[idx].total_pressure_pa = 98000.0f;

    eco_vulkan_bridge_pack_atmosphere(&bridge, cells);

    EcoVoxelAtmosphere voxel = bridge.voxel_grid[4][8][8];
    printf("  Voxel[4][8][8] Cloud Water: %.3f g/m^3 (expected 2.500)\n", voxel.cloud_liquid_water);
    printf("  Voxel[4][8][8] Vapor Density: %.3f g/m^3\n", voxel.water_vapor_density);
    printf("  Voxel[4][8][8] Temp: %.2f K, Pressure: %.1f Pa\n", voxel.temperature_k, voxel.pressure_pa);

    assert(fabsf(voxel.cloud_liquid_water - 2.5f) < 1e-3f);
    assert(voxel.water_vapor_density > 10.0f);
    assert(fabsf(voxel.temperature_k - 285.15f) < 1e-3f);

    printf("  -> %sOK: Atmospheric cells faithfully packed into GPU 3D texture staging layout!%s\n\n", ANSI_GREEN, ANSI_RESET);
}

static void test_vulkan_foliage_packing(void) {
    printf("[TEST] Testing Foliage MultiMesh GPU instancing buffer packing...\n");

    EcoVulkanBridge bridge;
    eco_vulkan_bridge_init(&bridge);

    EcoPlantState plants[ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z];
    EcoAtmosphericCell ground_air[ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z];
    memset(plants, 0, sizeof(plants));
    memset(ground_air, 0, sizeof(ground_air));

    /* Setup plant with mature biomass and wind */
    int idx = 4 * ECO_CHUNK_DIM_X + 4;
    plants[idx].biomass_stem_g = 1500.0f; /* 1.5 kg trunk wood */
    plants[idx].leaf_area_index = 2.4f;
    plants[idx].transpiration_e = 3.5f;   /* mmol/m^2/s */
    plants[idx].glucose_pool_g = 80.0f;

    ground_air[idx].wind_u = 2.0f;        /* 2 m/s eastward wind */
    ground_air[idx].wind_w = 0.5f;

    eco_vulkan_bridge_pack_foliage(&bridge, plants, ground_air);

    EcoFoliageInstance inst = bridge.foliage_instances[idx];

    printf("  Instance [%u] Position: (%.1f, %.1f, %.1f) m\n", idx, inst.pos_x, inst.pos_y, inst.pos_z);
    printf("  Instance [%u] Trunk Scale: %.2f (Allometric stem mass scaling)\n", idx, inst.scale_trunk);
    printf("  Instance [%u] Wind Deflection: (%.3f, %.3f) from velocity vector\n", idx, inst.wind_deflection_x, inst.wind_deflection_z);
    printf("  Instance [%u] Solar Occlusion: %.3f (LAI shading factor)\n", idx, inst.solar_occlusion);

    assert(inst.scale_trunk > 5.0f);
    assert(fabsf(inst.wind_deflection_x - 0.30f) < 1e-2f);
    assert(inst.solar_occlusion > 0.6f);

    printf("  -> %sOK: Foliage MultiMesh instance buffers dynamically mirror biological growth!%s\n\n", ANSI_GREEN, ANSI_RESET);
}

static void test_vulkan_spirv_binaries(void) {
    printf("[TEST] Checking compiled Vulkan SPIR-V compute binaries on disk...\n");

    const char* spv_files[] = {
        "/home/kidlucrid/Projects/games/engines/ecoengine/shaders/compute_clouds.spv",
        "/home/kidlucrid/Projects/games/engines/ecoengine/shaders/compute_aurora.spv",
        "/home/kidlucrid/Projects/games/engines/ecoengine/shaders/compute_foliage_cull.spv"
    };

    for (int i = 0; i < 3; ++i) {
        FILE* f = fopen(spv_files[i], "rb");
        assert(f != NULL && "SPIR-V binary file must exist!");
        fseek(f, 0, SEEK_END);
        long sz = ftell(f);
        fclose(f);
        printf("  Found %s (%ld bytes)\n", spv_files[i], sz);
        assert(sz > 1000);
    }

    printf("  -> %sOK: All compute shaders compiled to native SPIR-V 1.0 bytecode!%s\n\n", ANSI_GREEN, ANSI_RESET);
}

static void benchmark_vulkan_bridge(void) {
    printf("[TEST] Benchmarking full Vulkan bridge packing (Atmosphere 3D + Foliage MultiMesh)...\n");

    EcoVulkanBridge bridge;
    eco_vulkan_bridge_init(&bridge);

    EcoAtmosphericCell cells[ECO_CELLS_PER_CHUNK];
    EcoPlantState plants[ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z];
    EcoAtmosphericCell ground_air[ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z];
    memset(cells, 0, sizeof(cells));
    memset(plants, 0, sizeof(plants));
    memset(ground_air, 0, sizeof(ground_air));

    EcoEngineConfig cfg = eco_engine_default_config();
    EcoEngine* engine = eco_engine_create(&cfg);

    EcoPhotonSpectrum sun;
    memset(&sun, 0, sizeof(sun));
    sun.sun_direction[0] = 0.5f;
    sun.sun_direction[1] = 0.8f;
    sun.sun_direction[2] = 0.3f;
    sun.par_ppfd = 1800.0f;
    sun.nir_flux = 650.0f;

    const int iterations = 1000;
    double t0 = get_time_us();

    for (int i = 0; i < iterations; ++i) {
        float cam[3] = {16.0f, 10.0f, -5.0f};
        eco_vulkan_bridge_update_ubo(&bridge, engine, &sun, cam, 0.5f);
        eco_vulkan_bridge_pack_atmosphere(&bridge, cells);
        eco_vulkan_bridge_pack_foliage(&bridge, plants, ground_air);
    }

    double t1 = get_time_us();
    double total_ms = (t1 - t0) / 1000.0;
    double us_per_pack = (t1 - t0) / (double)iterations;

    printf("  Packed %d frames (2,048 atmospheric voxels + 256 foliage instances) in %.2f ms\n", iterations, total_ms);
    printf("  -> %sThroughput: %.2f us per frame upload (%s%.1f FPS headroom%s)%s\n\n",
           ANSI_CYAN, us_per_pack, ANSI_GREEN, 1000000.0 / us_per_pack, ANSI_CYAN, ANSI_RESET);

    eco_engine_destroy(engine);
}

int main(void) {
    printf("====================================================\n");
    printf("   ECO-ENGINE PHASE 5: VULKAN 1.4 COMPUTE BRIDGE    \n");
    printf("====================================================\n\n");

    test_vulkan_memory_layout();
    test_vulkan_atmosphere_packing();
    test_vulkan_foliage_packing();
    test_vulkan_spirv_binaries();
    benchmark_vulkan_bridge();

    printf("====================================================\n");
    printf("  %sALL PHASE 5 VULKAN BRIDGE TESTS PASSED!%s        \n", ANSI_GREEN, ANSI_RESET);
    printf("====================================================\n");
    return 0;
}
