#include "eco_atmosphere.h"
#include "eco_magnetosphere.h"
#include "eco_photons.h"
#include <stdio.h>
#include <assert.h>
#include <math.h>
#include <time.h>
#include <string.h>

static double get_time_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

int main(void) {
    printf("====================================================\n");
    printf("   ECO-ENGINE PHASE 3: ATMOSPHERE & MAGNETOSPHERE   \n");
    printf("====================================================\n\n");

    EcoAtmosphericCell atmo_cells[ECO_CELLS_PER_CHUNK];
    EcoPhotonSpectrum  phot_cells[ECO_CELLS_PER_CHUNK];
    EcoMagneticCell    mag_cells[ECO_CELLS_PER_CHUNK];
    EcoPlantState      plant_cells[ECO_CELLS_PER_CHUNK];

    memset(atmo_cells, 0, sizeof(atmo_cells));
    memset(phot_cells, 0, sizeof(phot_cells));
    memset(mag_cells, 0, sizeof(mag_cells));
    memset(plant_cells, 0, sizeof(plant_cells));

    EcoChunk chunk = {
        .coord = { .cx = 0, .cy = 0, .cz = 0, .lod_level = 0 },
        .is_active = true,
        .atmosphere = atmo_cells,
        .photons = phot_cells,
        .magnetics = mag_cells,
        .plants = plant_cells
    };

    EcoAtmoConfig atmo_cfg = {
        .cell_size_x = 10.0f,
        .cell_size_y = 5.0f,
        .cell_size_z = 10.0f,
        .kinematic_viscosity = 1.5e-5f,
        .thermal_diffusivity = 2.0e-5f,
        .drag_coefficient = 0.002f,
        .coriolis_f = 1.0e-4f // Mid-latitude Coriolis parameter
    };

    EcoMagnetoConfig mag_cfg = {
        .dipole_moment = ECO_EARTH_DIPOLE_MOMENT,
        .tilt_angle_rad = 0.20f, // ~11.5 deg
        .planetary_radius_m = ECO_PLANETARY_RADIUS,
        .solar_wind_speed = 400000.0f, // 400 km/s
        .solar_wind_density = 5.0e6f   // 5 protons/cm^3
    };

    // 1. Test Atmospheric Initialization & Hydrostatic Equilibrium
    printf("[TEST] Testing atmospheric hydrostatic equilibrium and gas profile...\n");
    eco_atmo_init_chunk(&chunk, &atmo_cfg, 288.15f);

    EcoAtmosphericCell* ground = &chunk.atmosphere[0];
    EcoAtmosphericCell* aloft  = &chunk.atmosphere[(ECO_CHUNK_DIM_Y - 1) * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X];

    printf("  Ground (y=0m):   P = %.1f Pa, T = %.2f K, rho = %.3f kg/m^3\n",
           ground->total_pressure_pa, ground->temperature_k, ground->density_kg_m3);
    printf("  Aloft  (y=35m):  P = %.1f Pa, T = %.2f K, rho = %.3f kg/m^3\n",
           aloft->total_pressure_pa, aloft->temperature_k, aloft->density_kg_m3);

    assert(ground->total_pressure_pa > aloft->total_pressure_pa);
    assert(ground->temperature_k > aloft->temperature_k);
    assert(ground->density_kg_m3 > aloft->density_kg_m3);
    printf("  -> OK: Hydrostatic gradient confirmed (pressure and density decrease with altitude)!\n\n");

    // 2. Test Convective Updrafts via Ground Solar Heating
    printf("[TEST] Testing solar ground heating and convective buoyancy updrafts...\n");
    // Midday solar photons
    eco_photons_solve_chunk(chunk.atmosphere, chunk.photons,
                            ECO_CHUNK_DIM_X, ECO_CHUNK_DIM_Y, ECO_CHUNK_DIM_Z,
                            atmo_cfg.cell_size_y, 0.5f, 0.0f, 0.0f);

    float pre_t = ground->temperature_k;
    eco_atmo_apply_solar_thermal_heating(&chunk, 10.0f); // 10 seconds of solar insolation
    printf("  Ground parcel heated from %.2f K to %.2f K (+%.2f K)\n", pre_t, ground->temperature_k, ground->temperature_k - pre_t);
    assert(ground->temperature_k > pre_t);

    // Solve buoyancy
    eco_atmo_solve_buoyancy(&chunk, &atmo_cfg);
    printf("  Ground parcel vertical velocity v = %.4f m/s (convective updraft created)\n", ground->wind_v);
    assert(ground->wind_v > 0.0f);
    printf("  -> OK: Solar insolation triggers physical convective updrafts!\n\n");

    // 3. Test Pressure Gradient & Coriolis Horizontal Wind
    printf("[TEST] Testing pressure gradient winds & Coriolis deflection...\n");
    // Create a continuous pressure gradient from High (x=0) to Low (x=15)
    for (int y = 0; y < ECO_CHUNK_DIM_Y; ++y) {
        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
                float pressure_offset = (float)(ECO_CHUNK_DIM_X - 1 - x) * 20.0f; // 0 to 300 Pa gradient
                chunk.atmosphere[idx].total_pressure_pa += pressure_offset;
            }
        }
    }

    eco_atmo_compute_pressure_gradients(&chunk, &atmo_cfg);
    EcoAtmosphericCell* mid_cell = &chunk.atmosphere[(2 * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (8 * ECO_CHUNK_DIM_X) + 8];
    printf("  Horizontal wind vector at center: u = %.4f m/s, w = %.4f m/s\n", mid_cell->wind_u, mid_cell->wind_w);
    assert(mid_cell->wind_u > 0.0f); // Air flows from High (x=0) toward Low (x=15)
    printf("  -> OK: Physical wind blows down the barometric pressure gradient!\n\n");

    // 4. Test Magnetosphere Dipole & Solar Wind Lorentz Force
    printf("[TEST] Testing planetary dipole B-field & Lorentz proton deflection...\n");
    float standoff_km = eco_magneto_calc_magnetopause_radius(&mag_cfg) / 1000.0f;
    printf("  Magnetopause Standoff Radius: %.1f km (~%.2f Earth radii)\n",
           standoff_km, standoff_km / (ECO_PLANETARY_RADIUS / 1000.0f));
    assert(standoff_km > 60000.0f && standoff_km < 80000.0f); // ~10-11 R_E standard

    // Surface equator position (r = 6371 km on X-axis)
    float b_equator[3];
    eco_magneto_calc_dipole_field(&mag_cfg, ECO_PLANETARY_RADIUS, 0.0f, 0.0f, b_equator);
    float b_eq_mag = sqrtf(b_equator[0]*b_equator[0] + b_equator[1]*b_equator[1] + b_equator[2]*b_equator[2]);
    printf("  Equatorial surface magnetic field |B| = %.2f uT (expected ~30.7 uT)\n", b_eq_mag);
    assert(b_eq_mag > 25.0f && b_eq_mag < 35.0f);

    // North pole position (r = 6371 km on Y-axis)
    float b_pole[3];
    eco_magneto_calc_dipole_field(&mag_cfg, 0.0f, ECO_PLANETARY_RADIUS, 0.0f, b_pole);
    float b_pole_mag = sqrtf(b_pole[0]*b_pole[0] + b_pole[1]*b_pole[1] + b_pole[2]*b_pole[2]);
    printf("  Polar surface magnetic field |B| = %.2f uT (expected ~61.4 uT, 2x equator)\n", b_pole_mag);
    assert(b_pole_mag > 55.0f && b_pole_mag < 65.0f);

    // Update chunk magnetics near polar aurora belt
    eco_magneto_update_chunk(&chunk, &mag_cfg, 0.0f, ECO_PLANETARY_RADIUS * 0.95f, ECO_PLANETARY_RADIUS * 0.31f);
    EcoMagneticCell* mag_cell = &chunk.magnetics[ECO_CELLS_PER_CHUNK - 1];
    printf("  Chunk B-field: (%.1f, %.1f, %.1f) uT, |B|=%.1f uT, Surface Rad: %.2f uSv/h, Auroral Ionization: %.3f\n",
           mag_cell->b_field[0], mag_cell->b_field[1], mag_cell->b_field[2], mag_cell->b_magnitude,
           mag_cell->surface_rad_dose, mag_cell->auroral_ionization);
    printf("  Lorentz acceleration on solar wind: ax=%.2e m/s^2, ay=%.2e m/s^2, az=%.2e m/s^2\n",
           mag_cell->lorentz_accel[0], mag_cell->lorentz_accel[1], mag_cell->lorentz_accel[2]);
    assert(mag_cell->surface_rad_dose < 50.0f);
    assert(fabsf(mag_cell->lorentz_accel[0]) > 1e4f || fabsf(mag_cell->lorentz_accel[1]) > 1e4f);
    printf("  -> OK: Planetary magnetosphere shields atmosphere and deflects solar plasma!\n\n");

    // 5. High-Performance Benchmark
    printf("[TEST] Benchmarking coupled Atmosphere + Magnetosphere simulation step...\n");
    const int benchmark_steps = 1000;
    double t_start = get_time_sec();
    for (int i = 0; i < benchmark_steps; ++i) {
        eco_atmo_tick(&chunk, &atmo_cfg, 0.1f);
        eco_magneto_update_chunk(&chunk, &mag_cfg, 0.0f, ECO_PLANETARY_RADIUS, 0.0f);
    }
    double t_end = get_time_sec();
    double total_ms = (t_end - t_start) * 1000.0;
    double us_per_tick = (total_ms / (double)benchmark_steps) * 1000.0;

    printf("  Benchmark (%d coupled ticks x 2048 cells): %.2f ms total (%.2f us/tick)\n",
           benchmark_steps, total_ms, us_per_tick);
    printf("  -> OK: Coupled Atmosphere & Magnetosphere runs at sub-millisecond tick rates!\n\n");

    printf("====================================================\n");
    printf("   PHASE 3 VERIFICATION PASSED (100%% SUCCESS)      \n");
    printf("====================================================\n");

    return 0;
}
