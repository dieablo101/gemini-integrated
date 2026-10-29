/**
 * @file eco_vulkan_bridge.c
 * @brief Host-side implementation of Vulkan compute data bridge.
 */

#include "eco_vulkan_bridge.h"
#include <string.h>
#include <math.h>

void eco_vulkan_bridge_init(EcoVulkanBridge* bridge) {
    if (!bridge) return;
    memset(bridge, 0, sizeof(EcoVulkanBridge));
    
    bridge->total_voxels = ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Y * ECO_CHUNK_DIM_Z;
    bridge->active_foliage_count = ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z;
    
    /* Default optical parameters */
    bridge->ubo.henyey_greenstein_g = 0.75f; /* Realistic forward scattering for water droplets */
    bridge->ubo.raymarch_step_size = 1.0f;
    bridge->ubo.planet_radius = 6371000.0f;
    bridge->ubo.atmosphere_radius = 6471000.0f;
}

void eco_vulkan_bridge_pack_atmosphere(
    EcoVulkanBridge* bridge,
    const EcoAtmosphericCell* cells
) {
    if (!bridge || !cells) return;

    for (int y = 0; y < ECO_CHUNK_DIM_Y; ++y) {
        for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
            for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
                int idx = y * (ECO_CHUNK_DIM_Z * ECO_CHUNK_DIM_X) + z * ECO_CHUNK_DIM_X + x;
                const EcoAtmosphericCell* cell = &cells[idx];
                EcoVoxelAtmosphere* voxel = &bridge->voxel_grid[y][z][x];

                /* Extract liquid water content (g/m^3) */
                voxel->cloud_liquid_water = cell->cloud_water_g_m3;

                /* Compute vapor density (g/m^3) from vapor partial pressure: rho_v = P_v / (R_v * T) */
                float temp = cell->temperature_k;
                if (temp < 100.0f) temp = 288.15f;
                float rho_v = (cell->p_h2o / (461.5f * temp)) * 1000.0f; /* g/m^3 */
                voxel->water_vapor_density = rho_v;

                /* Normalized temperature (Kelvin) */
                voxel->temperature_k = temp;

                /* Barometric pressure (Pascals) */
                voxel->pressure_pa = cell->total_pressure_pa;
            }
        }
    }
}

void eco_vulkan_bridge_pack_foliage(
    EcoVulkanBridge* bridge,
    const EcoPlantState* plants,
    const EcoAtmosphericCell* ground_air
) {
    if (!bridge || !plants) return;

    uint32_t index = 0;
    for (int z = 0; z < ECO_CHUNK_DIM_Z; ++z) {
        for (int x = 0; x < ECO_CHUNK_DIM_X; ++x) {
            int p_idx = z * ECO_CHUNK_DIM_X + x;
            const EcoPlantState* plant = &plants[p_idx];
            EcoFoliageInstance* inst = &bridge->foliage_instances[index++];

            /* World position centered in cell (cell resolution = 2m horizontally) */
            inst->pos_x = (float)x * 2.0f + 1.0f;
            inst->pos_y = 0.0f; /* Ground elevation */
            inst->pos_z = (float)z * 2.0f + 1.0f;

            /* Trunk scale from wood biomass (allometry: height ~ wood^0.38) */
            float stem_mass = plant->biomass_stem_g;
            if (stem_mass < 0.1f) stem_mass = 0.1f;
            inst->scale_trunk = powf(stem_mass, 0.38f) * 0.5f;

            /* Leaf canopy LOD and opacity */
            inst->leaf_area_index = plant->leaf_area_index;

            /* Dynamic wind sway from atmospheric velocity vectors */
            if (ground_air) {
                const EcoAtmosphericCell* air = &ground_air[p_idx];
                inst->wind_deflection_x = air->wind_u * 0.15f;
                inst->wind_deflection_z = air->wind_w * 0.15f;
            } else {
                inst->wind_deflection_x = 0.0f;
                inst->wind_deflection_z = 0.0f;
            }

            /* Latent heat transpiration cooling */
            inst->transpiration_cooling = plant->transpiration_e;

            /* Self-shading factor: high LAI attenuates inner canopy light */
            float extinction = expf(-0.5f * plant->leaf_area_index);
            inst->solar_occlusion = 1.0f - extinction;

            /* Normalized glucose reserve for seasonal flowering/budding */
            inst->glucose_reserve_norm = plant->glucose_pool_g / (plant->glucose_pool_g + 100.0f);
        }
    }
}

void eco_vulkan_bridge_update_ubo(
    EcoVulkanBridge* bridge,
    const EcoEngine* engine,
    const EcoPhotonSpectrum* sun_state,
    const float cam_pos[3],
    float step_size
) {
    if (!bridge) return;

    if (sun_state) {
        bridge->ubo.sun_direction[0] = sun_state->sun_direction[0];
        bridge->ubo.sun_direction[1] = sun_state->sun_direction[1];
        bridge->ubo.sun_direction[2] = sun_state->sun_direction[2];
        bridge->ubo.sun_direction[3] = 0.0f;

        float par_ppfd = sun_state->par_ppfd;
        bridge->ubo.sun_color_par[0] = 0.95f * (par_ppfd / 2000.0f);
        bridge->ubo.sun_color_par[1] = 0.98f * (par_ppfd / 2000.0f);
        bridge->ubo.sun_color_par[2] = 0.85f * (par_ppfd / 2000.0f);
        bridge->ubo.sun_color_par[3] = par_ppfd;

        float nir_flux = sun_state->nir_flux;
        bridge->ubo.sun_color_nir[0] = 1.0f * (nir_flux / 700.0f);
        bridge->ubo.sun_color_nir[1] = 0.4f * (nir_flux / 700.0f);
        bridge->ubo.sun_color_nir[2] = 0.2f * (nir_flux / 700.0f);
        bridge->ubo.sun_color_nir[3] = nir_flux;

        bridge->ubo.auroral_intensity = (sun_state->sun_direction[1] < 0.1f) ? 1.0f : 0.15f;
    } else {
        bridge->ubo.sun_direction[0] = 0.0f;
        bridge->ubo.sun_direction[1] = 1.0f;
        bridge->ubo.sun_direction[2] = 0.0f;
        bridge->ubo.sun_direction[3] = 0.0f;
        bridge->ubo.auroral_intensity = 0.5f;
    }

    if (cam_pos) {
        bridge->ubo.camera_pos[0] = cam_pos[0];
        bridge->ubo.camera_pos[1] = cam_pos[1];
        bridge->ubo.camera_pos[2] = cam_pos[2];
        bridge->ubo.camera_pos[3] = 1.0f;
    }

    bridge->ubo.raymarch_step_size = (step_size > 0.01f) ? step_size : 1.0f;
    bridge->ubo.magnetopause_radius = 64553600.0f;
    bridge->ubo.solar_wind_speed = 400.0f;

    if (engine) {
        bridge->ubo.elapsed_time = (float)engine->sim_time_sec;
    }
}
