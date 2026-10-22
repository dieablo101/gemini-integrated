"""Gemini WebApplet Subsystem.

A multi-instance, lightweight HTTP/SSE runtime and RPC bridge
powering bilateral interactive web portals (Wingman), 3D visualizers
(Inspector), and web testing automation.
"""

from gemini_app.webapplet.engine import WebAppletEngine

__all__ = ["WebAppletEngine"]
