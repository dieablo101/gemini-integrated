/**
 * ECO-ENGINE: Biophysical Farquhar Photosynthesis & Plant Biomass Engine
 * engines/ecoengine/include/eco_photosynthesis.h
 *
 * Implements the Farquhar-von Caemmerer-Berry (FvCB) C3/C4 biochemical model,
 * Ball-Berry-Leuning stomatal conductance, transpiration water flux,
 * and dynamic carbon/glucose biomass allocation.
 */

#ifndef ECO_PHOTOSYNTHESIS_H
#define ECO_PHOTOSYNTHESIS_H

#include "eco_types.h"
#include "eco_engine.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Species Physiological Parameters */
typedef struct EcoSpeciesParams {
    float vcmax_25;           /* Maximum carboxylation velocity at 25C (umol CO2 * m^-2 * s^-1) */
    float jmax_25;            /* Maximum electron transport rate at 25C (umol e- * m^-2 * s^-1) */
    float rd_25;              /* Day dark respiration rate at 25C (umol CO2 * m^-2 * s^-1) */
    float theta_j;            /* Curvature parameter for light response (typically 0.7 - 0.9) */
    float quantum_yield;      /* Quantum yield of electron transport alpha (mol e- / mol photons) */
    float ball_berry_g0;      /* Minimum stomatal conductance g0 (mol * m^-2 * s^-1) */
    float ball_berry_g1;      /* Stomatal slope parameter g1 (dimensionless, ~8 - 12) */
    float soil_wilt_point;    /* Permanent wilting point (m^3 / m^3, ~0.10) */
    float soil_field_cap;     /* Field capacity moisture (m^3 / m^3, ~0.35) */
    float sla;                /* Specific Leaf Area (m^2 leaf area / kg leaf biomass, ~15.0 - 25.0) */
    float stem_wood_density;  /* kg / m^3 stem biomass (~500.0) */
    bool is_c4;               /* False for C3 (temperate trees), True for C4 (tropical grasses) */
} EcoSpeciesParams;

/* Standard Botanical Species Presets */
typedef enum EcoSpeciesType {
    ECO_SPECIES_TEMPERATE_TREE = 0, /* C3 broadleaf deciduous (Oak, Maple) */
    ECO_SPECIES_CONIFER        = 1, /* C3 evergreen conifer (Pine, Spruce) */
    ECO_SPECIES_C3_GRASS       = 2, /* C3 perennial shrub / grass (Wheat, Rye) */
    ECO_SPECIES_C4_GRASS       = 3, /* C4 high-efficiency tropical grass (Corn, Savannah grass) */
    ECO_SPECIES_COUNT
} EcoSpeciesType;

/**
 * Retrieves botanical parameters for a predefined species type.
 */
EcoSpeciesParams eco_get_species_params(EcoSpeciesType type);

/**
 * Arrhenius temperature response function:
 * Rate(T) = Rate_25 * exp( (Ha / (R * 298.15)) * (1 - 298.15 / T) )
 */
float eco_arrhenius_temp_response(float param_25, float ha_j_mol, float temp_k);

/**
 * Calculates kinetic parameters of Rubisco enzyme at local temperature:
 * Kc (Michaelis constant for CO2), Ko (Michaelis constant for O2),
 * and Gamma* (Photorespiratory CO2 compensation point).
 */
void eco_rubisco_kinetics(
    float temp_k,
    bool is_c4,
    float *out_kc_pa,
    float *out_ko_pa,
    float *out_gamma_star_pa
);

/**
 * Solves the non-rectangular hyperbola for potential electron transport rate J:
 * theta * J^2 - (alpha * PPFD + Jmax) * J + alpha * PPFD * Jmax = 0
 */
float eco_electron_transport_rate(
    float par_ppfd,
    float jmax,
    float alpha,
    float theta
);

/**
 * Computes net carbon assimilation An (umol CO2 * m^-2 * s^-1) using the
 * coupled Farquhar-von Caemmerer-Berry and Ball-Berry stomatal conductance model.
 *
 * Simultaneously balances stomatal opening with vapor pressure deficit and soil water stress.
 */
void eco_solve_photosynthesis(
    const EcoSpeciesParams *params,
    float par_ppfd,
    float temp_k,
    float ca_pa,
    float rel_humidity,
    float total_pressure_pa,
    float soil_moisture,
    EcoPlantState *plant
);

/**
 * Allocates accumulated mobile glucose into structural biomass pools:
 * - Foliage (Leaf Area Index expansion for photon capture)
 * - Stem / Wood (Canopy elevation and structural height)
 * - Root System (Soil water acquisition)
 */
void eco_partition_biomass(
    const EcoSpeciesParams *params,
    EcoPlantState *plant,
    float dt_seconds
);

/**
 * Simulates a single vegetative time-step for a plant parcel coupled with its
 * atmospheric cell and incoming solar photons.
 *
 * Performs bilateral exchange:
 * - Depletes CO2 from air parcel
 * - Generates O2 in air parcel
 * - Transpires H2O vapor into air parcel (cooling and microclimate humidification)
 * - Deposits glucose into plant biomass
 */
void eco_simulate_plant_tick(
    EcoPlantState *plant,
    EcoAtmosphericCell *atmo,
    const EcoPhotonSpectrum *photons,
    float soil_moisture,
    float dt_seconds
);

/**
 * Simulates all botanical parcels across a chunk, applying canopy shading,
 * microclimate transpiration, and root soil moisture depletion.
 */
void eco_simulate_chunk_photosynthesis(
    EcoChunk *chunk,
    float dt_seconds
);

#ifdef __cplusplus
}
#endif

#endif /* ECO_PHOTOSYNTHESIS_H */
