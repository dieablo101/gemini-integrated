#include "eco_atmosphere.h"
#include <math.h>
#include <string.h>

#define CLAMP(v, min_v, max_v) ((v) < (min_v) ? (min_v) : ((v) > (max_v) ? (max_v) : (v)))

void eco_atmo_init_chunk(EcoChunk* chunk, const EcoAtmoConfig* config, float base_temperature_k) {
    if (!chunk || !config || !chunk->atmosphere) return;

    for (int y = 0; y < ECO_CHUNK_DIM_Y; ++y) {
        float alt_m = (float)y * config->cell_size_y;
        // Dry adiabatic lapse rate for vertical temperature profile
        float temp_k = base_temperature_k - (ECO_LAPSE_RATE_DRY * alt_m);
        if (temp_k < 210.0f) temp_k = 210.0f; // Tropopause floor

        // Barometric formula for hydrostatic pressure profile:
        // P(h) = P0 * exp(- g * M * h / (R * T))
        float exponent = - (ECO_GRAVITY_EARTH * alt_m) / (ECO_GAS_CONST_DRY_AIR * temp_k);
        float total_pressure = ECO_STANDARD_SL_PRESSURE * expf(exponent);

        // Density from ideal gas law: rho = P / (R * T)
        float density = total_pressure / (ECO_GAS_CONST_DRY_AIR * temp_k);

        // Standard molecular fractions
        float p_n2  = total_pressure * 0.7808f;
        float p_o2  = total_pressure * 0.2095f;
        float p_co2 = total_pressure * 0.00042f; // ~420 ppm
        float p_h2o = total_pressure * 0.0100f * expf(-alt_m / 2000.0f); // Drops with altitude

        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
                EcoAtmosphericCell* cell = &chunk->atmosphere[idx];

                cell->p_n2              = p_n2;
                cell->p_o2              = p_o2;
                cell->p_co2             = p_co2;
                cell->p_h2o             = p_h2o;
                cell->total_pressure_pa = total_pressure;
                cell->temperature_k     = temp_k;
                cell->density_kg_m3     = density;

                cell->wind_u = 0.0f;
                cell->wind_v = 0.0f;
                cell->wind_w = 0.0f;

                // Saturation vapor pressure (Tetens formula)
                float t_c = temp_k - 273.15f;
                float sat_vp = 610.78f * expf((17.27f * t_c) / (t_c + 237.3f));
                cell->relative_humidity = CLAMP(p_h2o / sat_vp, 0.0f, 1.0f);

                // Dew point (Magnus-Tetens)
                float a = 17.27f;
                float b = 237.3f;
                float alpha = ((a * t_c) / (b + t_c)) + logf(fmaxf(0.01f, cell->relative_humidity));
                cell->dew_point_k = 273.15f + ((b * alpha) / (a - alpha));

                cell->cloud_water_g_m3 = 0.0f;
                cell->precip_rate_mm_h = 0.0f;
            }
        }
    }
}

void eco_atmo_apply_solar_thermal_heating(EcoChunk* chunk, float dt) {
    if (!chunk || !chunk->atmosphere || !chunk->photons || dt <= 0.0f) return;

    // Ground layer (y = 0) receives NIR and shortwave direct flux,
    // converting radiative photon energy into sensible ground heat
    for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
        for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
            uint32_t idx_ground = (0 * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
            EcoAtmosphericCell* atmo = &chunk->atmosphere[idx_ground];
            const EcoPhotonSpectrum* phot = &chunk->photons[idx_ground];

            // Incident shortwave & NIR ground irradiance (W/m^2)
            float total_solar_w_m2 = phot->nir_flux + (phot->par_ppfd * 0.22f); // PAR flux conversion ~0.22 W per umol
            float albedo = 0.20f; // Typical soil/vegetation albedo
            float absorbed_w_m2 = total_solar_w_m2 * (1.0f - albedo);

            // Thermal heating: dT = Q / (rho * Cp * dz)
            float dz = 5.0f; // Ground cell layer thickness
            float heat_cap_layer = atmo->density_kg_m3 * ECO_SPECIFIC_HEAT_CP * dz;
            if (heat_cap_layer > 1.0f) {
                float temp_delta = (absorbed_w_m2 / heat_cap_layer) * dt;
                atmo->temperature_k += temp_delta;
                
                // Thermal expansion: Ideal gas law at near-constant local pressure lowers density
                atmo->density_kg_m3 = atmo->total_pressure_pa / (ECO_GAS_CONST_DRY_AIR * atmo->temperature_k);
            }
        }
    }
}

void eco_atmo_solve_buoyancy(EcoChunk* chunk, const EcoAtmoConfig* config) {
    if (!chunk || !config || !chunk->atmosphere) return;

    for (int y = 0; y < ECO_CHUNK_DIM_Y; ++y) {
        // Compute ambient layer mean temperature
        float sum_t = 0.0f;
        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
                sum_t += chunk->atmosphere[idx].temperature_k;
            }
        }
        float t_ambient = sum_t / (float)(ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z);
        if (t_ambient < 1.0f) t_ambient = 288.15f;

        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
                EcoAtmosphericCell* cell = &chunk->atmosphere[idx];

                // Buoyancy acceleration: a_y = g * (T_cell - T_amb) / T_amb - g * liquid_water_mass
                float thermal_buoyancy = ECO_GRAVITY_EARTH * ((cell->temperature_k - t_ambient) / t_ambient);
                float condensate_drag = ECO_GRAVITY_EARTH * (cell->cloud_water_g_m3 * 0.001f);
                float a_buoyancy = thermal_buoyancy - condensate_drag;

                cell->wind_v += a_buoyancy * 0.05f; // integrate step
                cell->wind_v *= 0.98f; // Aerodynamic drag/damping
            }
        }
    }
}

void eco_atmo_compute_pressure_gradients(EcoChunk* chunk, const EcoAtmoConfig* config) {
    if (!chunk || !config || !chunk->atmosphere) return;

    float inv_dx = 1.0f / (config->cell_size_x * 2.0f);
    float inv_dz = 1.0f / (config->cell_size_z * 2.0f);

    for (int y = 0; y < ECO_CHUNK_DIM_Y; ++y) {
        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
                EcoAtmosphericCell* cell = &chunk->atmosphere[idx];

                // Central difference for horizontal pressure gradient
                int x_prev = (x > 0) ? x - 1 : x;
                int x_next = (x < ECO_CHUNK_DIM_X - 1) ? x + 1 : x;
                int z_prev = (z > 0) ? z - 1 : z;
                int z_next = (z < ECO_CHUNK_DIM_Z - 1) ? z + 1 : z;

                uint32_t idx_xp = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x_prev;
                uint32_t idx_xn = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x_next;
                uint32_t idx_zp = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z_prev * ECO_CHUNK_DIM_X) + x;
                uint32_t idx_zn = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z_next * ECO_CHUNK_DIM_X) + x;

                float dp_dx = (chunk->atmosphere[idx_xn].total_pressure_pa - chunk->atmosphere[idx_xp].total_pressure_pa) * inv_dx;
                float dp_dz = (chunk->atmosphere[idx_zn].total_pressure_pa - chunk->atmosphere[idx_zp].total_pressure_pa) * inv_dz;

                float inv_rho = 1.0f / fmaxf(0.1f, cell->density_kg_m3);

                // Acceleration from pressure gradient: a = - (1 / rho) * grad(P)
                float a_u = - inv_rho * dp_dx;
                float a_w = - inv_rho * dp_dz;

                // Coriolis acceleration: f_coriolis = 2 * Omega * sin(lat)
                // a_cor_x = + f * v_z
                // a_cor_z = - f * v_x
                float a_cor_x = config->coriolis_f * cell->wind_w;
                float a_cor_z = - config->coriolis_f * cell->wind_u;

                cell->wind_u += (a_u + a_cor_x) * 0.05f;
                cell->wind_w += (a_w + a_cor_z) * 0.05f;

                // Damping / ground drag for boundary layer (y == 0)
                if (y == 0) {
                    float drag = 1.0f - (config->drag_coefficient * 5.0f);
                    cell->wind_u *= drag;
                    cell->wind_w *= drag;
                } else {
                    cell->wind_u *= 0.995f;
                    cell->wind_w *= 0.995f;
                }
            }
        }
    }
}

void eco_atmo_advect_scalars(EcoChunk* chunk, const EcoAtmoConfig* config, float dt) {
    if (!chunk || !config || !chunk->atmosphere || dt <= 0.0f) return;

    // Temporary storage buffer for advected scalar fields
    float temp_t[ECO_CELLS_PER_CHUNK];
    float temp_h2o[ECO_CELLS_PER_CHUNK];
    float temp_co2[ECO_CELLS_PER_CHUNK];

    float inv_dx = 1.0f / config->cell_size_x;
    float inv_dy = 1.0f / config->cell_size_y;
    float inv_dz = 1.0f / config->cell_size_z;

    for (int y = 0; y < ECO_CHUNK_DIM_Y; ++y) {
        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
                const EcoAtmosphericCell* cell = &chunk->atmosphere[idx];

                // Trace back velocity vector to find source position (Semi-Lagrangian backwards trace)
                float back_x = (float)x - (cell->wind_u * dt * inv_dx);
                float back_y = (float)y - (cell->wind_v * dt * inv_dy);
                float back_z = (float)z - (cell->wind_w * dt * inv_dz);

                // Clamp to chunk boundaries
                int src_x = CLAMP((int)roundf(back_x), 0, ECO_CHUNK_DIM_X - 1);
                int src_y = CLAMP((int)roundf(back_y), 0, ECO_CHUNK_DIM_Y - 1);
                int src_z = CLAMP((int)roundf(back_z), 0, ECO_CHUNK_DIM_Z - 1);

                uint32_t src_idx = (src_y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (src_z * ECO_CHUNK_DIM_X) + src_x;

                temp_t[idx]   = chunk->atmosphere[src_idx].temperature_k;
                temp_h2o[idx] = chunk->atmosphere[src_idx].p_h2o;
                temp_co2[idx] = chunk->atmosphere[src_idx].p_co2;
            }
        }
    }

    // Write back advected state and solve phase changes (condensation / clouds)
    for (uint32_t i = 0; i < ECO_CELLS_PER_CHUNK; ++i) {
        EcoAtmosphericCell* cell = &chunk->atmosphere[i];
        cell->temperature_k = temp_t[i];
        cell->p_h2o         = temp_h2o[i];
        cell->p_co2         = temp_co2[i];

        // Recalculate saturation vapor pressure (Tetens)
        float t_c = cell->temperature_k - 273.15f;
        float sat_vp = 610.78f * expf((17.27f * t_c) / (t_c + 237.3f));
        cell->relative_humidity = cell->p_h2o / sat_vp;

        // If humidity exceeds 100%, vapor condenses into cloud liquid water
        if (cell->relative_humidity > 1.0f) {
            float excess_vapor = cell->p_h2o - sat_vp;
            float condensed_liquid_g = excess_vapor * 0.007f; // Conversion to g/m^3
            cell->cloud_water_g_m3 += condensed_liquid_g;
            cell->p_h2o = sat_vp; // Clamp vapor to saturation
            cell->relative_humidity = 1.0f;

            // Latent heat release: Condensation warms the parcel
            float latent_heat = 2.5e6f; // J/kg
            float delta_t = ((condensed_liquid_g * 1e-3f) * latent_heat) / (cell->density_kg_m3 * ECO_SPECIFIC_HEAT_CP);
            cell->temperature_k += fminf(delta_t, 2.0f); // Latent warming cap
        } else if (cell->relative_humidity < 0.90f && cell->cloud_water_g_m3 > 0.0f) {
            // Evaporation of existing cloud droplets in dry air
            float deficit = sat_vp - cell->p_h2o;
            float evaporated_g = fminf(cell->cloud_water_g_m3, deficit * 0.007f);
            cell->cloud_water_g_m3 -= evaporated_g;
            cell->p_h2o += evaporated_g * (1.0f / 0.007f);
        }

        // Precipitation: If liquid water density exceeds droplet suspension threshold (0.5 g/m^3)
        if (cell->cloud_water_g_m3 > 0.5f) {
            float rain = (cell->cloud_water_g_m3 - 0.5f) * 2.5f; // mm/h rate
            cell->precip_rate_mm_h = rain;
            cell->cloud_water_g_m3 -= rain * 0.05f;
        } else {
            cell->precip_rate_mm_h = 0.0f;
        }

        // Update ideal gas total pressure and density
        cell->total_pressure_pa = cell->p_n2 + cell->p_o2 + cell->p_co2 + cell->p_h2o + ECO_REF_P_ARGON_PA;
        cell->density_kg_m3 = cell->total_pressure_pa / (ECO_GAS_CONST_DRY_AIR * cell->temperature_k);
    }
}

void eco_atmo_tick(EcoChunk* chunk, const EcoAtmoConfig* config, float dt) {
    if (!chunk || !config || dt <= 0.0f) return;

    // 1. Solar thermal ground heating
    eco_atmo_apply_solar_thermal_heating(chunk, dt);

    // 2. Convective thermal buoyancy updrafts
    eco_atmo_solve_buoyancy(chunk, config);

    // 3. Pressure-gradient horizontal wind acceleration & Coriolis
    eco_atmo_compute_pressure_gradients(chunk, config);

    // 4. Advection of moisture, heat, and trace gases
    eco_atmo_advect_scalars(chunk, config, dt);
}
