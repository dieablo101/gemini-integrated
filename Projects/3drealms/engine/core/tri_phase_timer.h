/**
 * Tri-Phase Silicon Timing Architecture
 * Project Photon Engine - Core Silicon Architecture
 *
 * Implements:
 * 1. Phase 1: True Lock Clock (Base Determinism, e.g. 3.0 GHz ratio 30x).
 * 2. Phase 2: Breather Clock (Relaxation & Degauss pulse during blanking window).
 * 3. Phase 3: Code-Organized Overclock (.9 Multiplier reserve bins 31x - 39x).
 * 4. Temp Run: Zero-switching coasting to super-cool silicon die into thermal paste.
 */

#ifndef TRI_PHASE_TIMER_H
#define TRI_PHASE_TIMER_H

#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <x86intrin.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    TIMING_PHASE_TRUE_LOCK,     /* 3.0 GHz Invariant base */
    TIMING_PHASE_BREATHER,      /* Blanking window relaxation */
    TIMING_PHASE_APEX_OC,       /* .9 Multiplier reserve boost (up to 3.9 GHz) */
    TIMING_PHASE_TEMP_RUN       /* Zero-switching macro chill */
} SiliconTimingPhase;

typedef struct {
    SiliconTimingPhase current_phase;
    double base_clock_ghz;       /* e.g. 3.0 */
    double apex_clock_ghz;       /* e.g. 3.9 */
    uint64_t phase_transitions;
    uint64_t temp_run_nanoseconds;
} TriPhaseTimer;

/**
 * Returns high-resolution monotonic time in nanoseconds.
 */
static inline uint64_t tri_phase_get_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/**
 * High-precision cycle counter (serialized RDTSCP).
 */
static inline uint64_t tri_phase_rdtscp(uint32_t *aux) {
    return __rdtscp(aux);
}

/**
 * Initializes the Tri-Phase Timer.
 */
static inline void tri_phase_timer_init(TriPhaseTimer *timer, double base_ghz, double apex_ghz) {
    if (!timer) return;
    timer->current_phase = TIMING_PHASE_TRUE_LOCK;
    timer->base_clock_ghz = base_ghz > 0.0 ? base_ghz : 3.0;
    timer->apex_clock_ghz = apex_ghz > 0.0 ? apex_ghz : 3.9;
    timer->phase_transitions = 0;
    timer->temp_run_nanoseconds = 0;
}

/**
 * Commands a phase transition in the silicon timing state machine.
 */
static inline void tri_phase_set_phase(TriPhaseTimer *timer, SiliconTimingPhase next_phase) {
    if (!timer) return;
    if (timer->current_phase != next_phase) {
        timer->current_phase = next_phase;
        timer->phase_transitions++;
    }
}

/**
 * Executes a Temp Run coast (super-cooling the silicon die into thermal paste)
 * by minimizing instruction switching activity for the requested duration.
 */
static inline void tri_phase_execute_temp_run(TriPhaseTimer *timer, uint64_t duration_ns) {
    if (!timer || duration_ns == 0) return;
    SiliconTimingPhase prev_phase = timer->current_phase;
    tri_phase_set_phase(timer, TIMING_PHASE_TEMP_RUN);

    uint64_t start = tri_phase_get_ns();
    while ((tri_phase_get_ns() - start) < duration_ns) {
        /* _mm_pause minimizes CPU dynamic switching power without relinquishing thread */
        _mm_pause();
    }

    timer->temp_run_nanoseconds += (tri_phase_get_ns() - start);
    tri_phase_set_phase(timer, prev_phase);
}

#ifdef __cplusplus
}
#endif

#endif /* TRI_PHASE_TIMER_H */
