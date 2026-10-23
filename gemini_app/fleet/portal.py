#!/usr/bin/env python3
"""Ephemeral Mothership Fleet Onboarding Portal on port 8888."""
import http.server
import os
import sys

from gemini_app.fleet.protocol import get_local_lan_ip

PORT = int(os.environ.get("PORTAL_PORT", 8890))
APK_DIR = os.path.expanduser("~/.gemini/apks")
TERMUX_APK = os.path.join(APK_DIR, "termux-app_v0.118.3_arm64.apk")
API_APK = os.path.join(APK_DIR, "termux-api-app_v0.53.0.apk")
BOOT_APK = os.path.join(APK_DIR, "termux-boot-app_v0.8.1.apk")

LOCAL_IP = get_local_lan_ip() or "192.168.1.90"

BOOTSTRAP_CMD = f"""pkg install -y git python termux-api
termux-wake-lock
cd ~
rm -rf gemini-integrated
git clone https://github.com/dieablo101/gemini-integrated.git
cd gemini-integrated
python3 gemini-integrated.py autostart --install --mothership {LOCAL_IP}
python3 gemini-integrated.py node {LOCAL_IP}"""

HTML_PAGE = f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mothership Fleet Bridge</title>
<style>
body {{ font-family: -apple-system, Roboto, sans-serif; background: #0e121a; color: #f0f4f8; text-align: center; padding: 18px; margin: 0; }}
h1 {{ color: #3399ff; font-size: 22px; margin-bottom: 4px; }}
p {{ color: #94a3b8; font-size: 14px; margin-bottom: 20px; }}
.card {{ background: #161e2e; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); max-width: 480px; margin: 0 auto; }}
.btn-apk {{ display: block; width: 100%; box-sizing: border-box; background: #0284c7; color: #fff; font-size: 15px; font-weight: bold; text-decoration: none; border-radius: 8px; padding: 14px 8px; margin-bottom: 12px; transition: background 0.2s; }}
.btn-apk:active {{ background: #0369a1; }}
.btn-copy {{ width: 100%; box-sizing: border-box; background: #2563eb; color: #fff; font-size: 16px; font-weight: bold; border: none; border-radius: 8px; padding: 16px 8px; cursor: pointer; transition: background 0.2s; margin-top: 14px; }}
.btn-copy:active {{ background: #1d4ed8; }}
.code-box {{ background: #090d14; border: 1px solid #1e293b; border-radius: 8px; padding: 14px; font-family: monospace; font-size: 13px; color: #38bdf8; word-break: break-all; margin: 12px 0; text-align: left; line-height: 1.5; white-space: pre-wrap; }}
.step-title {{ font-weight: bold; color: #e2e8f0; font-size: 14px; margin: 16px 0 8px 0; text-align: left; }}
.note-box {{ background: #1f2937; border-left: 4px solid #f59e0b; padding: 10px; font-size: 12px; color: #cbd5e1; text-align: left; border-radius: 4px; margin-bottom: 14px; }}
.copied {{ background: #10b981 !important; }}
</style>
</head>
<body>
<div class="card">
  <h1>🛸 Gemini Mothership Gate</h1>
  <p>Satellite Provisioning & Handshake</p>

  <div class="step-title">STEP 1: DOWNLOAD APKS</div>
  <a href="/download/termux" class="btn-apk">⬇️ 1. DOWNLOAD TERMUX (34 MB)</a>
  <a href="/download/termux-api" class="btn-apk" style="background: #0f766e;">⬇️ 2. DOWNLOAD TERMUX:API (8.5 MB)</a>
  <a href="/download/termux-boot" class="btn-apk" style="background: #7c3aed;">⬇️ 3. DOWNLOAD TERMUX:BOOT (0.7 MB)</a>

  <div class="note-box">
    <b>Important for Boot Persistence:</b><br>
    1. Open <b>Termux:Boot</b> app once after installing.<br>
    2. In Android Settings &rarr; Apps &rarr; Termux &rarr; Battery &rarr; Select <b>Unrestricted</b>.
  </div>

  <div class="step-title">STEP 2: RUN IN TERMUX</div>
  <button id="btn" class="btn-copy" onclick="copyCmd()">📋 TAP TO COPY RECONNECT COMMAND</button>
  <div class="code-box" id="cmd">{BOOTSTRAP_CMD}</div>
</div>
<script>
function copyCmd() {{
  const text = document.getElementById('cmd').innerText;
  navigator.clipboard.writeText(text).then(() => {{
    const btn = document.getElementById('btn');
    btn.innerText = '✓ COPIED TO CLIPBOARD!';
    btn.classList.add('copied');
    setTimeout(() => {{
      btn.innerText = '📋 TAP TO COPY RECONNECT COMMAND';
      btn.classList.remove('copied');
    }}, 3000);
  }}).catch(() => {{
    const range = document.createRange();
    range.selectNode(document.getElementById('cmd'));
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    alert('Selected! Long press text and tap Copy');
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
        elif self.path == '/download/termux-boot':
            self._serve_file(BOOT_APK, 'application/vnd.android.package-archive', 'Termux_Boot_v0.8.1.apk')
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
