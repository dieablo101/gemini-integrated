#include "eco_magnetosphere.h"
#include <math.h>

void eco_magneto_calc_dipole_field(const EcoMagnetoConfig* config,
                                   float world_x, float world_y, float world_z,
                                   float out_b_field[3]) {
    if (!config || !out_b_field) return;

    // Radius from center of planet
    float r2 = (world_x * world_x) + (world_y * world_y) + (world_z * world_z);
    float r = sqrtf(r2);
    if (r < 1.0f) r = 1.0f;

    // Unit radial direction vector r_hat
    float inv_r = 1.0f / r;
    float rx = world_x * inv_r;
    float ry = world_y * inv_r;
    float rz = world_z * inv_r;

    // Magnetic dipole moment vector M (tilted relative to Y-axis)
    // M = M0 * (sin(tilt), cos(tilt), 0)
    float mx = config->dipole_moment * sinf(config->tilt_angle_rad);
    float my = config->dipole_moment * cosf(config->tilt_angle_rad);
    float mz = 0.0f;

    // Dot product (M . r_hat)
    float m_dot_r = (mx * rx) + (my * ry) + (mz * rz);

    // B(r) = (mu_0 / 4*pi) * (1 / r^3) * [ 3 * (M . r_hat) * r_hat - M ]
    // mu_0 / (4 * pi) = 1.0e-7 T*m/A
    float factor = 1.0e-7f / (r * r * r);

    // Magnetic field components in Tesla
    float bx_t = factor * ((3.0f * m_dot_r * rx) - mx);
    float by_t = factor * ((3.0f * m_dot_r * ry) - my);
    float bz_t = factor * ((3.0f * m_dot_r * rz) - mz);

    // Convert from Tesla to microteslas (uT) (1 T = 1,000,000 uT)
    out_b_field[0] = bx_t * 1.0e6f;
    out_b_field[1] = by_t * 1.0e6f;
    out_b_field[2] = bz_t * 1.0e6f;
}

void eco_magneto_calc_lorentz_accel(const float velocity[3],
                                   const float b_field[3],
                                   float charge_c,
                                   float mass_kg,
                                   float out_accel[3]) {
    if (!velocity || !b_field || !out_accel || mass_kg <= 0.0f) return;

    // B-field converted from uT to T
    float bx = b_field[0] * 1.0e-6f;
    float by = b_field[1] * 1.0e-6f;
    float bz = b_field[2] * 1.0e-6f;

    // Cross product: (v x B)
    float v_cross_b_x = (velocity[1] * bz) - (velocity[2] * by);
    float v_cross_b_y = (velocity[2] * bx) - (velocity[0] * bz);
    float v_cross_b_z = (velocity[0] * by) - (velocity[1] * bx);

    // a = (q / m) * (v x B)  (assuming E = 0 for solar wind plasma)
    float q_over_m = charge_c / mass_kg;
    out_accel[0] = q_over_m * v_cross_b_x;
    out_accel[1] = q_over_m * v_cross_b_y;
    out_accel[2] = q_over_m * v_cross_b_z;
}

float eco_magneto_calc_magnetopause_radius(const EcoMagnetoConfig* config) {
    if (!config) return 0.0f;

    // Equatorial surface magnetic field B_0:
    // B_0 = (mu_0 / 4*pi) * M / R_planet^3
    float r_p = config->planetary_radius_m;
    float b0 = 1.0e-7f * (config->dipole_moment / (r_p * r_p * r_p)); // Tesla

    // Solar wind mass density: rho_sw = n_sw * m_proton
    float rho_sw = config->solar_wind_density * ECO_PROTON_MASS;

    // Solar wind dynamic pressure: P_dyn = rho_sw * v_sw^2
    float v_sw = config->solar_wind_speed;
    float p_dyn = rho_sw * v_sw * v_sw;
    if (p_dyn <= 1.0e-12f) p_dyn = 1.0e-12f;

    // Magnetic pressure at standoff balance:
    // R_mp / R_p = ( (2 * B_0^2) / (mu_0 * P_dyn) )^(1/6)
    float ratio_6 = (2.0f * b0 * b0) / (ECO_MU_0 * p_dyn);
    float standoff_ratio = powf(ratio_6, 1.0f / 6.0f);

    return standoff_ratio * r_p;
}

void eco_magneto_update_chunk(EcoChunk* chunk,
                              const EcoMagnetoConfig* config,
                              float chunk_world_x, float chunk_world_y, float chunk_world_z) {
    if (!chunk || !config || !chunk->magnetics) return;

    float solar_v[3] = { 0.0f, 0.0f, -config->solar_wind_speed }; // Solar wind incident along -Z axis
    float standoff_km = eco_magneto_calc_magnetopause_radius(config) * 1.0e-3f;

    for (int y = 0; y < ECO_CHUNK_DIM_Y; ++y) {
        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                uint32_t idx = (y * ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + (z * ECO_CHUNK_DIM_X) + x;
                EcoMagneticCell* mag = &chunk->magnetics[idx];

                float cell_wx = chunk_world_x + ((float)x * 10.0f);
                float cell_wy = chunk_world_y + ((float)y * 5.0f);
                float cell_wz = chunk_world_z + ((float)z * 10.0f);

                // 1. Calculate local dipole vector B
                float b_vec[3];
                eco_magneto_calc_dipole_field(config, cell_wx, cell_wy, cell_wz, b_vec);
                mag->b_field[0] = b_vec[0];
                mag->b_field[1] = b_vec[1];
                mag->b_field[2] = b_vec[2];

                float b_mag = sqrtf((b_vec[0] * b_vec[0]) + (b_vec[1] * b_vec[1]) + (b_vec[2] * b_vec[2]));
                mag->b_magnitude = b_mag;

                // 2. Compute Lorentz deflection of solar wind protons
                float accel[3];
                eco_magneto_calc_lorentz_accel(solar_v, b_vec, ECO_ELEM_CHARGE, ECO_PROTON_MASS, accel);
                mag->lorentz_accel[0] = accel[0];
                mag->lorentz_accel[1] = accel[1];
                mag->lorentz_accel[2] = accel[2];

                // 3. Solar wind properties at chunk
                mag->solar_wind_speed = config->solar_wind_speed * 1.0e-3f; // in km/s
                mag->proton_density_cm3 = config->solar_wind_density * 1.0e-6f; // per cm^3
                mag->magnetopause_r_km = standoff_km;

                // 4. Auroral ionization factor:
                // Aurora occurs where magnetic field lines plunge vertically into the atmosphere (high abs(By/|B|))
                // with sufficient magnetic strength and upper atmospheric altitude (y > 4)
                float vertical_inclination = fabsf(b_vec[1]) / fmaxf(1.0f, b_mag);
                float altitude_factor = (float)y / (float)ECO_CHUNK_DIM_Y;
                mag->auroral_ionization = vertical_inclination * altitude_factor * (b_mag / 60.0f);
                if (mag->auroral_ionization > 1.0f) mag->auroral_ionization = 1.0f;

                // 5. Surface ionizing radiation dose (uSv/h):
                // Strong horizontal B-field deflects harmful cosmic rays
                // Unshielded deep space ~100 uSv/h, surface shielded ~0.1 - 0.3 uSv/h
                float shielding = 1.0f - expf(- b_mag / 25.0f);
                mag->surface_rad_dose = 100.0f * (1.0f - shielding * 0.998f);
            }
        }
    }
}
