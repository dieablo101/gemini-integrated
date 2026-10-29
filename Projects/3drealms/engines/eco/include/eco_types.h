/**
 * ECO-ENGINE: Biophysical Core Type Definitions
 * engines/ecoengine/include/eco_types.h
 *
 * Cache-aligned (64-byte) physical, chemical, and biological state structures
 * for CPU SIMD vectorization and zero-copy Vulkan 1.4 compute buffer exchange.
 */

#ifndef ECO_TYPES_H
#define ECO_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_MSC_VER)
    #define ECO_ALIGN64 __declspec(align(64))
#elif defined(__GNUC__) || defined(__clang__)
    #define ECO_ALIGN64 __attribute__((aligned(64)))
#else
    #define ECO_ALIGN64
#endif

/* Physical Constants (CODATA Recommended Values) */
#define ECO_GAS_CONSTANT_R       8.314462618f     /* J / (mol * K) */
#define ECO_SPECIFIC_GAS_DRY_AIR 287.058f          /* J / (kg * K) */
#define ECO_PLANCK_CONSTANT_H    6.62607015e-34f   /* J * s */
#define ECO_SPEED_OF_LIGHT_C     299792458.0f      /* m / s */
#define ECO_AVOGADRO_NA          6.02214076e23f    /* mol^-1 */
#define ECO_STANDARD_GRAVITY_G   9.80665f          /* m / s^2 */
#define ECO_STEFAN_BOLTZMANN     5.670374419e-8f   /* W / (m^2 * K^4) */

/* Standard Molar Masses (kg / mol) */
#define ECO_MOLAR_MASS_N2        0.0280134f
#define ECO_MOLAR_MASS_O2        0.0319988f
#define ECO_MOLAR_MASS_CO2       0.0440100f
#define ECO_MOLAR_MASS_H2O       0.0180153f
#define ECO_MOLAR_MASS_ARGON     0.0399480f

/* Standard Sea-Level Reference Pressures (Pa) */
#define ECO_REF_PRESSURE_PA      101325.0f
#define ECO_REF_P_N2_PA          78084.0f
#define ECO_REF_P_O2_PA          20946.0f
#define ECO_REF_P_CO2_PA         42.0f             /* ~420 ppm */
#define ECO_REF_P_ARGON_PA       934.0f
#define ECO_REF_P_H2O_PA         1000.0f           /* ~50% RH at 15C */
#define ECO_REF_TEMPERATURE_K    288.15f           /* 15 deg C */

/**
 * 1. PHOTON & SPECTRAL RADIATION STATE
 * Captures photosynthetically active radiation (PAR), UV and NIR bands.
 * 64-byte aligned for AVX2/AVX-512 and direct Vulkan UBO/SSBO upload.
 */
typedef struct ECO_ALIGN64 EcoPhotonSpectrum {
    /* Radiance bands */
    float par_ppfd;           /* Photosynthetic Photon Flux Density (400-700nm): umol * m^-2 * s^-1 */
    float uv_flux;            /* Ultraviolet flux (280-400nm): W * m^-2 (tissue damage / ionization) */
    float nir_flux;           /* Near-infrared flux (700-1100nm): W * m^-2 (thermal radiation) */
    float direct_fraction;    /* Beam fraction (0.0 = completely diffuse, 1.0 = direct sunlight) */

    /* Geometry & Attenuation */
    float solar_zenith_rad;   /* Sun zenith angle from vertical (0 = directly overhead) */
    float solar_azimuth_rad;  /* Sun azimuth clockwise from North (radians) */
    float optical_depth;      /* Beer-Lambert optical airmass depth tau */
    float ground_albedo;      /* Surface reflection coefficient (0.0 - 1.0) */

    /* Vector Direction (Towards Sun) */
    float sun_direction[3];   /* Normalized solar illumination unit vector */
    float par_diffuse_ppfd;   /* Diffuse skylight scattered component */

    /* Reserved for SIMD alignment */
    float padding[4];
} EcoPhotonSpectrum;

/**
 * 2. ATMOSPHERIC GAS CELL
 * Conservation-of-mass molecular composition and thermodynamic state.
 * 64-byte aligned.
 */
typedef struct ECO_ALIGN64 EcoAtmosphericCell {
    /* Molecular partial pressures (Pascals) */
    float p_n2;               /* Nitrogen partial pressure */
    float p_o2;               /* Oxygen partial pressure */
    float p_co2;              /* Carbon dioxide partial pressure */
    float p_h2o;              /* Water vapor partial pressure (absolute humidity) */

    /* Thermodynamic Variables */
    float temperature_k;      /* Local temperature in Kelvin */
    float total_pressure_pa;  /* Barometric pressure = sum(p_i) */
    float density_kg_m3;      /* Air density rho = P / (R_spec * T) */
    float relative_humidity;  /* Relative humidity fraction (0.0 - 1.0) */

    /* Fluid Dynamics */
    float wind_u;             /* Wind velocity X (Eastward) in m/s */
    float wind_v;             /* Wind velocity Y (Vertical) in m/s */
    float wind_w;             /* Wind velocity Z (Northward) in m/s */
    float cloud_water_g_m3;   /* Condensed cloud liquid water density (g/m^3) */

    /* Hydrological & Precipitation */
    float precip_rate_mm_h;   /* Surface rainfall / snowfall rate (mm/h) */
    float dew_point_k;        /* Condensation dew point temperature in Kelvin */
    float reserved_a;
    float reserved_b;
} EcoAtmosphericCell;

/**
 * 3. PLANETARY MAGNETOSPHERE & IONOSPHERE
 * Intrinsic dipole magnetic field and solar wind plasma interaction.
 * 64-byte aligned.
 */
typedef struct ECO_ALIGN64 EcoMagneticCell {
    /* Intrinsic Magnetic Field Vector (microteslas, uT) */
    float b_field[3];         /* (Bx, By, Bz) magnetic flux density */
    float b_magnitude;        /* Total field strength = sqrt(Bx^2 + By^2 + Bz^2) */

    /* Solar Wind & Charged Plasma Interaction */
    float solar_wind_speed;   /* Solar wind velocity in km/s (~300-800 km/s) */
    float proton_density_cm3; /* Ionized proton density per cm^3 */
    float lorentz_accel[3];   /* Resulting Lorentz acceleration: a = (q/m)(v x B) */

    /* Atmospheric Shielding & Aurora */
    float auroral_ionization; /* Molecular excitation intensity (0.0 - 1.0 for GPU aurora rendering) */
    float magnetopause_r_km;  /* Standoff distance of magnetopause boundary in km */
    float surface_rad_dose;   /* Remanent ionizing radiation reaching surface (uSv/h) */
    float padding[4];
} EcoMagneticCell;

/**
 * 4. BOTANICAL BIOPHYSICAL STATE (Farquhar-von Caemmerer-Berry Model)
 * Real enzymatic photosynthesis, stomatal conductance, and biomass partitioning.
 * 64-byte aligned.
 */
typedef struct ECO_ALIGN64 EcoPlantState {
    /* Canopy Structure */
    float leaf_area_index;    /* LAI: total leaf area per unit ground area (m^2 / m^2) */
    float canopy_height_m;    /* Height of vegetative crown above ground */
    float foliage_cover;      /* Fraction of ground shaded (0.0 - 1.0) */
    float stomatal_conduct;   /* gs: Stomatal conductance to CO2 (mol * m^-2 * s^-1) */

    /* Biochemical Rates (Farquhar FvCB) */
    float rubisco_vcmax;      /* Max carboxylation capacity (umol CO2 * m^-2 * s^-1) */
    float electron_transport_j;/* Electron transport rate J (umol e- * m^-2 * s^-1) */
    float net_assimilation_a; /* Net carbon assimilation An (umol CO2 * m^-2 * s^-1) */
    float transpiration_e;    /* Water loss rate (mmol H2O * m^-2 * s^-1) */

    /* Carbon & Nutrient Reserves (Grams dry matter per m^2) */
    float glucose_pool_g;     /* Mobile glucose storage pool */
    float biomass_leaf_g;     /* Structural leaf biomass */
    float biomass_stem_g;     /* Structural wood/stem biomass */
    float biomass_root_g;     /* Root water/nutrient absorption biomass */

    /* Environmental Stress */
    float water_stress;       /* 0.0 = fully turgid, 1.0 = permanent wilting point */
    float thermal_stress;     /* 0.0 = optimal temperature (20-25C), 1.0 = enzyme denatured */
    float root_zone_moisture; /* Volumetric soil water content (theta: m^3 / m^3) */
    uint32_t plant_species_id;/* Botanical classification identifier */
} EcoPlantState;

/**
 * 5. CHUNK COORDINATES & SPATIAL DIMENSIONS
 */
typedef struct EcoChunkCoord {
    int32_t cx;               /* Chunk X coordinate */
    int32_t cy;               /* Chunk Y (Elevation) coordinate */
    int32_t cz;               /* Chunk Z coordinate */
    int32_t lod_level;        /* Level of detail (0 = discrete micro, 1 = meso, 2 = macro) */
} EcoChunkCoord;

/**
 * Compile-time assertion helper to enforce 64-byte cache alignment.
 */
#define ECO_STATIC_ASSERT(cond, msg) _Static_assert(cond, msg)

ECO_STATIC_ASSERT(sizeof(EcoPhotonSpectrum)   == 64, "EcoPhotonSpectrum must be exactly 64 bytes");
ECO_STATIC_ASSERT(sizeof(EcoAtmosphericCell)  == 64, "EcoAtmosphericCell must be exactly 64 bytes");
ECO_STATIC_ASSERT(sizeof(EcoMagneticCell)     == 64, "EcoMagneticCell must be exactly 64 bytes");
ECO_STATIC_ASSERT(sizeof(EcoPlantState)       == 64, "EcoPlantState must be exactly 64 bytes");

#ifdef __cplusplus
}
#endif

#endif /* ECO_TYPES_H */
