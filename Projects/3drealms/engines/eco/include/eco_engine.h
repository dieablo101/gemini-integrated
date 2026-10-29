/**
 * ECO-ENGINE: Master Public Engine Interface
 * engines/ecoengine/include/eco_engine.h
 *
 * Orchestrates physical chunks, biophysical causality pipeline,
 * and high-throughput memory arenas.
 */

#ifndef ECO_ENGINE_H
#define ECO_ENGINE_H

#include "eco_types.h"
#include "eco_arena.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ECO_CHUNK_DIM_X 16
#define ECO_CHUNK_DIM_Y 8
#define ECO_CHUNK_DIM_Z 16
#define ECO_CELLS_PER_CHUNK (ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Y * ECO_CHUNK_DIM_Z)

typedef struct EcoChunk {
    EcoChunkCoord       coord;
    bool                is_active;

    /* 64-byte aligned contiguous cell buffers */
    EcoAtmosphericCell* atmosphere;  /* [ECO_CELLS_PER_CHUNK] */
    EcoPhotonSpectrum*  photons;     /* [ECO_CELLS_PER_CHUNK] */
    EcoMagneticCell*    magnetics;   /* [ECO_CELLS_PER_CHUNK] */
    EcoPlantState*      plants;      /* [ECO_CELLS_PER_CHUNK] */
} EcoChunk;

typedef struct EcoEngineConfig {
    size_t   arena_capacity_bytes;   /* Memory budget (e.g. 64MB - 256MB) */
    uint32_t max_active_chunks;      /* Max simultaneous active chunks */
    float    planetary_magnetic_flux;/* Dipole moment in uT (Earth ~30-60 uT) */
    float    solar_constant_w_m2;    /* Insolation at top of atmosphere (~1361 W/m^2) */
    float    day_night_cycle_sec;    /* Length of full 24h diurnal cycle in seconds */
} EcoEngineConfig;

typedef struct EcoEngine {
    EcoArena            arena;
    EcoEngineConfig     config;
    EcoChunk*           chunks;
    uint32_t            active_chunk_count;
    double              sim_time_sec;
    uint64_t            tick_count;
} EcoEngine;

/**
 * Creates and initializes an EcoEngine instance with preallocated arena memory.
 */
EcoEngine* eco_engine_create(const EcoEngineConfig* config);

/**
 * Destroys an EcoEngine instance and releases all associated resources.
 */
void eco_engine_destroy(EcoEngine* engine);

/**
 * Allocates or re-uses a chunk at the specified chunk coordinates.
 */
EcoChunk* eco_engine_get_or_create_chunk(EcoEngine* engine, int32_t cx, int32_t cy, int32_t cz, int32_t lod);

/**
 * Advances the simulation by delta_time_sec:
 * 1. Solves solar zenith & photon attenuation across cells.
 * 2. Solves gas partial pressures and thermodynamic buoyancy.
 * 3. Deflects charged solar plasma via magnetic Lorentz vector.
 * 4. Runs Farquhar biochemical photosynthesis and plant biomass growth.
 */
void eco_engine_tick(EcoEngine* engine, float delta_time_sec);

/**
 * Computes Dalton total pressure and air density for an atmospheric cell.
 */
void eco_cell_compute_thermodynamics(EcoAtmosphericCell* cell);

/**
 * Default configuration generator with scientifically accurate planetary baselines.
 */
EcoEngineConfig eco_engine_default_config(void);

#ifdef __cplusplus
}
#endif

#endif /* ECO_ENGINE_H */
