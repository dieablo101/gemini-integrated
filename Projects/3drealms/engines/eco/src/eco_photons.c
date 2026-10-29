#include "eco_photons.h"
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Computes celestial solar vector and top-of-atmosphere flux
EcoSolarTOA eco_photons_compute_solar_toa(float day_fraction, float latitude_rad, float solar_declination_rad) {
    EcoSolarTOA toa;
    
    // Solar hour angle: day_fraction 0.0 = midnight (-PI), 0.5 = solar noon (0), 1.0 = midnight (PI)
    float hour_angle = (day_fraction - 0.5f) * 2.0f * (float)M_PI;
    
    // Solar elevation angle: sin(alpha) = sin(lat)*sin(dec) + cos(lat)*cos(dec)*cos(h)
    float sin_elevation = sinf(latitude_rad) * sinf(solar_declination_rad) +
                          cosf(latitude_rad) * cosf(solar_declination_rad) * cosf(hour_angle);
    
    if (sin_elevation <= 0.0f) {
        // Sun is below local horizon
        toa.solar_elevation_sin = 0.0f;
        toa.solar_zenith_rad = (float)M_PI * 0.5f;
        toa.solar_azimuth_rad = 0.0f;
        toa.air_mass = 0.0f;
        toa.toa_par_flux = 0.0f;
        toa.toa_uv_flux = 0.0f;
        toa.toa_nir_flux = 0.0f;
        toa.is_night = true;
        return toa;
    }
    
    toa.is_night = false;
    toa.solar_elevation_sin = sin_elevation;
    float elevation_rad = asinf(sin_elevation);
    toa.solar_zenith_rad = ((float)M_PI * 0.5f) - elevation_rad;
    
    // Solar azimuth angle
    float cos_azimuth = (sinf(solar_declination_rad) * cosf(latitude_rad) -
                         cosf(solar_declination_rad) * sinf(latitude_rad) * cosf(hour_angle)) /
                        cosf(elevation_rad);
    if (cos_azimuth > 1.0f) cos_azimuth = 1.0f;
    if (cos_azimuth < -1.0f) cos_azimuth = -1.0f;
    
    float azimuth = acosf(cos_azimuth);
    if (sinf(hour_angle) > 0.0f) {
        azimuth = 2.0f * (float)M_PI - azimuth;
    }
    toa.solar_azimuth_rad = azimuth;
    
    // Relative Optical Air Mass (Kasten and Young, 1989 formulation for curved atmosphere)
    float zenith_deg = toa.solar_zenith_rad * (180.0f / (float)M_PI);
    if (zenith_deg < 89.0f) {
        float denom = cosf(toa.solar_zenith_rad) + 0.50572f * powf(96.07995f - zenith_deg, -1.6364f);
        toa.air_mass = (denom > 0.001f) ? (1.0f / denom) : 38.0f;
    } else {
        toa.air_mass = 38.0f;
    }
    
    // Base TOA incident radiation
    toa.toa_par_flux = ECO_SOLAR_CONSTANT_PAR * sin_elevation;
    toa.toa_uv_flux  = ECO_SOLAR_CONSTANT_UV  * sin_elevation;
    toa.toa_nir_flux = ECO_SOLAR_CONSTANT_NIR * sin_elevation;
    
    return toa;
}

// Downward Beer-Lambert radiative transfer solver for a vertical column
void eco_photons_solve_column_extinction(EcoAtmosphericCell *atm_cells,
                                         EcoPhotonSpectrum *photon_cells,
                                         int chunk_x_size,
                                         int chunk_y_size,
                                         int chunk_z_size,
                                         int col_x,
                                         int col_z,
                                         float cell_vertical_height_m,
                                         const EcoSolarTOA *solar_toa) {
    if (solar_toa->is_night || solar_toa->solar_elevation_sin <= 0.001f) {
        for (int y = 0; y < chunk_y_size; ++y) {
            int idx = (y * chunk_z_size + col_z) * chunk_x_size + col_x;
            photon_cells[idx].par_ppfd = 0.0f;
            photon_cells[idx].par_diffuse_ppfd = 0.0f;
            photon_cells[idx].uv_flux = 0.0f;
            photon_cells[idx].nir_flux = 0.0f;
            photon_cells[idx].direct_fraction = 0.0f;
            photon_cells[idx].optical_depth = 100.0f;
            photon_cells[idx].solar_zenith_rad = solar_toa->solar_zenith_rad;
            photon_cells[idx].solar_azimuth_rad = solar_toa->solar_azimuth_rad;
            photon_cells[idx].sun_direction[0] = 0.0f;
            photon_cells[idx].sun_direction[1] = -1.0f;
            photon_cells[idx].sun_direction[2] = 0.0f;
        }
        return;
    }

    // Slant path length through one vertical cell layer (m)
    float slant_path_m = cell_vertical_height_m / solar_toa->solar_elevation_sin;
    
    // Unit vector towards the sun
    float cos_elev = cosf(((float)M_PI * 0.5f) - solar_toa->solar_zenith_rad);
    float sun_dir_x = sinf(solar_toa->solar_azimuth_rad) * cos_elev;
    float sun_dir_y = solar_toa->solar_elevation_sin;
    float sun_dir_z = cosf(solar_toa->solar_azimuth_rad) * cos_elev;

    // Cumulative optical depths
    float cum_tau_par = 0.0f;
    float cum_tau_uv  = 0.0f;
    float cum_tau_nir = 0.0f;
    
    // Radiative transfer sweeps DOWNWARD from top layer (chunk_y_size - 1) to ground (y = 0)
    for (int y = chunk_y_size - 1; y >= 0; --y) {
        int idx = (y * chunk_z_size + col_z) * chunk_x_size + col_x;
        const EcoAtmosphericCell *atm = &atm_cells[idx];
        EcoPhotonSpectrum *photon = &photon_cells[idx];
        
        // 1. Air column mass density in this cell
        float rho = atm->density_kg_m3;
        if (rho < 0.01f) rho = 1.20f;
        
        // 2. Optical extinction components
        // Rayleigh scattering scales with density and strongly in UV (lambda^-4)
        float d_tau_rayleigh = ECO_SIGMA_RAYLEIGH_PAR * rho * slant_path_m;
        
        // Water vapor absorption (chiefly attenuates NIR)
        float total_p = atm->total_pressure_pa > 100.0f ? atm->total_pressure_pa : 101325.0f;
        float vapor_mass_fraction = (atm->p_h2o / total_p) * (18.015f / 28.964f);
        float vapor_density = rho * vapor_mass_fraction;
        float d_tau_vapor = ECO_SIGMA_VAPOR_NIR * vapor_density * slant_path_m;
        
        // Cloud droplet extinction (based on condensed cloud_water_g_m3 or relative humidity)
        float cloud_water_kg_m3 = atm->cloud_water_g_m3 * 0.001f;
        if (atm->relative_humidity > 1.0f && cloud_water_kg_m3 <= 0.0f) {
            cloud_water_kg_m3 = (atm->relative_humidity - 1.0f) * vapor_density;
        }
        float d_tau_cloud = ECO_SIGMA_CLOUD_EXTINCTION * (cloud_water_kg_m3 * 1000.0f) * (slant_path_m * 0.001f);
        
        // Spectral optical depth increments
        cum_tau_par += d_tau_rayleigh + d_tau_cloud;
        cum_tau_uv  += (d_tau_rayleigh * 3.5f) + (d_tau_cloud * 1.2f);
        cum_tau_nir += (d_tau_rayleigh * 0.4f) + d_tau_vapor + (d_tau_cloud * 0.9f);
        
        // 3. Beer-Lambert Extinction: I = I_0 * exp(-tau)
        float direct_transmittance = expf(-cum_tau_par);
        float transmittance_uv     = expf(-cum_tau_uv);
        float transmittance_nir    = expf(-cum_tau_nir);
        
        // Forward diffuse skylight fraction
        float diffuse_scatter_factor = 0.20f * (1.0f - direct_transmittance);
        float total_par_transmittance = direct_transmittance + diffuse_scatter_factor;
        if (total_par_transmittance > 1.0f) total_par_transmittance = 1.0f;
        
        float par_direct_w = solar_toa->toa_par_flux * direct_transmittance;
        float par_diffuse_w = solar_toa->toa_par_flux * diffuse_scatter_factor;
        
        photon->par_ppfd = (par_direct_w + par_diffuse_w) * ECO_PAR_WATTS_TO_PPFD;
        photon->par_diffuse_ppfd = par_diffuse_w * ECO_PAR_WATTS_TO_PPFD;
        photon->direct_fraction = (photon->par_ppfd > 0.01f) ? (par_direct_w / (par_direct_w + par_diffuse_w)) : 0.0f;
        
        photon->uv_flux = solar_toa->toa_uv_flux * transmittance_uv;
        photon->nir_flux = solar_toa->toa_nir_flux * transmittance_nir;
        photon->optical_depth = cum_tau_par;
        photon->solar_zenith_rad = solar_toa->solar_zenith_rad;
        photon->solar_azimuth_rad = solar_toa->solar_azimuth_rad;
        photon->ground_albedo = 0.18f; // Standard vegetative/soil ground albedo
        
        photon->sun_direction[0] = sun_dir_x;
        photon->sun_direction[1] = sun_dir_y;
        photon->sun_direction[2] = sun_dir_z;
    }
}

// Solves photon transport across an entire volumetric chunk
void eco_photons_solve_chunk(EcoAtmosphericCell *atm_cells,
                             EcoPhotonSpectrum *photon_cells,
                             int chunk_x_size,
                             int chunk_y_size,
                             int chunk_z_size,
                             float cell_vertical_height_m,
                             float day_fraction,
                             float latitude_rad,
                             float solar_declination_rad) {
    EcoSolarTOA solar_toa = eco_photons_compute_solar_toa(day_fraction, latitude_rad, solar_declination_rad);
    
    for (int z = 0; z < chunk_z_size; ++z) {
        for (int x = 0; x < chunk_x_size; ++x) {
            eco_photons_solve_column_extinction(atm_cells,
                                                photon_cells,
                                                chunk_x_size,
                                                chunk_y_size,
                                                chunk_z_size,
                                                x,
                                                z,
                                                cell_vertical_height_m,
                                                &solar_toa);
        }
    }
}
