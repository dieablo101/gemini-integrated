/**
 * Dedicated Multiplier Stepping Controller (.9 Multiplier Section)
 * Project Photon Engine - Core Silicon Architecture
 *
 * Implements fine-grained stepping across the .9 multiplier headroom:
 * Multiplier Bins 31x through 39x (3.1 GHz - 3.9 GHz).
 * Provides proportional gear selection for dynamic computational demand.
 */

#ifndef MULTIPLIER_CONTROLLER_H
#define MULTIPLIER_CONTROLLER_H

#include "substrate_msr_governor.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    GEAR_TRUE_LOCK_FLOOR = 30,  /* 3.00 GHz: Base invariant tick */
    GEAR_WARM_ACCEL      = 32,  /* 3.20 GHz: Light branch prediction & physics resolve */
    GEAR_SUSTAINED_PUSH  = 35,  /* 3.50 GHz: Geometry transform / queue pump */
    GEAR_HIGH_SURGE      = 37,  /* 3.70 GHz: Dense SIMD raster calculations */
    GEAR_APEX_CEILING    = 39   /* 3.90 GHz: Peak AVX2 vector execution */
} MultiplierGear;

typedef struct {
    MultiplierGear current_gear;
    uint8_t current_bin;
    uint64_t step_count;
    SubstrateMsrGovernor *msr_gov;
} MultiplierController;

static inline void multiplier_controller_init(MultiplierController *mc, SubstrateMsrGovernor *gov) {
    if (!mc) return;
    mc->msr_gov = gov;
    mc->current_gear = GEAR_TRUE_LOCK_FLOOR;
    mc->current_bin = 30;
    mc->step_count = 0;
}

static inline bool multiplier_controller_step_to_gear(MultiplierController *mc, MultiplierGear gear) {
    if (!mc) return false;
    mc->current_gear = gear;
    mc->current_bin = (uint8_t)gear;
    mc->step_count++;
    if (mc->msr_gov) {
        return msr_set_multiplier_ratio(mc->msr_gov, mc->current_bin);
    }
    return true;
}

static inline bool multiplier_controller_step_direct_bin(MultiplierController *mc, uint8_t bin) {
    if (!mc || bin < 30 || bin > 39) return false;
    mc->current_bin = bin;
    mc->step_count++;
    if (mc->msr_gov) {
        return msr_set_multiplier_ratio(mc->msr_gov, bin);
    }
    return true;
}

#ifdef __cplusplus
}
#endif

#endif /* MULTIPLIER_CONTROLLER_H */
