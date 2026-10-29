#ifndef ECO_ATMOSPHERE_H
#define ECO_ATMOSPHERE_H

#include "eco_types.h"
#include "eco_engine.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Physical constants for atmospheric mechanics
#define ECO_GAS_CONST_DRY_AIR    287.058f  // J/(kg*K)
#define ECO_GAS_CONST_VAPOR      461.5f    // J/(kg*K)
#define ECO_SPECIFIC_HEAT_CP     1005.0f   // J/(kg*K) for dry air at constant pressure
#define ECO_GRAVITY_EARTH        9.80665f  // m/s^2
#define ECO_LAPSE_RATE_DRY       0.0098f   // K/m dry adiabatic lapse rate (~9.8 K/km)
#define ECO_STANDARD_SL_PRESSURE 101325.0f // Pa at sea level
#define ECO_STANDARD_SL_TEMP     288.15f   // K (15 deg C) at sea level
#define ECO_STANDARD_SL_DENSITY  1.225f    // kg/m^3

// Atmospheric fluid configuration
typedef struct EcoAtmoConfig {
    float cell_size_x;         // Meters per cell (horizontal, e.g. 10.0m)
    float cell_size_y;         // Meters per cell (vertical, e.g. 5.0m)
    float cell_size_z;         // Meters per cell (horizontal, e.g. 10.0m)
    float kinematic_viscosity; // Air viscosity (m^2/s, ~1.5e-5)
    float thermal_diffusivity; // Thermal conductivity / (rho * Cp) (~2.0e-5)
    float drag_coefficient;    // Ground friction drag (~0.002)
    float coriolis_f;          // 2 * Omega * sin(lat) in rad/s (~1.0e-4 for mid-latitudes)
} EcoAtmoConfig;

// Initialize atmospheric chunk with barometric hydrostatic equilibrium
void eco_atmo_init_chunk(EcoChunk* chunk, const EcoAtmoConfig* config, float base_temperature_k);

// Compute 3D Pressure Gradient Acceleration:
// a_grad = - (1 / rho) * grad(P)
void eco_atmo_compute_pressure_gradients(EcoChunk* chunk, const EcoAtmoConfig* config);

// Compute Convective Buoyancy Updrafts:
// a_buoyancy = g * (T_cell - T_ambient) / T_ambient - g * liquid_water_mass
void eco_atmo_solve_buoyancy(EcoChunk* chunk, const EcoAtmoConfig* config);

// Advect scalars (CO2, H2O vapor, temperature) using semi-Lagrangian advection:
// S(x, t + dt) = S(x - v*dt, t)
void eco_atmo_advect_scalars(EcoChunk* chunk, const EcoAtmoConfig* config, float dt);

// Thermodynamic surface heating from NIR & ground solar flux:
// Solves ground conduction into lowest atmospheric layer (y = 0)
void eco_atmo_apply_solar_thermal_heating(EcoChunk* chunk, float dt);

// Master atmospheric simulation step:
// Couples buoyancy, pressure winds, advection, and condensation/cloud formation
void eco_atmo_tick(EcoChunk* chunk, const EcoAtmoConfig* config, float dt);

#ifdef __cplusplus
}
#endif

#endif // ECO_ATMOSPHERE_H
