"""Dedicated 3D Asset & Shader Inspector Applet for the Photon Game Engine.

Runs isolated on a dedicated port (e.g., 8889) independently of Wingman (8888).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from gemini_app.webapplet.engine import WebAppletEngine


def get_inspector_html(port: int = 8889) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Inspector // Photon AI Game Engine</title>
  <style>
    body {{
      background: #050811;
      color: #93c5fd;
      font-family: -apple-system, sans-serif;
      margin: 0;
      padding: 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100vh;
      box-sizing: border-box;
    }}
    .box {{
      background: #0e172a;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 24px;
      text-align: center;
      max-width: 500px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    h1 {{ color: #38bdf8; font-size: 18px; margin-bottom: 8px; }}
    p {{ color: #64748b; font-size: 13px; line-height: 1.6; }}
    .badge {{
      display: inline-block;
      margin-top: 14px;
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid #38bdf8;
      color: #38bdf8;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-family: monospace;
    }}
  </style>
</head>
<body>
  <div class="box">
    <h1>🎮 Photon 3D Asset Inspector</h1>
    <p>Dedicated WebGL/Canvas viewport for Blender procedural meshes and Godot PBR shader swatches.</p>
    <div class="badge">LISTENING ON PORT {port}</div>
  </div>
</body>
</html>
"""


class InspectorApplet:
    """Standalone 3D visualizer applet."""

    def __init__(self, engine: Optional[WebAppletEngine] = None, port: int = 8889) -> None:
        self.engine = engine or WebAppletEngine(name="inspector", host="0.0.0.0", port=port, sse_path="/applet/inspector/events")
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.engine.register_get("/", self._handle_index)
        self.engine.register_get("/applet/inspector", self._handle_index)
        self.engine.register_get("/applet/inspector/ping", lambda h, q: {"status": "ok", "applet": "inspector"})

    def _handle_index(self, handler: Any, query: Dict[str, List[str]]) -> str:
        return get_inspector_html(port=self.engine.port)

    def start(self) -> bool:
        return self.engine.start()

    def stop(self) -> None:
        self.engine.stop()
