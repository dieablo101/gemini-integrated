"""Grim DAW Plugin for gemini-integrated.

Provides a unified digital audio workstation subsystem:
- Cockos REAPER headless pipeline & stem export automation
- Project RPP template generation with interactive stem matrix
- Real-time procedural DSP wave generation and audio utilities
- Direct bridge for Godot, Photon AI Game Engine, and external productions.
"""

from gemini_app.plugins.grim.core import GrimEngine, grim_engine

__all__ = ["GrimEngine", "grim_engine"]
