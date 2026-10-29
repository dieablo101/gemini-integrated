/**
 * ECO-ENGINE: Water & Atmospheric Shm Bridge Implementation
 * engines/ecoengine/src/eco_water_bridge.c
 */

#include "eco_water_bridge.h"
#include "eco_atmosphere.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>

static uint32_t s_bridge_sequence = 0;
static uint32_t s_rng_seed = 1337;

static float next_random_float(void) {
    s_rng_seed = s_rng_seed * 1664525u + 1013904223u;
    return (float)(s_rng_seed & 0x00FFFFFF) / (float)0x01000000;
}

int eco_water_bridge_init(void) {
    /* Verify /dev/shm or /tmp is accessible */
    FILE* f = fopen(ECO_SHM_TELEMETRY_PATH, "wb");
    if (!f) {
        return -1;
    }
    EcoWaterTelemetry dummy;
    memset(&dummy, 0, sizeof(dummy));
    dummy.magic = ECO_SHM_MAGIC;
    fwrite(&dummy, sizeof(dummy), 1, f);
    fclose(f);
    return 0;
}

void eco_water_bridge_update(EcoEngine* engine, float basin_x, float basin_z, float basin_radius) {
    if (!engine || engine->active_chunk_count == 0) {
        return;
    }

    EcoChunk* chunk = &engine->chunks[0];
    if (!chunk->is_active) {
        return;
    }

    EcoWaterTelemetry telem;
    memset(&telem, 0, sizeof(telem));

    telem.magic = ECO_SHM_MAGIC;
    telem.sequence = ++s_bridge_sequence;
    telem.sim_time = (float)engine->sim_time_sec;

    /* Compute diurnal solar angles */
    float cycle_sec = engine->config.day_night_cycle_sec > 0.0f ? engine->config.day_night_cycle_sec : 1200.0f;
    float day_fraction = fmodf((float)engine->sim_time_sec, cycle_sec) / cycle_sec;
    telem.sun_elevation = sinf(day_fraction * 2.0f * (float)M_PI - (float)M_PI * 0.5f);
    telem.sun_azimuth = day_fraction * 2.0f * (float)M_PI;

    /* Sample atmospheric ground cells (y = 0) */
    float sum_temp_k = 0.0f;
    float sum_press = 0.0f;
    float sum_vapor = 0.0f;
    float sum_cloud = 0.0f;
    float sum_wind_u = 0.0f;
    float sum_wind_w = 0.0f;
    float sum_par = 0.0f;
    float sum_nir = 0.0f;
    float sum_soil = 0.0f;
    float sum_precip = 0.0f;
    float sum_aurora = 0.0f;
    float sum_lai = 0.0f;
    float sum_assim = 0.0f;
    float sum_transp = 0.0f;
    float sum_biomass = 0.0f;
    float sum_canopy = 0.0f;

    int ground_cells = ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z;

    for (int z = 0; z < ECO_CHUNK_DIM_Z; z++) {
        for (int x = 0; x < ECO_CHUNK_DIM_X; x++) {
            int idx = z * (ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Y) + 0 * ECO_CHUNK_DIM_X + x;
            EcoAtmosphericCell* cell = &chunk->atmosphere[idx];
            EcoPhotonSpectrum* phot = &chunk->photons[idx];
            EcoMagneticCell* mag = &chunk->magnetics[idx];
            EcoPlantState* plant = &chunk->plants[idx];

            sum_temp_k  += cell->temperature_k;
            sum_press   += cell->total_pressure_pa;
            sum_vapor   += cell->p_h2o;
            sum_cloud   += cell->cloud_water_g_m3;
            sum_wind_u  += cell->wind_u;
            sum_wind_w  += cell->wind_w;
            sum_precip  += cell->precip_rate_mm_h;

            sum_par     += phot->par_ppfd;
            sum_nir     += phot->nir_flux;
            sum_soil    += plant->root_zone_moisture;
            sum_aurora  += mag->auroral_ionization;

            sum_lai     += plant->leaf_area_index;
            sum_assim   += plant->net_assimilation_a;
            sum_transp  += plant->transpiration_e;
            sum_biomass += (plant->biomass_leaf_g + plant->biomass_stem_g + plant->biomass_root_g) * 0.001f;
            sum_canopy  += plant->canopy_height_m;
        }
    }

    float inv_cells = 1.0f / (float)ground_cells;
    float avg_temp_k = sum_temp_k * inv_cells;
    float avg_press = sum_press * inv_cells;
    float avg_vapor = sum_vapor * inv_cells;
    float avg_cloud = sum_cloud * inv_cells;

    telem.temperature_c = avg_temp_k - 273.15f;
    telem.pressure_pa = avg_press;

    /* Compute Relative Humidity: vapor / saturation vapor pressure */
    float t_c = telem.temperature_c;
    float sat_vapor_pa = 610.78f * expf((17.27f * t_c) / (t_c + 237.3f));
    telem.relative_humidity = fminf(1.0f, fmaxf(0.05f, avg_vapor / sat_vapor_pa));

    telem.wind_vector_x = sum_wind_u * inv_cells;
    telem.wind_vector_z = sum_wind_w * inv_cells;
    telem.wind_speed = sqrtf(telem.wind_vector_x * telem.wind_vector_x + telem.wind_vector_z * telem.wind_vector_z);
    
    /* Wind shear stress factor tau for Vulkan compute water: tau = (U^2) / 64.0 */
    telem.wind_shear_stress = fminf(1.0f, fmaxf(0.02f, (telem.wind_speed * telem.wind_speed) / 64.0f));

    telem.solar_flux_par = sum_par * inv_cells;
    telem.solar_flux_nir = sum_nir * inv_cells;
    telem.soil_moisture  = sum_soil * inv_cells;
    telem.auroral_intensity = fminf(1.0f, sum_aurora * inv_cells);

    /* Phase 4 Botanical Biophysical Averages */
    telem.plant_lai          = sum_lai * inv_cells;
    telem.plant_net_assim    = sum_assim * inv_cells;
    telem.plant_transpiration= sum_transp * inv_cells;
    telem.plant_biomass_kg   = sum_biomass * inv_cells;
    telem.plant_canopy_height= sum_canopy * inv_cells;

    /* Cloud cover normalized from liquid water density (0 to 5 g/m^3) */
    telem.cloud_cover = fminf(1.0f, avg_cloud / 5.0f);

    /* Rain precipitation rate in mm/hour */
    telem.rain_rate_mmph = sum_precip * inv_cells;

    /* Generate raindrop splashes inside the water basin */
    telem.rain_splash_count = 0;
    if (telem.rain_rate_mmph > 0.05f || avg_cloud > 2.0f) {
        /* Number of splashes scales with rain rate */
        int num_drops = (int)(telem.rain_rate_mmph * 0.8f);
        if (num_drops < 1 && avg_cloud > 2.5f) num_drops = 2;
        if (num_drops > ECO_MAX_RAIN_SPLASHES) num_drops = ECO_MAX_RAIN_SPLASHES;

        telem.rain_splash_count = (uint32_t)num_drops;
        for (int i = 0; i < num_drops; i++) {
            float r_angle = next_random_float() * 2.0f * (float)M_PI;
            float r_dist = sqrtf(next_random_float()) * basin_radius;
            telem.rain_splashes[i].x = basin_x + cosf(r_angle) * r_dist;
            telem.rain_splashes[i].z = basin_z + sinf(r_angle) * r_dist;
            telem.rain_splashes[i].radius = 0.25f + next_random_float() * 0.35f;
            telem.rain_splashes[i].force = 0.6f + next_random_float() * 1.4f;
        }
    }

    /* Write atomically to shared memory file */
    FILE* f = fopen(ECO_SHM_TELEMETRY_PATH, "wb");
    if (f) {
        fwrite(&telem, sizeof(telem), 1, f);
        fflush(f);
        fclose(f);
    }
}

void eco_water_bridge_read_feedback(EcoWaterFeedback* out_feedback) {
    if (!out_feedback) return;
    FILE* f = fopen(ECO_SHM_FEEDBACK_PATH, "rb");
    if (f) {
        EcoWaterFeedback fb;
        if (fread(&fb, sizeof(fb), 1, f) == 1 && fb.magic == ECO_SHM_MAGIC) {
            *out_feedback = fb;
        }
        fclose(f);
    }
}
