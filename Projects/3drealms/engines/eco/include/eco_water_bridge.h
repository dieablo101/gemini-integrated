/**
 * ECO-ENGINE: Water & Atmospheric Shm Bridge
 * engines/ecoengine/include/eco_water_bridge.h
 *
 * Ultra-fast zero-latency shared memory ring buffer between C EcoEngine
 * and Godot / PhotonWater compute simulation.
 */

#ifndef ECO_WATER_BRIDGE_H
#define ECO_WATER_BRIDGE_H

#include "eco_types.h"
#include "eco_engine.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ECO_SHM_TELEMETRY_PATH "/dev/shm/eco_telemetry.bin"
#define ECO_SHM_FEEDBACK_PATH  "/dev/shm/eco_feedback.bin"
#define ECO_SHM_MAGIC          0x45434F31 /* "ECO1" */
#define ECO_MAX_RAIN_SPLASHES  16

typedef struct EcoRainSplash {
    float x;      /* World X */
    float z;      /* World Z */
    float radius; /* Splash ripple radius */
    float force;  /* Splash impulse amplitude */
} EcoRainSplash;

typedef struct EcoWaterTelemetry {
    uint32_t        magic;                /* ECO_SHM_MAGIC */
    uint32_t        sequence;             /* Monotonic frame sequence */
    float           sim_time;             /* Simulation time (seconds) */
    float           sun_elevation;        /* Angle above horizon (-PI/2 to PI/2) */
    float           sun_azimuth;          /* Solar azimuth angle */
    float           solar_flux_par;       /* Photosynthetically Active Radiation */
    float           solar_flux_nir;       /* Near-Infrared heating flux */
    float           temperature_c;        /* Celsius */
    float           pressure_pa;          /* Barometric pressure */
    float           relative_humidity;    /* 0.0 to 1.0 */
    float           wind_vector_x;        /* East/West wind (m/s) */
    float           wind_vector_z;        /* North/South wind (m/s) */
    float           wind_speed;           /* Total horizontal speed (m/s) */
    float           wind_shear_stress;    /* 0.0 to 1.0 for Vulkan water compute */
    float           cloud_cover;          /* 0.0 to 1.0 */
    float           rain_rate_mmph;       /* Rain precipitation rate (mm/h) */
    float           auroral_intensity;    /* 0.0 to 1.0 */
    float           soil_moisture;        /* 0.0 to 1.0 */
    float           plant_lai;            /* Average Leaf Area Index (0.0 to 8.0) */
    float           plant_net_assim;      /* Net CO2 assimilation (umol / m^2 / s) */
    float           plant_transpiration;  /* Transpiration flux (mmol H2O / m^2 / s) */
    float           plant_biomass_kg;     /* Total dry biomass per parcel (kg) */
    float           plant_canopy_height;  /* Canopy height (meters) */
    uint32_t        rain_splash_count;    /* Number of rain drops this frame */
    EcoRainSplash   rain_splashes[ECO_MAX_RAIN_SPLASHES];
} EcoWaterTelemetry;

typedef struct EcoWaterFeedback {
    uint32_t magic;                       /* ECO_SHM_MAGIC */
    float    basin_evaporation_flux;      /* Water basin evaporation rate (kg/s) */
    int32_t  weather_override;            /* -1=auto, 0=calm, 1=breeze, 2=storm */
} EcoWaterFeedback;

/**
 * Initializes the shared memory bridge state.
 */
int eco_water_bridge_init(void);

/**
 * Samples the ecoengine chunk state around a water basin and writes telemetry to shm.
 */
void eco_water_bridge_update(EcoEngine* engine, float basin_x, float basin_z, float basin_radius);

/**
 * Reads feedback from the game (evaporation, weather overrides) if present.
 */
void eco_water_bridge_read_feedback(EcoWaterFeedback* out_feedback);

#ifdef __cplusplus
}
#endif

#endif /* ECO_WATER_BRIDGE_H */
