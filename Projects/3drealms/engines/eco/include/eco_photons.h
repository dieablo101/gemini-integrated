#ifndef ECO_PHOTONS_H
#define ECO_PHOTONS_H

#include "eco_types.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Solar spectral constant outside atmosphere (AM0: Air Mass 0) in W/m^2
#define ECO_SOLAR_CONSTANT_TOTAL      1361.0f
// PAR fraction of total solar constant (~43% of solar spectrum is PAR 400-700nm)
#define ECO_SOLAR_CONSTANT_PAR        585.0f
// UV fraction of solar constant (~8% of solar spectrum is UV 290-400nm)
#define ECO_SOLAR_CONSTANT_UV         108.0f
// NIR fraction of solar constant (~49% of solar spectrum is Near-Infrared 700-2500nm)
#define ECO_SOLAR_CONSTANT_NIR        668.0f

// Conversion from PAR W/m^2 to PPFD (umol/m^2/s). 1 W/m^2 sunlight ≈ 4.57 umol/m^2/s
#define ECO_PAR_WATTS_TO_PPFD         4.57f

// Optical Extinction coefficients per unit density (m^2/kg)
#define ECO_SIGMA_RAYLEIGH_PAR        0.00010f   // Molecular Rayleigh scattering
#define ECO_SIGMA_AEROSOL_PAR         0.00045f   // Aerosols / particulate scattering
#define ECO_SIGMA_VAPOR_NIR           0.00180f   // Water vapor absorption (chiefly in NIR)
#define ECO_SIGMA_CLOUD_EXTINCTION    0.09500f   // Condensed cloud droplets (Mie extinction)

// Top-of-Atmosphere (TOA) incident solar vectors and flux
typedef struct {
    float solar_zenith_rad;        // Angle from vertical (0 = directly overhead, PI/2 = horizon)
    float solar_azimuth_rad;       // Horizontal orientation (0 = North, PI/2 = East)
    float solar_elevation_sin;     // sin(elevation) for direct projection on horizontal surface
    float air_mass;                // Relative optical path length (Kasten-Young formula)
    float toa_par_flux;            // Top-of-atmosphere PAR flux (W/m^2)
    float toa_uv_flux;             // Top-of-atmosphere UV flux (W/m^2)
    float toa_nir_flux;            // Top-of-atmosphere NIR flux (W/m^2)
    bool  is_night;                // True if sun is below horizon
} EcoSolarTOA;

// Computes Top-of-Atmosphere solar state from celestial geometry
EcoSolarTOA eco_photons_compute_solar_toa(float day_fraction, float latitude_rad, float solar_declination_rad);

// Solves downward optical extinction through a single vertical column
void eco_photons_solve_column_extinction(EcoAtmosphericCell *atm_cells,
                                         EcoPhotonSpectrum *photon_cells,
                                         int chunk_x_size,
                                         int chunk_y_size,
                                         int chunk_z_size,
                                         int col_x,
                                         int col_z,
                                         float cell_vertical_height_m,
                                         const EcoSolarTOA *solar_toa);

// Solves photon transport across an entire volumetric chunk
void eco_photons_solve_chunk(EcoAtmosphericCell *atm_cells,
                             EcoPhotonSpectrum *photon_cells,
                             int chunk_x_size,
                             int chunk_y_size,
                             int chunk_z_size,
                             float cell_vertical_height_m,
                             float day_fraction,
                             float latitude_rad,
                             float solar_declination_rad);

#ifdef __cplusplus
}
#endif

#endif // ECO_PHOTONS_H
