#!/usr/bin/env python3
"""Ephemeral Mothership Fleet Onboarding Portal on port 8888."""
import http.server
import os
import sys

PORT = 8888
APK_DIR = os.path.expanduser("~/.gemini/apks")
TERMUX_APK = os.path.join(APK_DIR, "termux-app_v0.118.3_arm64.apk")
API_APK = os.path.join(APK_DIR, "termux-api-app_v0.53.0.apk")

FULL_BOOTSTRAP_CMD = (
    "pkg install -y git python termux-api && "
    "cd ~ && "
    "rm -rf gemini-integrated && "
    "git clone https://github.com/dieablo101/gemini-integrated.git && "
    "cd gemini-integrated && "
    "python3 gemini-integrated.py node 192.168.1.91"
)

UPDATE_CMD = "cd ~/gemini-integrated && git pull && python3 gemini-integrated.py node 192.168.1.91"

JOIN_SCRIPT = f"""#!/bin/bash
set -e
echo "[+] Gemini Mothership Satellite Connecting..."
{FULL_BOOTSTRAP_CMD}
"""

HTML_PAGE = f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mothership Fleet Bridge</title>
<style>
body {{ font-family: -apple-system, Roboto, sans-serif; background: #0e121a; color: #f0f4f8; text-align: center; padding: 16px; margin: 0; }}
h1 {{ color: #3399ff; font-size: 22px; margin-bottom: 4px; }}
p {{ color: #94a3b8; font-size: 13px; margin-bottom: 16px; }}
.card {{ background: #161e2e; border: 1px solid #2d3748; border-radius: 12px; padding: 18px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); max-width: 480px; margin: 0 auto; }}
.btn-apk {{ display: block; width: 100%; box-sizing: border-box; background: #0284c7; color: #fff; font-size: 15px; font-weight: bold; text-decoration: none; border-radius: 8px; padding: 14px 8px; margin-bottom: 12px; transition: background 0.2s; }}
.btn-apk:active {{ background: #0369a1; }}
.btn-copy {{ width: 100%; box-sizing: border-box; background: #2563eb; color: #fff; font-size: 15px; font-weight: bold; border: none; border-radius: 8px; padding: 14px 8px; cursor: pointer; transition: background 0.2s; margin-top: 10px; }}
.btn-copy:active {{ background: #1d4ed8; }}
.code-box {{ background: #090d14; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 12px; color: #38bdf8; word-break: break-all; margin: 12px 0; text-align: left; line-height: 1.5; }}
.step-title {{ font-weight: bold; color: #e2e8f0; font-size: 13px; margin: 16px 0 8px 0; text-align: left; }}
.copied {{ background: #10b981 !important; }}
</style>
</head>
<body>
<div class="card">
  <h1>🛸 Gemini Mothership Gate</h1>
  <p>Satellite Provisioning & Handshake</p>

  <div class="step-title">STEP 1: DOWNLOAD & INSTALL APKS (If needed)</div>
  <a href="/download/termux" class="btn-apk">⬇️ 1. DOWNLOAD TERMUX APK (34 MB)</a>
  <a href="/download/termux-api" class="btn-apk" style="background: #0f766e;">⬇️ 2. DOWNLOAD TERMUX:API (8.5 MB)</a>

  <div class="step-title">STEP 2: RUN IN TERMUX</div>
  <button id="btn1" class="btn-copy" onclick="copyText('cmd1', 'btn1')">📋 TAP TO COPY SETUP & CONNECT COMMAND</button>
  <div class="code-box" id="cmd1">{FULL_BOOTSTRAP_CMD}</div>

  <div class="step-title" style="margin-top: 20px;">IF ALREADY CLONED:</div>
  <button id="btn2" class="btn-copy" style="background: #475569;" onclick="copyText('cmd2', 'btn2')">🔄 TAP TO COPY PULL & CONNECT</button>
  <div class="code-box" id="cmd2">{UPDATE_CMD}</div>

  <p style="font-size: 12px; color: #64748b; margin-top: 16px; text-align: left;">
    1. Tap <b>📋 TAP TO COPY</b> above.<br>
    2. Switch to <b>Termux</b>, long-press, tap <b>Paste</b>, and hit <b>Enter</b>.
  </p>
</div>
<script>
function copyText(elemId, btnId) {{
  const text = document.getElementById(elemId).innerText;
  navigator.clipboard.writeText(text).then(() => {{
    const btn = document.getElementById(btnId);
    const orig = btn.innerText;
    btn.innerText = '✓ COPIED TO CLIPBOARD!';
    btn.classList.add('copied');
    setTimeout(() => {{
      btn.innerText = orig;
      btn.classList.remove('copied');
    }}, 2500);
  }}).catch(() => {{
    const range = document.createRange();
    range.selectNode(document.getElementById(elemId));
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    alert('Selected! Long-press and tap Copy');
  }});
}}
</script>
</body>
</html>
"""

class FleetHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/download/termux':
            self._serve_file(TERMUX_APK, 'application/vnd.android.package-archive', 'Termux_v0.118.3_arm64.apk')
        elif self.path == '/download/termux-api':
            self._serve_file(API_APK, 'application/vnd.android.package-archive', 'Termux_API_v0.53.0.apk')
        elif self.path in ('/go', '/join', '/go.sh'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/x-shellscript; charset=utf-8')
            self.send_header('Content-Length', str(len(JOIN_SCRIPT.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(JOIN_SCRIPT.encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(HTML_PAGE.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))

    def _serve_file(self, filepath, mime, filename):
        if not os.path.exists(filepath):
            self.send_error(404, "File not found")
            return
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(size))
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)

    def log_message(self, format, *args):
        pass

class ReusableServer(http.server.HTTPServer):
    allow_reuse_address = True

if __name__ == '__main__':
    with ReusableServer(('0.0.0.0', PORT), FleetHandler) as httpd:
        httpd.serve_forever()
