/**
 * ECO-ENGINE: Biophysical Farquhar Photosynthesis & Plant Biomass Engine
 * engines/ecoengine/src/eco_photosynthesis.c
 *
 * Implements the Farquhar-von Caemmerer-Berry (FvCB) coupled with
 * Ball-Berry stomatal conductance, transpiration, and dynamic biomass partitioning.
 */

#include "eco_photosynthesis.h"
#include <math.h>
#include <string.h>

#define ECO_R_J_MOL_K 8.314462618f

EcoSpeciesParams eco_get_species_params(EcoSpeciesType type) {
    EcoSpeciesParams p;
    memset(&p, 0, sizeof(p));

    switch (type) {
        case ECO_SPECIES_TEMPERATE_TREE:
            p.vcmax_25          = 65.0f;   /* umol / m^2 / s */
            p.jmax_25           = 130.0f;  /* 2.0 * vcmax */
            p.rd_25             = 1.1f;    /* Day respiration */
            p.theta_j           = 0.85f;   /* Light curvature */
            p.quantum_yield     = 0.28f;   /* alpha */
            p.ball_berry_g0     = 0.010f;  /* Min conductance */
            p.ball_berry_g1     = 9.5f;    /* Stomatal slope */
            p.soil_wilt_point   = 0.10f;   /* 10% volumetric moisture */
            p.soil_field_cap    = 0.35f;   /* 35% volumetric moisture */
            p.sla               = 18.0f;   /* m^2 leaf / kg dry matter */
            p.stem_wood_density = 550.0f;  /* kg / m^3 */
            p.is_c4             = false;
            break;

        case ECO_SPECIES_CONIFER:
            p.vcmax_25          = 45.0f;
            p.jmax_25           = 85.0f;
            p.rd_25             = 0.8f;
            p.theta_j           = 0.90f;
            p.quantum_yield     = 0.24f;
            p.ball_berry_g0     = 0.005f;
            p.ball_berry_g1     = 6.5f;    /* More conservative stomata */
            p.soil_wilt_point   = 0.08f;
            p.soil_field_cap    = 0.30f;
            p.sla               = 8.5f;    /* Dense needles */
            p.stem_wood_density = 480.0f;
            p.is_c4             = false;
            break;

        case ECO_SPECIES_C3_GRASS:
            p.vcmax_25          = 80.0f;
            p.jmax_25           = 160.0f;
            p.rd_25             = 1.4f;
            p.theta_j           = 0.80f;
            p.quantum_yield     = 0.30f;
            p.ball_berry_g0     = 0.015f;
            p.ball_berry_g1     = 11.0f;   /* High water transpiration */
            p.soil_wilt_point   = 0.09f;
            p.soil_field_cap    = 0.32f;
            p.sla               = 26.0f;   /* High leaf area per mass */
            p.stem_wood_density = 250.0f;
            p.is_c4             = false;
            break;

        case ECO_SPECIES_C4_GRASS:
            p.vcmax_25          = 50.0f;
            p.jmax_25           = 180.0f;
            p.rd_25             = 0.9f;
            p.theta_j           = 0.75f;
            p.quantum_yield     = 0.32f;
            p.ball_berry_g0     = 0.020f;
            p.ball_berry_g1     = 4.5f;    /* High water-use efficiency */
            p.soil_wilt_point   = 0.06f;   /* Drought resilient */
            p.soil_field_cap    = 0.28f;
            p.sla               = 22.0f;
            p.stem_wood_density = 300.0f;
            p.is_c4             = true;
            break;

        default:
            return eco_get_species_params(ECO_SPECIES_TEMPERATE_TREE);
    }

    return p;
}

float eco_arrhenius_temp_response(float param_25, float ha_j_mol, float temp_k) {
    if (temp_k <= 250.0f || temp_k >= 340.0f) {
        return 0.0f; /* Enzymes denatured by freezing or extreme heat */
    }
    const float t_ref = 298.15f; /* 25 deg C */
    float exponent = (ha_j_mol / (ECO_R_J_MOL_K * t_ref)) * (1.0f - (t_ref / temp_k));
    if (exponent > 15.0f) exponent = 15.0f;
    if (exponent < -15.0f) exponent = -15.0f;
    return param_25 * expf(exponent);
}

void eco_rubisco_kinetics(
    float temp_k,
    bool is_c4,
    float *out_kc_pa,
    float *out_ko_pa,
    float *out_gamma_star_pa
) {
    if (is_c4) {
        /* C4 plants concentrate CO2 internally via PEP carboxylase, reducing photorespiration to near zero */
        *out_kc_pa = 65.0f;
        *out_ko_pa = 40000.0f;
        *out_gamma_star_pa = 0.5f;
        return;
    }

    /* Standard C3 Arrhenius kinetic constants */
    /* Kc (CO2 affinity): 40.4 Pa at 25C, Ha = 79430 J/mol */
    *out_kc_pa = eco_arrhenius_temp_response(40.4f, 79430.0f, temp_k);

    /* Ko (O2 affinity): 27840 Pa at 25C, Ha = 36380 J/mol */
    *out_ko_pa = eco_arrhenius_temp_response(27840.0f, 36380.0f, temp_k);

    /* Gamma* (Compensation point): 4.275 Pa at 25C, Ha = 37830 J/mol */
    *out_gamma_star_pa = eco_arrhenius_temp_response(4.275f, 37830.0f, temp_k);
}

float eco_electron_transport_rate(
    float par_ppfd,
    float jmax,
    float alpha,
    float theta
) {
    if (par_ppfd <= 0.0f || jmax <= 0.0f) {
        return 0.0f;
    }

    /* Solves theta * J^2 - (alpha * I + Jmax) * J + alpha * I * Jmax = 0 */
    float i_eff = alpha * par_ppfd;
    float b = i_eff + jmax;
    float disc = b * b - 4.0f * theta * i_eff * jmax;
    if (disc < 0.0f) disc = 0.0f;

    return (b - sqrtf(disc)) / (2.0f * theta);
}

void eco_solve_photosynthesis(
    const EcoSpeciesParams *params,
    float par_ppfd,
    float temp_k,
    float ca_pa,
    float rel_humidity,
    float total_pressure_pa,
    float soil_moisture,
    EcoPlantState *plant
) {
    if (ca_pa < 5.0f) ca_pa = 5.0f;
    if (total_pressure_pa < 50000.0f) total_pressure_pa = 101325.0f;

    /* 1. Soil water stress calculation */
    float f_water = 1.0f;
    if (soil_moisture <= params->soil_wilt_point) {
        f_water = 0.01f; /* Near wilting point */
    } else if (soil_moisture < params->soil_field_cap) {
        f_water = (soil_moisture - params->soil_wilt_point) / (params->soil_field_cap - params->soil_wilt_point);
        if (f_water < 0.01f) f_water = 0.01f;
        if (f_water > 1.0f) f_water = 1.0f;
    }
    plant->water_stress = 1.0f - f_water;
    plant->root_zone_moisture = soil_moisture;

    /* 2. Temperature inhibition factor */
    float t_opt = params->is_c4 ? 306.15f : 298.15f; /* 33C for C4, 25C for C3 */
    float t_diff = fabsf(temp_k - t_opt);
    float t_factor = 1.0f / (1.0f + 0.003f * t_diff * t_diff);
    if (temp_k < 273.15f) {
        t_factor *= fmaxf(0.0f, (temp_k - 268.15f) / 5.0f); /* Freezing inhibition */
    }
    plant->thermal_stress = 1.0f - t_factor;

    /* 3. Enzyme kinetic capacities scaled by temperature and water stress */
    float vcmax = params->vcmax_25 * t_factor * f_water;
    float jmax  = params->jmax_25  * t_factor * f_water;
    float rd    = params->rd_25    * t_factor;

    plant->rubisco_vcmax = vcmax;

    /* 4. Electron transport rate J */
    float j_rate = eco_electron_transport_rate(par_ppfd, jmax, params->quantum_yield, params->theta_j);
    plant->electron_transport_j = j_rate;

    /* 5. Rubisco kinetics */
    float kc_pa, ko_pa, gamma_star_pa;
    eco_rubisco_kinetics(temp_k, params->is_c4, &kc_pa, &ko_pa, &gamma_star_pa);

    float oi_pa = 20946.0f; /* 20.9% atmospheric O2 */
    float km_pa = kc_pa * (1.0f + oi_pa / ko_pa);

    /* If darkness / night */
    if (par_ppfd < 1.0f || vcmax < 0.1f) {
        plant->net_assimilation_a = -rd;
        plant->stomatal_conduct = params->ball_berry_g0;
        plant->transpiration_e = 0.05f;
        return;
    }

    /* 6. Intercellular CO2 (Ci) and Stomatal Conductance (gs) mutual iteration */
    /* CO2 in ppm: Ca_ppm = (Ca_Pa / P_tot) * 1e6 */
    float ca_ppm = (ca_pa / total_pressure_pa) * 1e6f;
    if (ca_ppm < 50.0f) ca_ppm = 50.0f;

    /* Initial estimate: Ci / Ca ratio */
    float ci_ratio = params->is_c4 ? 0.40f : 0.70f;
    float ci_pa = ca_pa * ci_ratio;

    float an = 0.0f;
    float gs = params->ball_berry_g0;

    for (int iter = 0; iter < 4; ++iter) {
        if (ci_pa < gamma_star_pa + 0.1f) ci_pa = gamma_star_pa + 0.1f;

        /* Rubisco-limited carboxylation Wc */
        float wc = vcmax * (ci_pa - gamma_star_pa) / (ci_pa + km_pa);

        /* RuBP regeneration-limited carboxylation Wj */
        float wj = 0.0f;
        if (params->is_c4) {
            wj = j_rate * 0.5f;
        } else {
            wj = (j_rate / 4.0f) * (ci_pa - gamma_star_pa) / (ci_pa + 2.0f * gamma_star_pa);
        }

        /* Gross assimilation is minimum of limiting steps */
        float a_gross = fminf(wc, wj);
        if (a_gross < 0.0f) a_gross = 0.0f;

        an = a_gross - rd;

        /* Ball-Berry stomatal conductance: gs = g0 + g1 * (An * RH / Ca_ppm) */
        float rh_clamped = fmaxf(0.15f, fminf(rel_humidity, 1.0f));

        if (an > 0.0f) {
            gs = params->ball_berry_g0 + params->ball_berry_g1 * (an * rh_clamped / ca_ppm) * f_water;
        } else {
            gs = params->ball_berry_g0;
        }
        if (gs < params->ball_berry_g0) gs = params->ball_berry_g0;
        if (gs > 1.2f) gs = 1.2f;

        /* Fick's first law of diffusion: An = (gs / 1.6) * (Ca - Ci) / P_tot
         * => Delta Ci_Pa = (An * 1e-6 * P_tot) / (gs / 1.6) */
        float g_co2 = fmaxf(gs / 1.6f, 0.002f);
        float delta_ci_pa = (an * 1e-6f * total_pressure_pa) / g_co2;
        ci_pa = ca_pa - delta_ci_pa;
    }

    plant->net_assimilation_a = an;
    plant->stomatal_conduct = gs;

    /* 7. Transpiration water loss (mmol H2O * m^-2 * s^-1) */
    /* Vapor Pressure Deficit (VPD in Pa) */
    /* Tetens saturation formula */
    float t_c = temp_k - 273.15f;
    float e_sat_pa = 610.78f * expf((17.27f * t_c) / (t_c + 237.3f));
    float vpd_pa = fmaxf(0.0f, e_sat_pa * (1.0f - rel_humidity));

    /* E = gs_H2O * (VPD / P_tot) */
    float gs_h2o = gs * 1.6f;
    float transpiration_mol_m2_s = gs_h2o * (vpd_pa / total_pressure_pa);
    plant->transpiration_e = transpiration_mol_m2_s * 1000.0f; /* Convert to mmol */
}

void eco_partition_biomass(
    const EcoSpeciesParams *params,
    EcoPlantState *plant,
    float dt_seconds
) {
    (void)dt_seconds;
    if (plant->glucose_pool_g <= 0.0f) {
        return;
    }

    /* In micro-ticks during active daylight, partition 70% of new photosynthate into structural tissues
     * and retain 30% in mobile non-structural carbohydrate storage pool.
     * In seasonal or batch allocation (large dt or standalone invocation), partition available pool. */
    float carbon_partitioned = plant->glucose_pool_g;
    if (dt_seconds < 1800.0f && plant->net_assimilation_a > 0.0f) {
        float lai_active = fmaxf(plant->leaf_area_index, 0.1f);
        float new_photosynthate_g = plant->net_assimilation_a * 1e-6f * 30.026f * lai_active * dt_seconds;
        carbon_partitioned = fminf(plant->glucose_pool_g, new_photosynthate_g * 0.70f);
    }

    /* Growth respiration consumes ~20% of synthesized glucose */
    float growth_efficiency = 0.80f;
    float available_carbon = carbon_partitioned * growth_efficiency;

    /* Dynamic allocation fractions based on functional equilibrium hypothesis:
     * - Water stress increases root investment
     * - Low light (shading) increases leaf investment
     * - Height competition increases stem/wood investment */
    float f_root = 0.25f + 0.40f * plant->water_stress;
    if (f_root > 0.65f) f_root = 0.65f;

    float light_limitation = fmaxf(0.0f, 1.0f - (plant->electron_transport_j / (params->jmax_25 + 0.1f)));
    float f_leaf = 0.35f * (1.0f - plant->water_stress) + 0.20f * light_limitation;
    if (f_leaf > 0.50f) f_leaf = 0.50f;

    float f_stem = 1.0f - (f_root + f_leaf);
    if (f_stem < 0.10f) {
        f_stem = 0.10f;
        f_leaf = 1.0f - (f_root + f_stem);
    }

    /* Convert glucose to dry biomass */
    float delta_leaf = available_carbon * f_leaf;
    float delta_stem = available_carbon * f_stem;
    float delta_root = available_carbon * f_root;

    plant->biomass_leaf_g += delta_leaf;
    plant->biomass_stem_g += delta_stem;
    plant->biomass_root_g += delta_root;

    /* Deduct partitioned glucose from the mobile pool */
    plant->glucose_pool_g -= carbon_partitioned;

    /* Update architectural structural properties */
    /* Leaf Area Index (LAI) = Leaf Biomass (kg/m^2) * Specific Leaf Area (m^2/kg) */
    float leaf_kg_m2 = plant->biomass_leaf_g * 0.001f;
    plant->leaf_area_index = leaf_kg_m2 * params->sla;
    if (plant->leaf_area_index > 8.0f) plant->leaf_area_index = 8.0f; /* Biological saturation */

    /* Canopy crown cover = 1.0 - exp(-k * LAI) */
    plant->foliage_cover = 1.0f - expf(-0.55f * plant->leaf_area_index);

    /* Canopy height from stem allometry (allometric power law: H ~ M_stem^0.38) */
    float stem_kg = plant->biomass_stem_g * 0.001f;
    if (stem_kg > 0.01f) {
        plant->canopy_height_m = 1.2f * powf(stem_kg, 0.38f);
    } else {
        plant->canopy_height_m = 0.1f;
    }
}

void eco_simulate_plant_tick(
    EcoPlantState *plant,
    EcoAtmosphericCell *atmo,
    const EcoPhotonSpectrum *photons,
    float soil_moisture,
    float dt_seconds
) {
    EcoSpeciesParams params = eco_get_species_params((EcoSpeciesType)plant->plant_species_id);

    /* 1. Solve biochemical photosynthesis */
    eco_solve_photosynthesis(
        &params,
        photons->par_ppfd,
        atmo->temperature_k,
        atmo->p_co2,
        atmo->relative_humidity,
        atmo->total_pressure_pa,
        soil_moisture,
        plant
    );

    /* 2. Carbon assimilation into glucose pool
     * An is in umol CO2 / m^2 / s.
     * Molar mass of Glucose (C6H12O6) = 180.156 g / mol.
     * 1 mole Glucose requires 6 moles CO2 -> 30.026 g Glucose / mole CO2.
     * Glucose gained (g) = An * 1e-6 * 30.026 * LAI * dt */
    float lai_active = fmaxf(plant->leaf_area_index, 0.1f);
    float glucose_delta_g = plant->net_assimilation_a * 1e-6f * 30.026f * lai_active * dt_seconds;

    plant->glucose_pool_g += glucose_delta_g;
    if (plant->glucose_pool_g < 0.0f) plant->glucose_pool_g = 0.0f;

    /* 3. Gas exchange with local atmospheric cell (conservation of mass) */
    /* Assume atmospheric cell volume of 2.0m x 2.0m x 5.0m = 20.0 m^3 */
    const float cell_volume_m3 = 20.0f;
    const float ground_area_m2 = 4.0f;

    /* CO2 consumed (moles) = An * 1e-6 * ground_area * LAI * dt */
    float moles_co2_fixed = plant->net_assimilation_a * 1e-6f * ground_area_m2 * lai_active * dt_seconds;
    /* Delta P = n * R * T / V */
    float delta_p_co2 = (moles_co2_fixed * ECO_GAS_CONSTANT_R * atmo->temperature_k) / cell_volume_m3;
    atmo->p_co2 -= delta_p_co2;
    if (atmo->p_co2 < 5.0f) atmo->p_co2 = 5.0f;

    /* O2 produced (equal to moles of CO2 fixed by oxygenic photosynthesis) */
    float delta_p_o2 = delta_p_co2;
    atmo->p_o2 += delta_p_o2;

    /* Transpiration: H2O vapor added to atmospheric parcel */
    /* E is in mmol H2O / m^2 / s -> moles = E * 1e-3 * ground_area * LAI * dt */
    float moles_h2o_transpired = (plant->transpiration_e * 1e-3f) * ground_area_m2 * lai_active * dt_seconds;
    float delta_p_h2o = (moles_h2o_transpired * ECO_GAS_CONSTANT_R * atmo->temperature_k) / cell_volume_m3;
    atmo->p_h2o += delta_p_h2o;

    /* Evaporative cooling of the microclimate parcel from latent heat of vaporization */
    /* Lv ~ 2.45e6 J / kg. Mass H2O = moles * 0.018015 kg */
    float mass_h2o_evap = moles_h2o_transpired * ECO_MOLAR_MASS_H2O;
    float air_mass_kg = atmo->density_kg_m3 * cell_volume_m3;
    if (air_mass_kg > 0.1f) {
        float cooling_j = mass_h2o_evap * 2.45e6f;
        float delta_t = cooling_j / (air_mass_kg * 1005.0f); /* Cp of air ~ 1005 J/(kg*K) */
        atmo->temperature_k -= delta_t;
    }

    /* 4. Allocate biomass */
    eco_partition_biomass(&params, plant, dt_seconds);
}

void eco_simulate_chunk_photosynthesis(
    EcoChunk *chunk,
    float dt_seconds
) {
    if (!chunk) return;

    /* Simulate vegetation on ground layer (y = 0) */
    const int y = 0;
    for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
        for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
            uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
            EcoPlantState *plant = &chunk->plants[idx];
            EcoAtmosphericCell *atmo = &chunk->atmosphere[idx];
            const EcoPhotonSpectrum *photons = &chunk->photons[idx];

            /* Default soil moisture if uninitialized */
            float soil_moisture = plant->root_zone_moisture;
            if (soil_moisture <= 0.001f) {
                soil_moisture = 0.28f; /* 28% volumetric content */
            }

            /* Soil moisture recharged by rainfall */
            if (atmo->precip_rate_mm_h > 0.0f) {
                float rain_m = (atmo->precip_rate_mm_h * 1e-3f / 3600.0f) * dt_seconds;
                soil_moisture += rain_m * 0.5f; /* Infiltration fraction */
                if (soil_moisture > 0.45f) soil_moisture = 0.45f; /* Saturation capacity */
            }

            eco_simulate_plant_tick(plant, atmo, photons, soil_moisture, dt_seconds);

            /* Root uptake depletes soil moisture */
            float water_used_m = (plant->transpiration_e * 1e-3f * 0.018015f / 1000.0f) * dt_seconds;
            soil_moisture -= water_used_m;
            if (soil_moisture < 0.02f) soil_moisture = 0.02f;
            plant->root_zone_moisture = soil_moisture;
        }
    }
}
