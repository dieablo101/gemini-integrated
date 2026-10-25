#!/usr/bin/env python3
"""
Upper Mind Web Nexus Public Distribution Exporter
Exports self-contained HTML and API JSON artifacts to public/ for Firebase Hosting and CDN edge distribution.
"""
import os
import json
import shutil
from gemini_app.cloud.upper_mind_server import UpperMindServer

def export_distribution():
    srv = UpperMindServer()
    os.makedirs('public/api', exist_ok=True)

    # 1. Export Observatory HTML
    observatory_html = srv._render_observatory_html()
    with open('public/index.html', 'w', encoding='utf-8') as f:
        f.write(observatory_html)

    # 2. Export Promo / Docs HTML
    if os.path.exists('docs/index.html'):
        shutil.copy('docs/index.html', 'public/docs.html')

    # 3. Export API JSON artifacts
    graph_data = srv._handle_graph(None, {})
    telemetry_data = srv._handle_telemetry(None, {})
    epiphanies_data = srv._handle_epiphanies(None, {})

    with open('public/api/graph.json', 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, indent=2)
    shutil.copy('public/api/graph.json', 'public/api/graph')

    with open('public/api/telemetry.json', 'w', encoding='utf-8') as f:
        json.dump(telemetry_data, f, indent=2)
    shutil.copy('public/api/telemetry.json', 'public/api/telemetry')

    with open('public/api/epiphanies.json', 'w', encoding='utf-8') as f:
        json.dump(epiphanies_data, f, indent=2)
    shutil.copy('public/api/epiphanies.json', 'public/api/epiphanies')

    print('Public distribution successfully generated in public/')

if __name__ == '__main__':
    export_distribution()
