/**
 * @file eco_vulkan_bridge.h
 * @brief Vulkan 1.4 Compute Direct-Bridge & Host-Device SSBO/Image Mappings.
 *
 * Bridges the C biophysical engine data layout directly to Vulkan SSBOs,
 * 3D volumetric images (Cloud water, vapor, temperature, pressure),
 * and dynamic MultiMesh foliage instance buffers.
 */

#ifndef ECO_VULKAN_BRIDGE_H
#define ECO_VULKAN_BRIDGE_H

#include "eco_types.h"
#include "eco_engine.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief 3D Volumetric atmospheric voxel grid layout for GPU texturing.
 * Matches GLSL layout(rgba16f) or layout(rgba32f) image3D.
 * Channel R: Liquid cloud droplet water content (g/m^3)
 * Channel G: Water vapor density / specific humidity (g/m^3)
 * Channel B: Air parcel temperature normalized (Kelvin)
 * Channel A: Barometric pressure normalized (Pascals)
 */
typedef struct ECO_ALIGN64 EcoVoxelAtmosphere {
    float cloud_liquid_water;  /**< g/m^3 condensed water */
    float water_vapor_density; /**< g/m^3 vapor */
    float temperature_k;       /**< Kelvin */
    float pressure_pa;         /**< Pascals */
} EcoVoxelAtmosphere;

/**
 * @brief Foliage GPU MultiMesh instance buffer payload.
 * 64-byte aligned to allow 1:1 hardware instanced indirect draws on GPU.
 */
typedef struct ECO_ALIGN64 EcoFoliageInstance {
    float pos_x, pos_y, pos_z;      /**< 3D world position (m) */
    float scale_trunk;              /**< Trunk height/radius scale derived from wood biomass */
    float leaf_area_index;          /**< LAI for canopy opacity & leaf mesh LOD */
    float wind_deflection_x;        /**< Real-time branch sway vector X from fluid solver */
    float wind_deflection_z;        /**< Real-time branch sway vector Z from fluid solver */
    float transpiration_cooling;   /**< Transpiration evaporative cooling rate */
    float solar_occlusion;          /**< Self-shading and neighbor shadow extinction [0..1] */
    float glucose_reserve_norm;     /**< Sugar reserves for seasonal bud/bloom state [0..1] */
    float padding[6];               /**< Pad to strict 64 bytes (10 named + 6 padding = 16 floats * 4 = 64B) */
} EcoFoliageInstance;

/**
 * @brief Global Uniform Buffer Object (UBO) passed to compute raymarchers.
 * 64-byte aligned std140 layout matching GLSL uniform Block.
 */
typedef struct ECO_ALIGN64 EcoVulkanComputeUBO {
    float sun_direction[4];       /**< Normalized unit vector to sun (xyz) + pad */
    float sun_color_par[4];       /**< Incident PAR spectrum RGB (W/m^2) + PPFD */
    float sun_color_nir[4];       /**< Incident NIR spectrum RGB (W/m^2) + pad */
    float camera_pos[4];          /**< Camera eye position (xyz) + pad */
    float camera_inv_view[16];    /**< Inverse view matrix for ray generation */
    float camera_inv_proj[16];    /**< Inverse projection matrix */
    
    /* Planetary & Atmospheric Parameters */
    float planet_radius;          /**< Planetary radius in meters */
    float atmosphere_radius;      /**< Top of atmosphere radius in meters */
    float henyey_greenstein_g;    /**< Forward scattering asymmetry factor (e.g. 0.8) */
    float raymarch_step_size;     /**< Integration step size in meters */
    
    /* Electrodynamic Magnetosphere */
    float magnetopause_radius;    /**< Standoff radius (meters) */
    float solar_wind_speed;       /**< km/s */
    float auroral_intensity;      /**< Overall auroral glow gain */
    float elapsed_time;           /**< Simulation clock (seconds) */
} EcoVulkanComputeUBO;

/**
 * @brief High-level Vulkan bridge host staging structure.
 */
typedef struct EcoVulkanBridge {
    EcoVulkanComputeUBO ubo;
    EcoVoxelAtmosphere  voxel_grid[ECO_CHUNK_DIM_Y][ECO_CHUNK_DIM_Z][ECO_CHUNK_DIM_X];
    EcoFoliageInstance  foliage_instances[ECO_CHUNK_DIM_X * ECO_CHUNK_DIM_Z];
    uint32_t            active_foliage_count;
    uint32_t            total_voxels;
} EcoVulkanBridge;

/**
 * @brief Initializes the Vulkan bridge staging buffers.
 */
void eco_vulkan_bridge_init(EcoVulkanBridge* bridge);

/**
 * @brief Packs an EcoEngine chunk's atmospheric cells into the 3D voxel grid.
 */
void eco_vulkan_bridge_pack_atmosphere(
    EcoVulkanBridge* bridge,
    const EcoAtmosphericCell* cells
);

/**
 * @brief Packs botanical biomass and physiological state into the foliage MultiMesh buffer.
 */
void eco_vulkan_bridge_pack_foliage(
    EcoVulkanBridge* bridge,
    const EcoPlantState* plants,
    const EcoAtmosphericCell* ground_air
);

/**
 * @brief Updates the Compute UBO with current solar kinematics and magnetosphere state.
 */
void eco_vulkan_bridge_update_ubo(
    EcoVulkanBridge* bridge,
    const EcoEngine* engine,
    const EcoPhotonSpectrum* sun_state,
    const float cam_pos[3],
    float step_size
);

#ifdef __cplusplus
}
#endif

#endif /* ECO_VULKAN_BRIDGE_H */
