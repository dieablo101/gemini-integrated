#ifndef ECO_MAGNETOSPHERE_H
#define ECO_MAGNETOSPHERE_H

#include "eco_types.h"
#include "eco_engine.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Physical constants for Electrodynamics & Solar Wind
#define ECO_MU_0                 1.25663706212e-6f // Vacuum permeability (H/m or N/A^2)
#define ECO_ELEM_CHARGE          1.602176634e-19f  // Proton charge in Coulombs
#define ECO_PROTON_MASS          1.67262192369e-27f // Proton mass in kg
#define ECO_EARTH_DIPOLE_MOMENT  7.8e22f           // A*m^2 (Earth's magnetic dipole moment)
#define ECO_PLANETARY_RADIUS     6.371e6f          // meters

// Planetary Magnetosphere Configuration
typedef struct EcoMagnetoConfig {
    float dipole_moment;       // Planetary dipole strength in A*m^2
    float tilt_angle_rad;      // Magnetic dipole tilt relative to rotational axis (e.g. 11.5 deg = 0.20 rad)
    float planetary_radius_m;  // Planetary body radius
    float solar_wind_speed;    // Solar wind velocity (m/s, standard ~400,000 m/s = 400 km/s)
    float solar_wind_density;  // Protons per m^3 (standard quiet sun ~5.0e6 / m^3)
} EcoMagnetoConfig;

// Compute dipole magnetic field B(x, y, z) at a planetary position in world meters:
// B(r) = (mu_0 / 4*pi) * (1 / r^3) * [ 3 * (M . r_hat) * r_hat - M ]
void eco_magneto_calc_dipole_field(const EcoMagnetoConfig* config,
                                   float world_x, float world_y, float world_z,
                                   float out_b_field[3]);

// Compute Lorentz force acceleration on a charged particle / plasma packet:
// a = (q / m) * (E + v x B)
void eco_magneto_calc_lorentz_accel(const float velocity[3],
                                   const float b_field[3],
                                   float charge_c,
                                   float mass_kg,
                                   float out_accel[3]);

// Calculate solar wind dynamic pressure and Magnetopause Standoff Radius (Chapman-Ferraro distance):
// R_mp = ( B_0^2 / (mu_0 * rho_sw * v_sw^2) )^(1/6) * R_planet
float eco_magneto_calc_magnetopause_radius(const EcoMagnetoConfig* config);

// Update chunk magnetic state:
// Evaluates B-field vectors, auroral excitation (where B-field converges near poles),
// and radiation shielding factor (blocking solar particle atmospheric stripping)
void eco_magneto_update_chunk(EcoChunk* chunk,
                              const EcoMagnetoConfig* config,
                              float chunk_world_x, float chunk_world_y, float chunk_world_z);

#ifdef __cplusplus
}
#endif

#endif // ECO_MAGNETOSPHERE_H
