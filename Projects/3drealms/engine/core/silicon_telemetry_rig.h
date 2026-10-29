/**
 * Silicon Telemetry Rig - Metric Instrumentation & Verification Harness
 * Project Photon Engine - Core Silicon Architecture
 *
 * Measures:
 * 1. Clean Room Isolation: Involuntary context switch count (Target: 0).
 * 2. Tri-Phase Clocks & Multiplier Transition Speed.
 * 3. A/B Opposing Force Blanking Latency (Pipeline Stall Delta).
 * 4. Temp Run Thermal Decay (dT/dt) & Energy Drain.
 */

#ifndef SILICON_TELEMETRY_RIG_H
#define SILICON_TELEMETRY_RIG_H

#include "substrate_arbiter.h"
#include "tri_phase_timer.h"
#include "blanking_polarity_switch.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    /* Core Purity */
    int pinned_core;
    long involuntary_context_switches;
    long voluntary_context_switches;
    bool is_clean_room_pure;

    /* Timing & Multiplier */
    double measured_base_ghz;
    double measured_apex_ghz;
    uint64_t oc_burst_cycles;
    uint64_t multiplier_transition_cycles;

    /* A/B Opposing Force Degauss */
    uint64_t control_stall_cycles;     /* Without degauss */
    uint64_t active_stall_cycles;      /* With Big-Endian degauss */
    double pipeline_recovery_ratio;

    /* Temp Run & Super-Cool Gel */
    double temp_run_ms;
    double thermal_decay_celsius;
    double tim_dissipation_rate_c_per_ms;
} SiliconTelemetryAudit;

/**
 * Runs the full empirical verification suite and populates the audit report.
 */
SiliconTelemetryAudit run_silicon_telemetry_suite(int target_core, int iterations);

/**
 * Prints the formatted telemetry audit report to stdout.
 */
void print_silicon_telemetry_audit(const SiliconTelemetryAudit *audit);

#ifdef __cplusplus
}
#endif

#endif /* SILICON_TELEMETRY_RIG_H */
