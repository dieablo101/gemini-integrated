cmake_minimum_required(VERSION 3.16)
project(EcoEngine C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# High performance optimization flags for biological/fluid simulation
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-O3 -march=native -Wall -Wextra -ffast-math)
endif()

include_directories(include)

# Core engine library
set(ECO_SOURCES
    src/eco_arena.c
    src/eco_photons.c
    src/eco_atmosphere.c
    src/eco_magnetosphere.c
    src/eco_photosynthesis.c
    src/eco_engine.c
    src/eco_vulkan_bridge.c
    src/eco_water_bridge.c
)

add_library(ecoengine SHARED ${ECO_SOURCES})
target_link_libraries(ecoengine m)

# Real-time planetary daemon executable
add_executable(eco_daemon src/eco_daemon.c)
target_link_libraries(eco_daemon ecoengine m)

# Phase 1 Verification suite
add_executable(eco_test tests/test_eco_core.c)
target_link_libraries(eco_test ecoengine m)

# Phase 2 Photon solver test suite
add_executable(eco_photons_test tests/test_eco_photons.c)
target_link_libraries(eco_photons_test ecoengine m)

# Phase 3 Atmosphere & Magnetosphere test suite
add_executable(eco_atmo_mag_test tests/test_eco_atmo_mag.c)
target_link_libraries(eco_atmo_mag_test ecoengine m)

# Phase 4 Farquhar Photosynthesis test suite
add_executable(eco_photosynthesis_test tests/test_eco_photosynthesis.c)
target_link_libraries(eco_photosynthesis_test ecoengine m)

# Phase 5 Vulkan 1.4 Compute Bridge test suite
add_executable(eco_vulkan_bridge_test tests/test_eco_vulkan_bridge.c)
target_link_libraries(eco_vulkan_bridge_test ecoengine m)
