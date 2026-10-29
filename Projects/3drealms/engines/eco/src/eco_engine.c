/**
 * ECO-ENGINE: Master Public Engine Implementation
 * engines/ecoengine/src/eco_engine.c
 */

#include "eco_engine.h"
#include "eco_photosynthesis.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifndef M_PI
    #define M_PI 3.14159265358979323846
#endif

EcoEngineConfig eco_engine_default_config(void) {
    EcoEngineConfig cfg;
    cfg.arena_capacity_bytes    = 64 * 1024 * 1024; /* 64 MB baseline */
    cfg.max_active_chunks       = 32;               /* 32 chunks = ~65,536 volumetric cells */
    cfg.planetary_magnetic_flux = 45.0f;            /* 45 uT (Earth mid-latitudes) */
    cfg.solar_constant_w_m2     = 1361.0f;          /* Standard solar constant */
    cfg.day_night_cycle_sec     = 1200.0f;          /* 20 minutes in-game day/night */
    return cfg;
}

EcoEngine* eco_engine_create(const EcoEngineConfig* config) {
    EcoEngineConfig cfg = config ? *config : eco_engine_default_config();

    EcoEngine* engine = (EcoEngine*)calloc(1, sizeof(EcoEngine));
    if (!engine) {
        return NULL;
    }

    engine->config = cfg;
    if (!eco_arena_init(&engine->arena, cfg.arena_capacity_bytes)) {
        free(engine);
        return NULL;
    }

    engine->chunks = (EcoChunk*)eco_arena_alloc_zero(&engine->arena, cfg.max_active_chunks, sizeof(EcoChunk));
    if (!engine->chunks) {
        eco_arena_destroy(&engine->arena);
        free(engine);
        return NULL;
    }

    engine->active_chunk_count = 0;
    engine->sim_time_sec = 0.0;
    engine->tick_count = 0;

    return engine;
}

void eco_engine_destroy(EcoEngine* engine) {
    if (!engine) return;
    eco_arena_destroy(&engine->arena);
    free(engine);
}

void eco_cell_compute_thermodynamics(EcoAtmosphericCell* cell) {
    if (!cell) return;

    /* Dalton's Law of Partial Pressures */
    cell->total_pressure_pa = cell->p_n2 + cell->p_o2 + cell->p_co2 + cell->p_h2o + ECO_REF_P_ARGON_PA;

    /* Ensure temperature is strictly above absolute zero */
    if (cell->temperature_k < 1.0f) {
        cell->temperature_k = 1.0f;
    }

    /* Dry air gas constant & density: rho = P / (R_spec * T) */
    cell->density_kg_m3 = cell->total_pressure_pa / (ECO_SPECIFIC_GAS_DRY_AIR * cell->temperature_k);

    /* Saturation Vapor Pressure via Tetens Equation (Pa) */
    float temp_c = cell->temperature_k - 273.15f;
    float es_pa = 610.78f * expf((17.27f * temp_c) / (temp_c + 237.3f));

    if (es_pa > 0.0f) {
        cell->relative_humidity = cell->p_h2o / es_pa;
        if (cell->relative_humidity > 1.5f) cell->relative_humidity = 1.5f; /* Supersaturation bound */
        if (cell->relative_humidity < 0.0f) cell->relative_humidity = 0.0f;
    } else {
        cell->relative_humidity = 0.0f;
    }

    /* Magnus-Tetens Dew Point approximation */
    float a = 17.27f;
    float b = 237.3f;
    float alpha = ((a * temp_c) / (b + temp_c)) + logf(fmaxf(cell->relative_humidity, 0.001f));
    cell->dew_point_k = (b * alpha / (a - alpha)) + 273.15f;
}

static void init_chunk_cells(EcoEngine* engine, EcoChunk* chunk) {
    size_t n = ECO_CELLS_PER_CHUNK;

    chunk->atmosphere = (EcoAtmosphericCell*)eco_arena_alloc_zero(&engine->arena, n, sizeof(EcoAtmosphericCell));
    chunk->photons    = (EcoPhotonSpectrum*) eco_arena_alloc_zero(&engine->arena, n, sizeof(EcoPhotonSpectrum));
    chunk->magnetics  = (EcoMagneticCell*)   eco_arena_alloc_zero(&engine->arena, n, sizeof(EcoMagneticCell));
    chunk->plants     = (EcoPlantState*)      eco_arena_alloc_zero(&engine->arena, n, sizeof(EcoPlantState));

    if (!chunk->atmosphere || !chunk->photons || !chunk->magnetics || !chunk->plants) {
        chunk->is_active = false;
        return;
    }

    /* Seed physical defaults into every cell */
    for (size_t i = 0; i < n; ++i) {
        /* Atmospheric Baselines */
        chunk->atmosphere[i].p_n2           = ECO_REF_P_N2_PA;
        chunk->atmosphere[i].p_o2           = ECO_REF_P_O2_PA;
        chunk->atmosphere[i].p_co2          = ECO_REF_P_CO2_PA;
        chunk->atmosphere[i].p_h2o          = ECO_REF_P_H2O_PA;
        chunk->atmosphere[i].temperature_k  = ECO_REF_TEMPERATURE_K;
        eco_cell_compute_thermodynamics(&chunk->atmosphere[i]);

        /* Magnetic Baselines */
        chunk->magnetics[i].b_field[0]        = 0.0f;
        chunk->magnetics[i].b_field[1]        = engine->config.planetary_magnetic_flux * 0.8f;
        chunk->magnetics[i].b_field[2]        = engine->config.planetary_magnetic_flux * 0.6f;
        chunk->magnetics[i].b_magnitude       = engine->config.planetary_magnetic_flux;
        chunk->magnetics[i].solar_wind_speed  = 400.0f; /* 400 km/s quiet solar wind */
        chunk->magnetics[i].proton_density_cm3= 5.0f;

        /* Photon Radiation Baselines */
        chunk->photons[i].par_ppfd            = 800.0f; /* Noon sunlight PPFD */
        chunk->photons[i].uv_flux             = 35.0f;
        chunk->photons[i].nir_flux            = 450.0f;
        chunk->photons[i].direct_fraction     = 0.85f;
        chunk->photons[i].sun_direction[0]    = 0.0f;
        chunk->photons[i].sun_direction[1]    = 1.0f;
        chunk->photons[i].sun_direction[2]    = 0.0f;

        /* Plant Botanical Baselines */
        chunk->plants[i].plant_species_id     = (uint32_t)(i % 4);
        chunk->plants[i].leaf_area_index      = 2.5f;   /* Temperate forest canopy */
        chunk->plants[i].canopy_height_m      = 12.0f;
        chunk->plants[i].foliage_cover        = 0.75f;
        chunk->plants[i].stomatal_conduct     = 0.25f;  /* mol * m^-2 * s^-1 */
        chunk->plants[i].rubisco_vcmax        = 65.0f;  /* umol * m^-2 * s^-1 */
        chunk->plants[i].glucose_pool_g       = 150.0f;
        chunk->plants[i].biomass_leaf_g       = 450.0f;
        chunk->plants[i].biomass_stem_g       = 1200.0f;
        chunk->plants[i].biomass_root_g       = 800.0f;
        chunk->plants[i].water_stress         = 0.05f;
        chunk->plants[i].root_zone_moisture   = 0.35f;  /* Volumetric soil moisture */
    }

    chunk->is_active = true;
}

EcoChunk* eco_engine_get_or_create_chunk(EcoEngine* engine, int32_t cx, int32_t cy, int32_t cz, int32_t lod) {
    if (!engine) return NULL;

    /* Check if already allocated */
    for (uint32_t i = 0; i < engine->active_chunk_count; ++i) {
        if (engine->chunks[i].is_active &&
            engine->chunks[i].coord.cx == cx &&
            engine->chunks[i].coord.cy == cy &&
            engine->chunks[i].coord.cz == cz &&
            engine->chunks[i].coord.lod_level == lod) {
            return &engine->chunks[i];
        }
    }

    if (engine->active_chunk_count >= engine->config.max_active_chunks) {
        /* Max active chunks reached */
        return NULL;
    }

    EcoChunk* chunk = &engine->chunks[engine->active_chunk_count++];
    chunk->coord.cx = cx;
    chunk->coord.cy = cy;
    chunk->coord.cz = cz;
    chunk->coord.lod_level = lod;

    init_chunk_cells(engine, chunk);
    return chunk;
}

void eco_engine_tick(EcoEngine* engine, float delta_time_sec) {
    if (!engine || delta_time_sec <= 0.0f) return;

    engine->sim_time_sec += delta_time_sec;
    engine->tick_count++;

    /* Diurnal cycle calculation */
    double day_fraction = fmod(engine->sim_time_sec, (double)engine->config.day_night_cycle_sec) / (double)engine->config.day_night_cycle_sec;
    float solar_elevation = sinf((float)(day_fraction * 2.0 * M_PI));
    float is_day = solar_elevation > 0.0f ? 1.0f : 0.0f;

    /* Compute active chunks */
    for (uint32_t c = 0; c < engine->active_chunk_count; ++c) {
        EcoChunk* chunk = &engine->chunks[c];
        if (!chunk->is_active) continue;

        for (size_t i = 0; i < ECO_CELLS_PER_CHUNK; ++i) {
            EcoPhotonSpectrum*  photons = &chunk->photons[i];
            EcoAtmosphericCell* atmo    = &chunk->atmosphere[i];

            /* 1. Photon Radiation Step */
            photons->solar_zenith_rad = acosf(fmaxf(0.0f, solar_elevation));
            photons->par_ppfd = is_day * 1200.0f * fmaxf(0.0f, solar_elevation);

            /* 2. Thermodynamic & Molecular Gas Step */
            eco_cell_compute_thermodynamics(atmo);
        }

        /* 3. Phase 4 Farquhar-von Caemmerer-Berry Photosynthesis & Biomass Engine */
        eco_simulate_chunk_photosynthesis(chunk, delta_time_sec);
    }
}
