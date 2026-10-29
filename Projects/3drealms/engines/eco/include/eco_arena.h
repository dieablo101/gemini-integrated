/**
 * ECO-ENGINE: Memory Arena Allocator
 * engines/ecoengine/include/eco_arena.h
 *
 * Fast, 64-byte cache-aligned linear bump allocator with scratchpad markers.
 * Designed for zero-fragmentation high-throughput chunk simulation grids.
 */

#ifndef ECO_ARENA_H
#define ECO_ARENA_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ECO_CACHE_LINE_BYTES 64

typedef struct EcoArenaMarker {
    size_t offset;
} EcoArenaMarker;

typedef struct EcoArenaStats {
    size_t total_capacity_bytes;
    size_t bytes_allocated;
    size_t peak_allocated;
    size_t allocation_count;
    size_t alignment_padding_bytes;
} EcoArenaStats;

typedef struct EcoArena {
    uint8_t*       buffer;
    size_t         capacity;
    size_t         offset;
    size_t         peak_offset;
    size_t         allocation_count;
    size_t         padding_bytes;
    bool           owns_memory;
} EcoArena;

/**
 * Initializes a new memory arena backed by an internally allocated aligned block.
 * @param arena Pointer to uninitialized arena struct
 * @param capacity_bytes Total buffer size to reserve
 * @return true on successful allocation, false otherwise
 */
bool eco_arena_init(EcoArena* arena, size_t capacity_bytes);

/**
 * Initializes an arena using an existing pre-allocated buffer (e.g. mmap or static buffer).
 * @param arena Pointer to uninitialized arena struct
 * @param external_buffer Pre-allocated memory pointer
 * @param buffer_size Size of external buffer in bytes
 * @return true on success, false if buffer is invalid
 */
bool eco_arena_init_fixed(EcoArena* arena, void* external_buffer, size_t buffer_size);

/**
 * Destroys the arena, releasing internal backing memory.
 */
void eco_arena_destroy(EcoArena* arena);

/**
 * Allocates a contiguous block aligned to 64 bytes.
 * @param arena Active arena
 * @param size_bytes Number of payload bytes requested
 * @return 64-byte aligned pointer, or NULL if capacity exceeded
 */
void* eco_arena_alloc(EcoArena* arena, size_t size_bytes);

/**
 * Allocates a typed array aligned to 64 bytes with zero-cleared memory.
 */
void* eco_arena_alloc_zero(EcoArena* arena, size_t count, size_t elem_size);

/**
 * Creates a rollback marker to allow rolling back temporary scratch allocations.
 */
EcoArenaMarker eco_arena_create_marker(const EcoArena* arena);

/**
 * Rolls back the arena to a previously saved marker.
 */
void eco_arena_rollback(EcoArena* arena, EcoArenaMarker marker);

/**
 * Resets the entire arena back to zero offset without freeing underlying memory.
 */
void eco_arena_reset(EcoArena* arena);

/**
 * Queries real-time memory telemetry metrics.
 */
EcoArenaStats eco_arena_get_stats(const EcoArena* arena);

#ifdef __cplusplus
}
#endif

#endif /* ECO_ARENA_H */
