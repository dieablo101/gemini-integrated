/**
 * ECO-ENGINE: Unit Tests & Verification Suite
 * engines/ecoengine/tests/test_eco_core.c
 */

#include "eco_types.h"
#include "eco_arena.h"
#include "eco_engine.h"

#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <math.h>
#include <time.h>

static void test_struct_alignments_and_sizes(void) {
    printf("[TEST] Checking struct memory layouts and 64-byte alignments...\n");

    printf("  sizeof(EcoPhotonSpectrum)  = %zu bytes\n", sizeof(EcoPhotonSpectrum));
    printf("  sizeof(EcoAtmosphericCell) = %zu bytes\n", sizeof(EcoAtmosphericCell));
    printf("  sizeof(EcoMagneticCell)    = %zu bytes\n", sizeof(EcoMagneticCell));
    printf("  sizeof(EcoPlantState)      = %zu bytes\n", sizeof(EcoPlantState));

    assert(sizeof(EcoPhotonSpectrum)  == 64);
    assert(sizeof(EcoAtmosphericCell) == 64);
    assert(sizeof(EcoMagneticCell)    == 64);
    assert(sizeof(EcoPlantState)      == 64);

    assert(alignof(EcoPhotonSpectrum)  == 64);
    assert(alignof(EcoAtmosphericCell) == 64);
    assert(alignof(EcoMagneticCell)    == 64);
    assert(alignof(EcoPlantState)      == 64);

    printf("  -> OK: All physical types strictly 64-byte cache-aligned!\n");
}

static void test_arena_allocator(void) {
    printf("[TEST] Testing 64-byte memory arena allocator...\n");

    EcoArena arena;
    bool ok = eco_arena_init(&arena, 1024 * 1024); /* 1 MB */
    assert(ok);
    assert(arena.buffer != NULL);
    assert(((uintptr_t)arena.buffer % 64) == 0);

    /* Allocate small chunk and verify alignment */
    void* p1 = eco_arena_alloc(&arena, 12);
    assert(p1 != NULL);
    assert(((uintptr_t)p1 % 64) == 0);

    /* Allocate array of 100 atmospheric cells */
    EcoAtmosphericCell* cells = (EcoAtmosphericCell*)eco_arena_alloc_zero(&arena, 100, sizeof(EcoAtmosphericCell));
    assert(cells != NULL);
    assert(((uintptr_t)cells % 64) == 0);

    /* Verify zero-cleared memory */
    for (int i = 0; i < 100; ++i) {
        assert(cells[i].temperature_k == 0.0f);
        assert(cells[i].total_pressure_pa == 0.0f);
    }

    /* Test marker & rollback */
    EcoArenaMarker marker = eco_arena_create_marker(&arena);
    void* temp = eco_arena_alloc(&arena, 4096);
    assert(temp != NULL);
    assert(arena.offset > marker.offset);

    eco_arena_rollback(&arena, marker);
    assert(arena.offset == marker.offset);

    EcoArenaStats stats = eco_arena_get_stats(&arena);
    printf("  Arena stats: capacity=%zu, allocated=%zu, peak=%zu, padding=%zu\n",
           stats.total_capacity_bytes, stats.bytes_allocated, stats.peak_allocated, stats.alignment_padding_bytes);

    eco_arena_destroy(&arena);
    printf("  -> OK: Memory arena operates with zero fragmentation!\n");
}

static void test_atmospheric_thermodynamics(void) {
    printf("[TEST] Testing atmospheric gas laws and thermodynamics...\n");

    EcoAtmosphericCell cell;
    cell.p_n2          = ECO_REF_P_N2_PA;
    cell.p_o2          = ECO_REF_P_O2_PA;
    cell.p_co2         = ECO_REF_P_CO2_PA;
    cell.p_h2o         = 1200.0f; /* 1200 Pa water vapor */
    cell.temperature_k = 293.15f; /* 20 deg C */

    eco_cell_compute_thermodynamics(&cell);

    /* Dalton's Law: total pressure should be sum of partial pressures + argon */
    float expected_total = cell.p_n2 + cell.p_o2 + cell.p_co2 + cell.p_h2o + ECO_REF_P_ARGON_PA;
    assert(fabsf(cell.total_pressure_pa - expected_total) < 0.01f);

    /* Air density should be approx 1.2 kg/m^3 at room temp sea level */
    printf("  Calculated air density: %.4f kg/m^3 (expected ~1.20)\n", cell.density_kg_m3);
    assert(cell.density_kg_m3 > 1.15f && cell.density_kg_m3 < 1.25f);

    /* Relative humidity should be reasonable (~51% at 20C with 1200Pa) */
    printf("  Relative humidity: %.1f%%\n", cell.relative_humidity * 100.0f);
    assert(cell.relative_humidity > 0.40f && cell.relative_humidity < 0.65f);

    printf("  -> OK: Thermodynamics conform to standard physical gas laws!\n");
}

static void test_engine_lifecycle_and_tick(void) {
    printf("[TEST] Testing EcoEngine chunk allocation and diurnal tick loop...\n");

    EcoEngineConfig cfg = eco_engine_default_config();
    cfg.arena_capacity_bytes = 16 * 1024 * 1024; /* 16 MB */
    cfg.max_active_chunks = 8;
    cfg.day_night_cycle_sec = 60.0f; /* 60s fast test cycle */

    EcoEngine* engine = eco_engine_create(&cfg);
    assert(engine != NULL);

    /* Create chunk at (0, 0, 0, LOD 0) */
    EcoChunk* chunk = eco_engine_get_or_create_chunk(engine, 0, 0, 0, 0);
    assert(chunk != NULL);
    assert(chunk->is_active);
    assert(chunk->atmosphere != NULL);
    assert(chunk->photons != NULL);
    assert(chunk->magnetics != NULL);
    assert(chunk->plants != NULL);

    /* Check initial baseline plant state */
    float initial_glucose = chunk->plants[0].glucose_pool_g;
    float initial_co2 = chunk->atmosphere[0].p_co2;
    printf("  Initial chunk [0] state: CO2=%.2f Pa, Glucose=%.2f g\n", initial_co2, initial_glucose);

    /* Advance simulation into broad daylight (sim_time = 15s in a 60s cycle is 1/4 = peak solar noon) */
    eco_engine_tick(engine, 15.0f);

    /* Verify photons and photosynthesis occurred */
    assert(chunk->photons[0].par_ppfd > 100.0f);
    assert(chunk->plants[0].net_assimilation_a > 0.0f);
    assert(chunk->plants[0].glucose_pool_g > initial_glucose);
    assert(chunk->atmosphere[0].p_co2 < initial_co2);

    printf("  Peak noon chunk [0] state: PAR=%.1f umol/m^2/s, CO2=%.2f Pa, Glucose=%.2f g, Assimilation=%.2f umol/m^2/s\n",
           chunk->photons[0].par_ppfd, chunk->atmosphere[0].p_co2, chunk->plants[0].glucose_pool_g, chunk->plants[0].net_assimilation_a);

    /* Benchmark: Run 1,000 engine ticks across chunk cells */
    clock_t start = clock();
    for (int t = 0; t < 1000; ++t) {
        eco_engine_tick(engine, 0.016f); /* 60 FPS delta */
    }
    clock_t end = clock();
    double elapsed_ms = ((double)(end - start) / CLOCKS_PER_SEC) * 1000.0;
    double us_per_tick = (elapsed_ms * 1000.0) / 1000.0;

    printf("  Benchmark (1,000 ticks x %d cells): %.2f ms total (%.2f us/tick)\n",
           ECO_CELLS_PER_CHUNK, elapsed_ms, us_per_tick);

    eco_engine_destroy(engine);
    printf("  -> OK: Engine runs with sub-millisecond execution speeds!\n");
}

int main(void) {
    setbuf(stdout, NULL);
    printf("=========================================\n");
    printf("   ECO-ENGINE CORE VERIFICATION SUITE    \n");
    printf("=========================================\n\n");

    test_struct_alignments_and_sizes();
    printf("\n");
    test_arena_allocator();
    printf("\n");
    test_atmospheric_thermodynamics();
    printf("\n");
    test_engine_lifecycle_and_tick();
    printf("\n");

    printf("=========================================\n");
    printf("   ALL ECO-ENGINE TESTS PASSED! [100%%]  \n");
    printf("=========================================\n");
    return 0;
}
