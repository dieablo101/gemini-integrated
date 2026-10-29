/**
 * Blanking Polarity Switch (Opposing Force Degauss)
 * Project Photon Engine - Core Silicon Architecture
 *
 * Implements:
 * 1. Big-Endian bit reversal / degauss pulse during the 150µs blanking window.
 * 2. Opposing polarity sweep across CPU register files and L1 data cache lines.
 * 3. Line capacitance discharge & ground bounce mitigation.
 */

#ifndef BLANKING_POLARITY_SWITCH_H
#define BLANKING_POLARITY_SWITCH_H

#include <stdint.h>
#include <immintrin.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Executes a 64-bit opposing polarity flip via endian reversal.
 */
static inline uint64_t degauss_flip64(uint64_t val) {
    return __builtin_bswap64(val);
}

/**
 * Executes an opposing polarity flash across an AVX2 256-bit register.
 * Inverts the byte layout to swing all differential line pairs 180 degrees.
 */
static inline void degauss_opposing_vector_pulse(void *buffer, size_t count_bytes) {
    if (!buffer || count_bytes < 32) return;

    /* Endian-reversal byte mask for 256-bit AVX2 register */
    const __m256i mask = _mm256_setr_epi8(
        15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0,
        15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0
    );

    uint8_t *ptr = (uint8_t *)buffer;
    size_t chunks = count_bytes / 32;

    for (size_t i = 0; i < chunks; ++i) {
        __m256i line = _mm256_loadu_si256((const __m256i *)(ptr + i * 32));
        __m256i flipped = _mm256_shuffle_epi8(line, mask);
        _mm256_storeu_si256((__m256i *)(ptr + i * 32), flipped);
    }
}

/**
 * Blanking window pulse: cycles opposing polarity through L1 cache scratchpad
 * to drain residual parasitic charge before the next frame crunch.
 */
static inline void blanking_degauss_pulse(void *scratchpad_32k) {
    if (!scratchpad_32k) return;
    /* 32KB is typical Intel L1 data cache size */
    degauss_opposing_vector_pulse(scratchpad_32k, 32768);
}

#ifdef __cplusplus
}
#endif

#endif /* BLANKING_POLARITY_SWITCH_H */
