/**
 * ECO-ENGINE: Phase 4 Farquhar Photosynthesis & Plant Biomass Test Suite
 * engines/ecoengine/tests/test_eco_photosynthesis.c
 */

#include "eco_photosynthesis.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <assert.h>

static double get_time_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

int main(void) {
    printf("====================================================\n");
    printf("   ECO-ENGINE PHASE 4: FARQUHAR PHOTOSYNTHESIS      \n");
    printf("====================================================\n\n");

    /* TEST 1: Arrhenius & Rubisco Kinetics */
    printf("[TEST] Testing Rubisco kinetics and Arrhenius temperature scaling...\n");
    float kc_15, ko_15, gamma_15;
    float kc_25, ko_25, gamma_25;
    eco_rubisco_kinetics(288.15f, false, &kc_15, &ko_15, &gamma_15); /* 15 C */
    eco_rubisco_kinetics(298.15f, false, &kc_25, &ko_25, &gamma_25); /* 25 C */

    printf("  15C C3 Kinetics: Kc = %.2f Pa, Ko = %.1f Pa, Gamma* = %.3f Pa\n", kc_15, ko_15, gamma_15);
    printf("  25C C3 Kinetics: Kc = %.2f Pa, Ko = %.1f Pa, Gamma* = %.3f Pa\n", kc_25, ko_25, gamma_25);

    assert(kc_25 > kc_15);
    assert(gamma_25 > gamma_15);

    /* C4 comparison */
    float kc_c4, ko_c4, gamma_c4;
    eco_rubisco_kinetics(298.15f, true, &kc_c4, &ko_c4, &gamma_c4);
    printf("  25C C4 Kinetics: Gamma* = %.3f Pa (Photorespiration suppressed)\n", gamma_c4);
    assert(gamma_c4 < 1.0f);
    printf("  -> OK: Kinetic parameters obey Arrhenius temperature laws!\n\n");

    /* TEST 2: Farquhar Light Response Curve */
    printf("[TEST] Testing Farquhar light response curve (Night vs Noon)...\n");
    EcoSpeciesParams oak = eco_get_species_params(ECO_SPECIES_TEMPERATE_TREE);
    EcoPlantState plant_night, plant_low, plant_noon;
    memset(&plant_night, 0, sizeof(plant_night));
    memset(&plant_low, 0, sizeof(plant_low));
    memset(&plant_noon, 0, sizeof(plant_noon));

    /* Night: PPFD = 0 */
    eco_solve_photosynthesis(&oak, 0.0f, 298.15f, 42.0f, 0.65f, 101325.0f, 0.30f, &plant_night);
    printf("  Night (PPFD = 0):     An = %6.2f umol/m^2/s, gs = %.4f mol/m^2/s\n",
           plant_night.net_assimilation_a, plant_night.stomatal_conduct);
    assert(plant_night.net_assimilation_a < 0.0f); /* Dark respiration */

    /* Low light: PPFD = 200 */
    eco_solve_photosynthesis(&oak, 200.0f, 298.15f, 42.0f, 0.65f, 101325.0f, 0.30f, &plant_low);
    printf("  Low Light (PPFD=200): An = %6.2f umol/m^2/s, gs = %.4f mol/m^2/s\n",
           plant_low.net_assimilation_a, plant_low.stomatal_conduct);
    assert(plant_low.net_assimilation_a > 0.0f);

    /* Full Noon: PPFD = 1600 */
    eco_solve_photosynthesis(&oak, 1600.0f, 298.15f, 42.0f, 0.65f, 101325.0f, 0.30f, &plant_noon);
    printf("  Full Sun (PPFD=1600): An = %6.2f umol/m^2/s, gs = %.4f mol/m^2/s, E = %.2f mmol/m^2/s\n",
           plant_noon.net_assimilation_a, plant_noon.stomatal_conduct, plant_noon.transpiration_e);
    assert(plant_noon.net_assimilation_a > plant_low.net_assimilation_a);
    assert(plant_noon.stomatal_conduct > plant_low.stomatal_conduct);
    printf("  -> OK: Photosynthesis responds realistically to photon flux density!\n\n");

    /* TEST 3: Soil Water Stress & Stomatal Throttling */
    printf("[TEST] Testing stomatal response to soil drought...\n");
    EcoPlantState plant_wet, plant_dry;
    memset(&plant_wet, 0, sizeof(plant_wet));
    memset(&plant_dry, 0, sizeof(plant_dry));

    /* Well-watered (moisture = 0.32) */
    eco_solve_photosynthesis(&oak, 1200.0f, 298.15f, 42.0f, 0.60f, 101325.0f, 0.32f, &plant_wet);
    /* Drought (moisture = 0.11 near wilt point 0.10) */
    eco_solve_photosynthesis(&oak, 1200.0f, 298.15f, 42.0f, 0.60f, 101325.0f, 0.11f, &plant_dry);

    printf("  Well-watered: gs = %.4f mol/m^2/s, E = %.2f mmol/m^2/s, WaterStress = %.2f\n",
           plant_wet.stomatal_conduct, plant_wet.transpiration_e, plant_wet.water_stress);
    printf("  Severe drought: gs = %.4f mol/m^2/s, E = %.2f mmol/m^2/s, WaterStress = %.2f\n",
           plant_dry.stomatal_conduct, plant_dry.transpiration_e, plant_dry.water_stress);

    assert(plant_dry.water_stress > 0.8f);
    assert(plant_dry.stomatal_conduct < plant_wet.stomatal_conduct * 0.2f);
    assert(plant_dry.transpiration_e < plant_wet.transpiration_e * 0.25f);
    printf("  -> OK: Stomata throttle transpiration when soil is dry!\n\n");

    /* TEST 4: Dynamic Biomass Allocation */
    printf("[TEST] Testing dynamic carbon & biomass allocation (Roots vs Canopy)...\n");
    EcoPlantState test_plant;
    memset(&test_plant, 0, sizeof(test_plant));
    test_plant.glucose_pool_g = 50.0f; /* 50 grams synthesized glucose */
    test_plant.water_stress = 0.85f;   /* High drought stress */
    eco_partition_biomass(&oak, &test_plant, 3600.0f);

    printf("  Drought allocation: Leaf = %.2f g, Stem = %.2f g, Root = %.2f g, LAI = %.2f\n",
           test_plant.biomass_leaf_g, test_plant.biomass_stem_g, test_plant.biomass_root_g, test_plant.leaf_area_index);
    assert(test_plant.biomass_root_g > test_plant.biomass_leaf_g); /* Roots prioritized during drought */

    /* Reset and test well-watered shading */
    memset(&test_plant, 0, sizeof(test_plant));
    test_plant.glucose_pool_g = 50.0f;
    test_plant.water_stress = 0.0f;
    test_plant.electron_transport_j = 20.0f; /* Shaded */
    eco_partition_biomass(&oak, &test_plant, 3600.0f);

    printf("  Shaded allocation:  Leaf = %.2f g, Stem = %.2f g, Root = %.2f g, LAI = %.2f\n",
           test_plant.biomass_leaf_g, test_plant.biomass_stem_g, test_plant.biomass_root_g, test_plant.leaf_area_index);
    assert(test_plant.biomass_leaf_g > test_plant.biomass_root_g); /* Foliage prioritized during shading */
    printf("  -> OK: Biomass allocation dynamically adapts to environmental limitations!\n\n");

    /* TEST 5: Coupled Plant-Atmosphere Bilateral Gas Exchange */
    printf("[TEST] Testing bilateral atmospheric coupling (CO2 depletion, O2 release, Transpiration cooling)...\n");
    EcoAtmosphericCell atmo;
    memset(&atmo, 0, sizeof(atmo));
    atmo.p_co2 = 42.0f;
    atmo.p_o2 = 20946.0f;
    atmo.p_h2o = 1200.0f;
    atmo.temperature_k = 295.15f;
    atmo.total_pressure_pa = 101325.0f;
    atmo.density_kg_m3 = 1.20f;
    atmo.relative_humidity = 0.50f;

    EcoPhotonSpectrum photons;
    memset(&photons, 0, sizeof(photons));
    photons.par_ppfd = 1200.0f;

    EcoPlantState tree;
    memset(&tree, 0, sizeof(tree));
    tree.leaf_area_index = 3.5f;
    tree.plant_species_id = ECO_SPECIES_TEMPERATE_TREE;

    float init_co2 = atmo.p_co2;
    float init_o2 = atmo.p_o2;
    float init_h2o = atmo.p_h2o;
    float init_temp = atmo.temperature_k;

    /* Simulate 60 seconds of daylight exchange */
    eco_simulate_plant_tick(&tree, &atmo, &photons, 0.30f, 60.0f);

    printf("  Atmosphere before: CO2 = %.4f Pa, O2 = %.4f Pa, H2O = %.4f Pa, T = %.2f K\n",
           init_co2, init_o2, init_h2o, init_temp);
    printf("  Atmosphere after:  CO2 = %.4f Pa, O2 = %.4f Pa, H2O = %.4f Pa, T = %.2f K\n",
           atmo.p_co2, atmo.p_o2, atmo.p_h2o, atmo.temperature_k);

    assert(atmo.p_co2 < init_co2);      /* Plants consume CO2 */
    assert(atmo.p_o2 > init_o2);        /* Plants generate O2 */
    assert(atmo.p_h2o > init_h2o);      /* Transpiration adds water vapor */
    assert(atmo.temperature_k < init_temp); /* Latent heat cooling */
    printf("  -> OK: Bilateral physical coupling verified (CO2-, O2+, H2O+, Evaporative Cooling)!\n\n");

    /* TEST 6: Chunk-Level Vegetation Benchmark */
    printf("[TEST] Benchmarking chunk vegetation simulation (256 plant parcels)...\n");
    EcoChunk chunk;
    memset(&chunk, 0, sizeof(chunk));
    EcoAtmosphericCell atmo_cells[ECO_CELLS_PER_CHUNK];
    EcoPhotonSpectrum photon_cells[ECO_CELLS_PER_CHUNK];
    EcoMagneticCell mag_cells[ECO_CELLS_PER_CHUNK];
    EcoPlantState plant_cells[ECO_CELLS_PER_CHUNK];
    chunk.atmosphere = atmo_cells;
    chunk.photons = photon_cells;
    chunk.magnetics = mag_cells;
    chunk.plants = plant_cells;

    for (int i = 0; i < ECO_CELLS_PER_CHUNK; ++i) {
        chunk.atmosphere[i].p_co2 = 42.0f;
        chunk.atmosphere[i].p_o2 = 20946.0f;
        chunk.atmosphere[i].p_h2o = 1200.0f;
        chunk.atmosphere[i].temperature_k = 293.15f;
        chunk.atmosphere[i].total_pressure_pa = 101325.0f;
        chunk.atmosphere[i].density_kg_m3 = 1.20f;
        chunk.atmosphere[i].relative_humidity = 0.55f;
        chunk.photons[i].par_ppfd = 1000.0f;
        chunk.plants[i].leaf_area_index = 2.5f;
        chunk.plants[i].root_zone_moisture = 0.28f;
        chunk.plants[i].plant_species_id = (i % 4); /* Mix of species */
    }

    const int iterations = 1000;
    double t_start = get_time_seconds();
    for (int iter = 0; iter < iterations; ++iter) {
        eco_simulate_chunk_photosynthesis(&chunk, 1.0f);
    }
    double t_end = get_time_seconds();
    double total_ms = (t_end - t_start) * 1000.0;
    double us_per_tick = (total_ms / iterations) * 1000.0;

    printf("  Benchmark (1,000 chunk ticks x 256 plant parcels): %.2f ms total (%.2f us/tick)\n",
           total_ms, us_per_tick);
    assert(us_per_tick < 500.0);
    printf("  -> OK: Vegetative biophysics executes at %.2f us per chunk!\n\n", us_per_tick);

    printf("====================================================\n");
    printf("   100%% PHASE 4 VERIFICATION SUITE PASSED!         \n");
    printf("====================================================\n");

    return 0;
}
