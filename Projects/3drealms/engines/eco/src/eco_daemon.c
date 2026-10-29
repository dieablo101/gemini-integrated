/**
 * ECO-ENGINE: Real-Time Planetary Daemon
 * engines/ecoengine/src/eco_daemon.c
 *
 * Runs the biophysical simulation in lockstep with the game frame rate,
 * streaming wind shear, precipitation drops, and thermodynamics into /dev/shm.
 */

#include "eco_engine.h"
#include "eco_water_bridge.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <signal.h>

#define ECO_CMD_FILE "/dev/shm/eco_cmd.txt"

static volatile bool s_running = true;

static void handle_sigint(int sig) {
    (void)sig;
    s_running = false;
}

int main(int argc, char** argv) {
    int max_ticks = -1;
    bool quiet = false;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--ticks") == 0 && i + 1 < argc) {
            max_ticks = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--quiet") == 0) {
            quiet = true;
        }
    }

    signal(SIGINT, handle_sigint);
    signal(SIGTERM, handle_sigint);

    if (!quiet) {
        printf("[EcoDaemon] Starting planetary EcoEngine daemon...\n");
    }

    eco_water_bridge_init();

    EcoEngineConfig cfg = eco_engine_default_config();
    cfg.arena_capacity_bytes = 16 * 1024 * 1024; /* 16MB */
    EcoEngine* engine = eco_engine_create(&cfg);
    if (!engine) {
        fprintf(stderr, "[EcoDaemon] Failed to allocate EcoEngine!\n");
        return 1;
    }

    /* Initialize central chunk for game arena */
    EcoChunk* chunk = eco_engine_get_or_create_chunk(engine, 0, 0, 0, 0);
    if (!chunk) {
        fprintf(stderr, "[EcoDaemon] Failed to allocate central chunk!\n");
        eco_engine_destroy(engine);
        return 1;
    }

    /* Add initial moisture and wind gradient */
    for (int i = 0; i < ECO_CELLS_PER_CHUNK; i++) {
        chunk->atmosphere[i].p_h2o = 1200.0f;             /* 1.2 kPa */
        chunk->atmosphere[i].cloud_water_g_m3 = 1.5f;     /* 1.5 g/m^3 cloud water */
        chunk->atmosphere[i].wind_u = 3.5f;               /* 3.5 m/s East wind */
        chunk->atmosphere[i].wind_w = 2.1f;               /* 2.1 m/s North wind */
        chunk->plants[i].root_zone_moisture = 0.28f;
    }

    if (!quiet) {
        printf("[EcoDaemon] Online. Streaming to %s at 60 Hz.\n", ECO_SHM_TELEMETRY_PATH);
    }

    const float dt = 1.0f / 60.0f;
    int tick = 0;
    float rain_override = 0.0f;
    bool is_raining = false;

    while (s_running) {
        /* Check IPC command file every 10 ticks */
        if (tick % 10 == 0) {
            FILE* cmd_f = fopen(ECO_CMD_FILE, "r");
            if (cmd_f) {
                char cmd_buf[128];
                if (fgets(cmd_buf, sizeof(cmd_buf), cmd_f)) {
                    if (strncmp(cmd_buf, "rain", 4) == 0) {
                        float rate = 16.0f;
                        if (strlen(cmd_buf) > 5) {
                            float parsed = (float)atof(cmd_buf + 5);
                            if (parsed > 0.0f) rate = parsed;
                        }
                        rain_override = rate;
                        is_raining = true;
                        if (!quiet) printf("[EcoDaemon] CMD: Rain triggered at %.1f mm/h\n", rain_override);
                    } else if (strncmp(cmd_buf, "storm", 5) == 0) {
                        rain_override = 28.0f;
                        is_raining = true;
                        for (int i = 0; i < ECO_CELLS_PER_CHUNK; i++) {
                            chunk->atmosphere[i].wind_u = 8.5f;
                            chunk->atmosphere[i].wind_w = 6.2f;
                        }
                        if (!quiet) printf("[EcoDaemon] CMD: Storm triggered at %.1f mm/h with heavy winds\n", rain_override);
                    } else if (strncmp(cmd_buf, "clear", 5) == 0) {
                        rain_override = 0.0f;
                        is_raining = false;
                        for (int i = 0; i < ECO_CELLS_PER_CHUNK; i++) {
                            chunk->atmosphere[i].cloud_water_g_m3 = 0.2f;
                            chunk->atmosphere[i].precip_rate_mm_h = 0.0f;
                            chunk->atmosphere[i].wind_u = 2.5f;
                            chunk->atmosphere[i].wind_w = 1.2f;
                        }
                        if (!quiet) printf("[EcoDaemon] CMD: Skies cleared.\n");
                    }
                }
                fclose(cmd_f);
                unlink(ECO_CMD_FILE);
            }
        }

        /* Apply rain conditions across cells if active */
        if (is_raining && rain_override > 0.0f) {
            for (int i = 0; i < ECO_CELLS_PER_CHUNK; i++) {
                chunk->atmosphere[i].cloud_water_g_m3 = 3.5f;
                chunk->atmosphere[i].precip_rate_mm_h = rain_override;
                chunk->atmosphere[i].relative_humidity = 0.98f;
            }
        }

        /* Advance biophysical causality */
        eco_engine_tick(engine, dt);

        /* Write water basin telemetry (basin at x = 0, z = -4.5, radius = 7.5m) */
        eco_water_bridge_update(engine, 0.0f, -4.5f, 7.5f);

        tick++;
        if (max_ticks > 0 && tick >= max_ticks) {
            break;
        }

        /* 60 FPS pacing (~16.6ms) */
        usleep(16666);
    }

    if (!quiet) {
        printf("[EcoDaemon] Shutting down after %d ticks.\n", tick);
    }

    eco_engine_destroy(engine);
    return 0;
}
