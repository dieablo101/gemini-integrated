/**
 * FLUX Recipe: Obsidian Gothic Basalt
 * 2KB text recipe replacing ~20MB of 2048x2048 PBR maps
 */
#include "../core/flux_core.h"
#include <stdio.h>

int main(void) {
    FluxRecipe obsidian = {
        .seed = 0xDEADBEEF,
        .cell_scale = 3.5f,
        .cell_jitter = 0.85f,
        .mortar_depth = 0.18f,
        .mortar_width = 0.08f,
        .weathering_intensity = 0.65f,
        .crack_octaves = 4.0f,
        .edge_wear = 0.25f,
        .primary_tint = {0.05f, 0.04f, 0.06f},   /* Deep void obsidian */
        .secondary_tint = {0.14f, 0.12f, 0.18f}, /* Lustrous basalt highlight */
        .mortar_tint = {0.02f, 0.015f, 0.025f},  /* Cold dark crypt mortar */
        .base_roughness = 0.32f,                 /* Semi-gloss obsidian */
        .base_metallic = 0.15f
    };

    char shader_code[8192];
    int len = flux_compile_godot_shader(&obsidian, "Obsidian_Gothic_Basalt", shader_code, sizeof(shader_code));
    
    FILE *f = fopen("Projects/3drealms/engines/flux/shaders/obsidian_basalt.gdshader", "w");
    if (f) {
        fwrite(shader_code, 1, len, f);
        fclose(f);
        printf("FLUX: Successfully compiled obsidian_basalt.gdshader (%d bytes) - 0KB texture VRAM!\n", len);
    }
    return 0;
}
