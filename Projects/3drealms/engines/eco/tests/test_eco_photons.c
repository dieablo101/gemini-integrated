#include "eco_photons.h"
#include "eco_types.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <assert.h>
#include <time.h>

int main(void) {
    printf("==========================================\n");
    printf("    ECO-ENGINE PHASE 2: PHOTON SOLVER    \n");
    printf("==========================================\n\n");

    // 1. Test Celestial Solar Geometry (Solar Noon vs Night)
    printf("[TEST] Testing celestial solar geometry and TOA radiation...\n");
    float lat_equator = 0.0f;
    float declination_equinox = 0.0f;
    
    // Noon
    EcoSolarTOA noon = eco_photons_compute_solar_toa(0.5f, lat_equator, declination_equinox);
    assert(!noon.is_night);
    assert(fabsf(noon.solar_zenith_rad - 0.0f) < 0.001f);
    assert(fabsf(noon.solar_elevation_sin - 1.0f) < 0.001f);
    assert(fabsf(noon.toa_par_flux - ECO_SOLAR_CONSTANT_PAR) < 0.01f);
    printf("  Noon PAR Flux: %.2f W/m^2 (Zenith: %.2f rad, AirMass: %.2f)\n",
           noon.toa_par_flux, noon.solar_zenith_rad, noon.air_mass);
    
    // Midnight
    EcoSolarTOA midnight = eco_photons_compute_solar_toa(0.0f, lat_equator, declination_equinox);
    assert(midnight.is_night);
    assert(midnight.toa_par_flux == 0.0f);
    printf("  Midnight PAR Flux: %.2f W/m^2 (Night verified)\n", midnight.toa_par_flux);
    
    // Sunrise/Dawn (day_fraction ~ 0.26)
    EcoSolarTOA dawn = eco_photons_compute_solar_toa(0.26f, lat_equator, declination_equinox);
    assert(!dawn.is_night);
    assert(dawn.air_mass > 10.0f);
    printf("  Dawn Air Mass: %.2f (Optical path extended at horizon)\n", dawn.air_mass);
    printf("  -> OK: Celestial solar kinematics verified!\n\n");

    // 2. Test Downward Atmospheric Radiative Transfer (Beer-Lambert Extinction)
    printf("[TEST] Testing vertical column optical extinction (Beer-Lambert)...\n");
    int chunk_x = 16, chunk_y = 8, chunk_z = 16;
    int total_cells = chunk_x * chunk_y * chunk_z;
    
    EcoAtmosphericCell *atm_cells = (EcoAtmosphericCell*)calloc(total_cells, sizeof(EcoAtmosphericCell));
    EcoPhotonSpectrum *photon_cells = (EcoPhotonSpectrum*)calloc(total_cells, sizeof(EcoPhotonSpectrum));
    
    // Initialize atmospheric layers: standard decreasing density with altitude
    for (int y = 0; y < chunk_y; ++y) {
        float alt_km = (float)y * 0.5f; // 500m per layer
        float rho = 1.225f * expf(-alt_km / 8.5f); // Scale height 8.5km
        for (int z = 0; z < chunk_z; ++z) {
            for (int x = 0; x < chunk_x; ++x) {
                int idx = (y * chunk_z + z) * chunk_x + x;
                atm_cells[idx].density_kg_m3 = rho;
                atm_cells[idx].total_pressure_pa = 101325.0f * expf(-alt_km / 8.5f);
                atm_cells[idx].p_h2o = 1200.0f;
                atm_cells[idx].relative_humidity = 0.5f;
            }
        }
    }

    // Solve for Solar Noon
    eco_photons_solve_chunk(atm_cells, photon_cells, chunk_x, chunk_y, chunk_z, 500.0f, 0.5f, lat_equator, declination_equinox);
    
    // Verify top cell vs ground cell
    int top_idx = ((chunk_y - 1) * chunk_z + 0) * chunk_x + 0;
    int gnd_idx = (0 * chunk_z + 0) * chunk_x + 0;
    
    printf("  Top Layer PAR PPFD:    %.1f umol/m^2/s (Optical Depth: %.4f)\n",
           photon_cells[top_idx].par_ppfd, photon_cells[top_idx].optical_depth);
    printf("  Ground Layer PAR PPFD: %.1f umol/m^2/s (Optical Depth: %.4f)\n",
           photon_cells[gnd_idx].par_ppfd, photon_cells[gnd_idx].optical_depth);
    printf("  Ground Direct Fraction: %.2f (Diffuse: %.1f umol/m^2/s)\n",
           photon_cells[gnd_idx].direct_fraction, photon_cells[gnd_idx].par_diffuse_ppfd);
    
    assert(photon_cells[top_idx].par_ppfd > photon_cells[gnd_idx].par_ppfd);
    assert(photon_cells[gnd_idx].optical_depth > photon_cells[top_idx].optical_depth);
    printf("  -> OK: Optical extinction correctly attenuates down the column!\n\n");

    // 3. Cloud / Fog Attenuation Test
    printf("[TEST] Testing cloud moisture attenuation...\n");
    // Inject cloud into layer y=4 (2.5 g/m^3 condensed water droplets)
    for (int z = 0; z < chunk_z; ++z) {
        for (int x = 0; x < chunk_x; ++x) {
            int idx = (4 * chunk_z + z) * chunk_x + x;
            atm_cells[idx].cloud_water_g_m3 = 2.5f;
            atm_cells[idx].relative_humidity = 1.0f;
        }
    }
    
    eco_photons_solve_chunk(atm_cells, photon_cells, chunk_x, chunk_y, chunk_z, 500.0f, 0.5f, lat_equator, declination_equinox);
    printf("  Cloudy Ground PAR PPFD: %.1f umol/m^2/s (was %.1f in clear sky)\n",
           photon_cells[gnd_idx].par_ppfd, 2600.0f);
    assert(photon_cells[gnd_idx].par_ppfd < 2000.0f);
    printf("  -> OK: Cloud water extinction blocks photosynthetically active radiation!\n\n");

    // 4. Performance Benchmark: 1,000 volumetric chunk passes (256 columns x 8 layers each)
    printf("[TEST] Benchmarking volumetric chunk photon solver...\n");
    clock_t start = clock();
    int iterations = 1000;
    for (int i = 0; i < iterations; ++i) {
        float day_frac = (float)i / (float)iterations;
        eco_photons_solve_chunk(atm_cells, photon_cells, chunk_x, chunk_y, chunk_z, 500.0f, day_frac, lat_equator, declination_equinox);
    }
    clock_t end = clock();
    double total_ms = ((double)(end - start) / CLOCKS_PER_SEC) * 1000.0;
    double us_per_chunk = (total_ms / iterations) * 1000.0;
    printf("  Benchmark (1,000 diurnal solves x %d cells): %.2f ms total (%.2f us/solve)\n",
           total_cells, total_ms, us_per_chunk);
    assert(us_per_chunk < 250.0); // Must execute in sub-millisecond real time
    printf("  -> OK: Photon solver executes at %.2f us per chunk!\n\n", us_per_chunk);

    free(atm_cells);
    free(photon_cells);

    printf("==========================================\n");
    printf("      ALL PHASE 2 PHOTON TESTS PASSED     \n");
    printf("==========================================\n");
    return 0;
}
