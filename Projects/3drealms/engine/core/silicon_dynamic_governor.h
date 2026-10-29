/**
 * Dynamic Silicon Voltage/Frequency Governor
 * Project Photon Engine - Core Silicon Architecture
 *
 * Coordinates:
 * 1. MSR Governor (Hardware Multiplier bins 30x - 39x)
 * 2. Tri-Phase Timer (True Lock <-> .9 Apex OC <-> Temp Run)
 * 3. Blanking Polarity Switch (Opposing Degauss Pulse)
 * 4. Autonomous Thermal Loop Guard (Super-cools when die temperature crosses limit)
 */

#ifndef SILICON_DYNAMIC_GOVERNOR_H
#define SILICON_DYNAMIC_GOVERNOR_H

#include "substrate_msr_governor.h"
#include "tri_phase_timer.h"
#include "blanking_polarity_switch.h"
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    SubstrateMsrGovernor msr_gov;
    TriPhaseTimer timer;
    double thermal_ceiling_celsius;   /* e.g. 75.0C -> auto trips Temp Run */
    double thermal_floor_celsius;     /* e.g. 60.0C -> resume normal clock */
    uint64_t apex_burst_count;
    uint64_t degauss_pulse_count;
    uint64_t temp_run_trips;
} DynamicSiliconGovernor;

/**
 * Initializes the Dynamic Silicon Governor.
 */
static inline bool dynamic_governor_init(DynamicSiliconGovernor *gov, int target_core, double base_ghz, double apex_ghz) {
    if (!gov) return false;
    msr_governor_init(&gov->msr_gov, target_core);
    tri_phase_timer_init(&gov->timer, base_ghz, apex_ghz);

    gov->thermal_ceiling_celsius = 75.0;
    gov->thermal_floor_celsius = 60.0;
    gov->apex_burst_count = 0;
    gov->degauss_pulse_count = 0;
    gov->temp_run_trips = 0;

    return true;
}

/**
 * Engages the .9 Multiplier Apex Overclock for incoming dense vector loops.
 */
static inline void dynamic_governor_enter_apex_oc(DynamicSiliconGovernor *gov) {
    if (!gov) return;
    tri_phase_set_phase(&gov->timer, TIMING_PHASE_APEX_OC);
    msr_set_multiplier_ratio(&gov->msr_gov, gov->msr_gov.apex_ratio);
    gov->apex_burst_count++;
}

/**
 * Returns to the deterministic True Lock base floor.
 */
static inline void dynamic_governor_exit_to_true_lock(DynamicSiliconGovernor *gov) {
    if (!gov) return;
    tri_phase_set_phase(&gov->timer, TIMING_PHASE_TRUE_LOCK);
    msr_set_multiplier_ratio(&gov->msr_gov, gov->msr_gov.base_ratio);
}

/**
 * Executes a Breather Blanking Window with Big-Endian opposing force degauss.
 */
static inline void dynamic_governor_blanking_breather(DynamicSiliconGovernor *gov, void *l1_scratchpad) {
    if (!gov) return;
    tri_phase_set_phase(&gov->timer, TIMING_PHASE_BREATHER);
    blanking_degauss_pulse(l1_scratchpad);
    gov->degauss_pulse_count++;
}

/**
 * Evaluates real-time thermal junction and executes Temp Run if thermal ceiling exceeded.
 */
static inline bool dynamic_governor_evaluate_thermal_run(DynamicSiliconGovernor *gov, uint64_t coast_duration_ns) {
    if (!gov) return false;
    double current_temp = msr_get_core_temp_celsius(&gov->msr_gov);

    if (current_temp >= gov->thermal_ceiling_celsius) {
        /* Drop off into Temp Run: halt switching activity to let the gel and copper wick heat */
        dynamic_governor_exit_to_true_lock(gov);
        tri_phase_execute_temp_run(&gov->timer, coast_duration_ns);
        gov->temp_run_trips++;
        return true;
    }
    return false;
}

/**
 * Clean shutdown of governor resources.
 */
static inline void dynamic_governor_close(DynamicSiliconGovernor *gov) {
    if (!gov) return;
    dynamic_governor_exit_to_true_lock(gov);
    msr_governor_close(&gov->msr_gov);
}

#ifdef __cplusplus
}
#endif

#endif /* SILICON_DYNAMIC_GOVERNOR_H */
