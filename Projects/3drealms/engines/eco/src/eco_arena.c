/**
 * ECO-ENGINE: Memory Arena Allocator Implementation
 * engines/ecoengine/src/eco_arena.c
 */

#define _POSIX_C_SOURCE 200809L

#include "eco_arena.h"
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER) || defined(__MINGW32__)
    #include <malloc.h>
    #define eco_aligned_malloc(size, align) _aligned_malloc((size), (align))
    #define eco_aligned_free(ptr)           _aligned_free((ptr))
#else
    static inline void* eco_aligned_malloc(size_t size, size_t align) {
        void* ptr = NULL;
        if (posix_memalign(&ptr, align, size) != 0) {
            return NULL;
        }
        return ptr;
    }
    #define eco_aligned_free(ptr) free((ptr))
#endif

static inline uintptr_t align_forward_uintptr(uintptr_t ptr, size_t alignment) {
    uintptr_t p = ptr;
    uintptr_t a = (uintptr_t)alignment;
    uintptr_t modulo = p & (a - 1);
    if (modulo != 0) {
        p += (a - modulo);
    }
    return p;
}

bool eco_arena_init(EcoArena* arena, size_t capacity_bytes) {
    if (!arena || capacity_bytes == 0) {
        return false;
    }

    /* Round capacity up to multiple of cache line size */
    size_t aligned_capacity = (capacity_bytes + (ECO_CACHE_LINE_BYTES - 1)) & ~(ECO_CACHE_LINE_BYTES - 1);
    void* mem = eco_aligned_malloc(aligned_capacity, ECO_CACHE_LINE_BYTES);
    if (!mem) {
        return false;
    }

    arena->buffer = (uint8_t*)mem;
    arena->capacity = aligned_capacity;
    arena->offset = 0;
    arena->peak_offset = 0;
    arena->allocation_count = 0;
    arena->padding_bytes = 0;
    arena->owns_memory = true;

    return true;
}

bool eco_arena_init_fixed(EcoArena* arena, void* external_buffer, size_t buffer_size) {
    if (!arena || !external_buffer || buffer_size == 0) {
        return false;
    }

    uintptr_t raw_addr = (uintptr_t)external_buffer;
    uintptr_t aligned_addr = align_forward_uintptr(raw_addr, ECO_CACHE_LINE_BYTES);
    size_t lead_padding = (size_t)(aligned_addr - raw_addr);

    if (lead_padding >= buffer_size) {
        return false;
    }

    arena->buffer = (uint8_t*)aligned_addr;
    arena->capacity = buffer_size - lead_padding;
    arena->offset = 0;
    arena->peak_offset = 0;
    arena->allocation_count = 0;
    arena->padding_bytes = lead_padding;
    arena->owns_memory = false;

    return true;
}

void eco_arena_destroy(EcoArena* arena) {
    if (!arena) return;

    if (arena->owns_memory && arena->buffer) {
        eco_aligned_free(arena->buffer);
    }

    arena->buffer = NULL;
    arena->capacity = 0;
    arena->offset = 0;
    arena->peak_offset = 0;
    arena->allocation_count = 0;
    arena->padding_bytes = 0;
    arena->owns_memory = false;
}

void* eco_arena_alloc(EcoArena* arena, size_t size_bytes) {
    if (!arena || !arena->buffer || size_bytes == 0) {
        return NULL;
    }

    uintptr_t current_addr = (uintptr_t)(arena->buffer + arena->offset);
    uintptr_t aligned_addr = align_forward_uintptr(current_addr, ECO_CACHE_LINE_BYTES);
    size_t padding = (size_t)(aligned_addr - current_addr);

    if (arena->offset + padding + size_bytes > arena->capacity) {
        /* Out of memory in this arena */
        return NULL;
    }

    arena->offset += padding + size_bytes;
    arena->padding_bytes += padding;
    arena->allocation_count++;

    if (arena->offset > arena->peak_offset) {
        arena->peak_offset = arena->offset;
    }

    return (void*)aligned_addr;
}

void* eco_arena_alloc_zero(EcoArena* arena, size_t count, size_t elem_size) {
    size_t total_bytes = count * elem_size;
    void* ptr = eco_arena_alloc(arena, total_bytes);
    if (ptr) {
        memset(ptr, 0, total_bytes);
    }
    return ptr;
}

EcoArenaMarker eco_arena_create_marker(const EcoArena* arena) {
    EcoArenaMarker marker;
    marker.offset = arena ? arena->offset : 0;
    return marker;
}

void eco_arena_rollback(EcoArena* arena, EcoArenaMarker marker) {
    if (!arena) return;
    if (marker.offset <= arena->offset) {
        arena->offset = marker.offset;
    }
}

void eco_arena_reset(EcoArena* arena) {
    if (!arena) return;
    arena->offset = 0;
    arena->allocation_count = 0;
}

EcoArenaStats eco_arena_get_stats(const EcoArena* arena) {
    EcoArenaStats stats;
    memset(&stats, 0, sizeof(stats));
    if (arena) {
        stats.total_capacity_bytes   = arena->capacity;
        stats.bytes_allocated        = arena->offset;
        stats.peak_allocated         = arena->peak_offset;
        stats.allocation_count       = arena->allocation_count;
        stats.alignment_padding_bytes= arena->padding_bytes;
    }
    return stats;
}
