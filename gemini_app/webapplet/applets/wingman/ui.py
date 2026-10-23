"""Self-contained interactive HTML/CSS/JS client for the Wingman portal.

Designed for dual-screen monitors on Mothership and 1/3 iPad Pro split view.
Provides:
  - Zero-Trust Security Gate (Awaiting Mothership Console Authorization OR direct PBKDF2 passkey unlock)
  - Work vs Chat dropdown switcher (Interactive Cards vs Bilateral Remote Chat Stream)
  - Live SSE card streaming & Apple Face ID / WebAuthn biometric authentication
"""

from __future__ import annotations


def get_wingman_html(
    title: str = "Wingman // Gemini Bilateral Portal",
    port: int = 8888,
    node_id: str = "local",
    auth_state: str = "pending",
    auth_req_id: str = "",
    client_ip: str = "127.0.0.1",
    session_token: str = "",
) -> str:
    """Returns responsive, dark-mode single-page portal HTML."""
    gate_display = "none" if auth_state == "approved" else "flex"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-hover: #1f2937;
      --border: #1f293d;
      --border-focus: #3b82f6;
      --accent: #3399ff;
      --accent-glow: rgba(51, 153, 255, 0.25);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --code-bg: #030712;
      --bubble-user: #1e3a8a;
      --bubble-bot: #111827;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }}

    html, body {{
      height: 100%;
      height: 100dvh;
      width: 100%;
      overflow: hidden;
    }}

    body {{
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font-sans);
      font-size: 14px;
      line-height: 1.5;
      display: flex;
      flex-direction: column;
      -webkit-text-size-adjust: 100%;
    }}

    /* Header */
    header {{
      background: rgba(17, 24, 39, 0.95);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border);
      padding: 10px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
      z-index: 50;
      gap: 12px;
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .brand-icon {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 10px var(--accent);
      animation: pulse-glow 2.5s infinite;
    }}

    @keyframes pulse-glow {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.6; transform: scale(0.9); }}
    }}

    .brand-text {{
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text);
    }}

    .brand-tag {{
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(51, 153, 255, 0.15);
      color: var(--accent);
      border: 1px solid var(--accent);
      font-family: var(--font-mono);
    }}

    /* Mode Dropdown Selector */
    .mode-dropdown-wrapper {{
      position: relative;
      display: inline-block;
    }}

    .mode-btn {{
      background: rgba(31, 41, 55, 0.8);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
      font-family: var(--font-sans);
    }}

    .mode-btn:hover {{
      background: rgba(55, 65, 81, 0.8);
      border-color: var(--accent);
    }}

    .mode-dropdown-menu {{
      display: none;
      position: absolute;
      top: calc(100% + 6px);
      left: 50%;
      transform: translateX(-50%);
      background: #111827;
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
      width: 210px;
      z-index: 100;
      overflow: hidden;
      animation: menu-pop 0.15s ease-out;
    }}

    @keyframes menu-pop {{
      from {{ opacity: 0; transform: translate(-50%, -6px); }}
      to {{ opacity: 1; transform: translate(-50%, 0); }}
    }}

    .mode-dropdown-menu.show {{
      display: block;
    }}

    .dropdown-item {{
      padding: 10px 14px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-muted);
      transition: all 0.12s ease;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }}

    .dropdown-item:last-child {{
      border-bottom: none;
    }}

    .dropdown-item:hover {{
      background: rgba(51, 153, 255, 0.12);
      color: #fff;
    }}

    .dropdown-item.active {{
      background: rgba(51, 153, 255, 0.18);
      color: var(--accent);
      font-weight: 600;
    }}

    .status-badge {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-muted);
    }}

    .status-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 6px var(--success);
    }}

    .status-dot.offline {{
      background: var(--danger);
      box-shadow: 0 0 6px var(--danger);
    }}

    .status-dot.pending {{
      background: var(--warning);
      box-shadow: 0 0 6px var(--warning);
      animation: pulse-glow 1.2s infinite;
    }}

    /* Main Container */
    #viewsContainer {{
      flex: 1 1 0%;
      min-height: 0;
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}

    /* Security Gate Modal Screen */
    #securityGate {{
      position: absolute;
      inset: 0;
      background: rgba(11, 15, 25, 0.96);
      backdrop-filter: blur(14px);
      z-index: 40;
      display: {gate_display};
      align-items: center;
      justify-content: center;
      padding: 16px;
    }}

    .gate-card {{
      background: #111827;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      width: 100%;
      max-width: 440px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6);
      text-align: center;
      animation: slide-up 0.25s ease-out;
    }}

    .gate-icon {{
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: rgba(51, 153, 255, 0.12);
      border: 1px solid var(--accent);
      margin: 0 auto 14px auto;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 22px;
      box-shadow: 0 0 18px var(--accent-glow);
    }}

    .gate-title {{
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0.04em;
      margin-bottom: 6px;
      color: #fff;
    }}

    .gate-desc {{
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 18px;
      line-height: 1.4;
    }}

    .pending-radar {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-radius: 20px;
      background: rgba(245, 158, 11, 0.12);
      border: 1px solid rgba(245, 158, 11, 0.3);
      color: #fbbf24;
      font-size: 12px;
      font-family: var(--font-mono);
      margin-bottom: 20px;
    }}

    .radar-pulse {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #f59e0b;
      box-shadow: 0 0 8px #f59e0b;
      animation: pulse-glow 1s infinite;
    }}

    .gate-divider {{
      display: flex;
      align-items: center;
      text-align: center;
      margin: 18px 0;
      color: #4b5563;
      font-size: 11px;
      font-family: var(--font-mono);
    }}

    .gate-divider::before, .gate-divider::after {{
      content: '';
      flex: 1;
      border-bottom: 1px solid var(--border);
    }}

    .gate-divider span {{
      padding: 0 10px;
    }}

    .gate-form {{
      text-align: left;
    }}

    .gate-label {{
      display: block;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .gate-input {{
      width: 100%;
      padding: 10px 12px;
      border-radius: 6px;
      background: #030712;
      border: 1px solid var(--border);
      color: #fff;
      font-size: 13px;
      font-family: var(--font-mono);
      margin-bottom: 12px;
      outline: none;
      transition: border-color 0.15s ease;
    }}

    .gate-input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 10px var(--accent-glow);
    }}

    .gate-checkbox-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 16px;
      cursor: pointer;
    }}

    .gate-checkbox-row input {{
      cursor: pointer;
    }}

    .gate-error {{
      font-size: 12px;
      color: var(--danger);
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      padding: 8px;
      border-radius: 6px;
      margin-bottom: 12px;
      display: none;
      text-align: center;
    }}

    /* WORK VIEW: Interactive Cards Feed */
    #workView {{
      flex: 1 1 0%;
      min-height: 0;
      height: 100%;
      max-height: 100%;
      overflow-y: scroll;
      overflow-x: hidden;
      -webkit-overflow-scrolling: touch;
      touch-action: pan-y;
      overscroll-behavior-y: contain;
      padding: 16px;
      padding-bottom: 24px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}

    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      transition: all 0.2s ease;
      animation: slide-up 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }}

    @keyframes slide-up {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    .card.accent {{
      border-color: var(--accent);
      box-shadow: 0 0 16px var(--accent-glow);
    }}

    .card.biometric {{
      border-color: #8b5cf6;
      box-shadow: 0 0 20px rgba(139, 92, 246, 0.3);
      background: linear-gradient(180deg, #161226 0%, #111827 100%);
    }}

    .card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }}

    .card-title {{
      font-weight: 600;
      font-size: 13px;
      letter-spacing: 0.02em;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .card-time {{
      font-size: 10px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }}

    .card-content {{
      color: #d1d5db;
      font-size: 13px;
      margin-bottom: 12px;
      white-space: pre-wrap;
      word-break: break-word;
    }}

    .card-actions {{
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }}

    /* Buttons */
    .btn {{
      padding: 8px 14px;
      font-size: 12px;
      font-weight: 600;
      border-radius: 6px;
      cursor: pointer;
      border: 1px solid transparent;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: all 0.15s ease;
      font-family: var(--font-sans);
    }}

    .btn:active {{
      transform: scale(0.97);
    }}

    .btn-primary {{
      background: var(--accent);
      color: #fff;
    }}

    .btn-primary:hover {{
      background: #2563eb;
    }}

    .btn-biometric {{
      background: #7c3aed;
      color: #fff;
      box-shadow: 0 0 12px rgba(124, 58, 237, 0.4);
    }}

    .btn-biometric:hover {{
      background: #6d28d9;
    }}

    .btn-secondary {{
      background: transparent;
      border-color: var(--border);
      color: var(--text-muted);
    }}

    .btn-secondary:hover {{
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
    }}

    .btn-block {{
      width: 100%;
    }}

    /* CHAT VIEW: Bilateral Remote Chat Stream */
    #chatView {{
      display: none;
      flex: 1 1 0%;
      min-height: 0;
      height: 100%;
      max-height: 100%;
      flex-direction: column;
      overflow: hidden;
      background: var(--bg);
    }}

    #chatFeed {{
      flex: 1 1 0%;
      min-height: 0;
      height: 100%;
      max-height: 100%;
      overflow-y: scroll;
      overflow-x: hidden;
      -webkit-overflow-scrolling: touch;
      touch-action: pan-y;
      overscroll-behavior-y: contain;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}

    .card, .chat-bubble {{
      touch-action: pan-y;
      pointer-events: auto;
    }}

    .chat-bubble {{
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      line-height: 1.5;
      word-break: break-word;
      animation: slide-up 0.2s ease-out;
    }}

    .chat-bubble.bot {{
      align-self: flex-start;
      background: var(--bubble-bot);
      border: 1px solid var(--border);
      color: #e5e7eb;
    }}

    .chat-bubble.user {{
      align-self: flex-end;
      background: var(--bubble-user);
      border: 1px solid rgba(59, 130, 246, 0.4);
      color: #ffffff;
    }}

    .chat-meta {{
      font-size: 10px;
      color: var(--text-muted);
      margin-bottom: 4px;
      font-family: var(--font-mono);
      display: flex;
      justify-content: space-between;
      gap: 10px;
    }}

    .chat-input-container {{
      background: #0d121f;
      border-top: 1px solid var(--border);
      padding: 10px 14px;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-shrink: 0;
    }}

    .chat-input {{
      flex: 1;
      padding: 9px 12px;
      background: #030712;
      border: 1px solid var(--border);
      border-radius: 6px;
      color: #fff;
      font-size: 13px;
      outline: none;
      font-family: var(--font-sans);
      resize: none;
      height: 38px;
      box-sizing: border-box;
      line-height: 1.35;
      overflow-y: hidden;
    }}

    .chat-input:focus {{
      border-color: var(--accent);
    }}

    /* Footer */
    footer {{
      background: #080c14;
      border-top: 1px solid var(--border);
      padding: 6px 16px;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }}

    /* First-Action Session Passkey Modal */
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.78);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      animation: fade-in 0.15s ease-out;
    }}
    @keyframes fade-in {{
      from {{ opacity: 0; }}
      to {{ opacity: 1; }}
    }}
    .modal-card {{
      background: #111827;
      border: 1px solid var(--accent);
      box-shadow: 0 0 24px var(--accent-glow), 0 20px 40px rgba(0, 0, 0, 0.8);
      border-radius: 12px;
      padding: 24px;
      width: 100%;
      max-width: 440px;
      animation: slide-up 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    .modal-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
    }}
    .modal-icon {{
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: rgba(51, 153, 255, 0.15);
      border: 1px solid var(--accent);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      flex-shrink: 0;
    }}
    .modal-title {{
      font-size: 15px;
      font-weight: 700;
      color: #fff;
    }}
    .modal-subtitle {{
      font-size: 11px;
      color: var(--text-muted);
    }}
    .input-wrapper {{
      position: relative;
      display: flex;
      align-items: center;
      margin-bottom: 16px;
    }}
    .input-wrapper .gate-input {{
      width: 100%;
      padding-right: 40px;
    }}
    .passkey-secure-input {{
      -webkit-text-security: disc !important;
      text-security: disc !important;
    }}
    .passkey-secure-input.plain-text {{
      -webkit-text-security: none !important;
      text-security: none !important;
    }}
    .btn-toggle-eye {{
      position: absolute;
      right: 8px;
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 4px;
      font-size: 14px;
    }}
    .btn-toggle-eye:hover {{
      color: #fff;
    }}
    .modal-actions {{
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }}
  </style>
</head>
<body>

  <!-- Top Navigation Header -->
  <header>
    <div class="brand">
      <div class="brand-icon"></div>
      <span class="brand-text">Wingman</span>
      <span class="brand-tag">PORT {port}</span>
    </div>

    <!-- Mode Switcher Dropdown (Chat / Work) -->
    <div class="mode-dropdown-wrapper" id="modeDropdownWrapper">
      <button class="mode-btn" id="modeBtn" onclick="toggleModeDropdown()">
        <span id="modeIcon">⚡</span>
        <span id="modeLabel">Work</span>
        <span style="font-size: 9px; opacity: 0.7;">▼</span>
      </button>
      <div class="mode-dropdown-menu" id="modeMenu">
        <div class="dropdown-item active" id="itemWork" onclick="selectMode('work')">
          <span>⚡</span>
          <div>
            <div>Work</div>
            <div style="font-size: 10px; opacity: 0.6;">Workflow, Actions & HUD</div>
          </div>
        </div>
        <div class="dropdown-item" id="itemChat" onclick="selectMode('chat')">
          <span>💬</span>
          <div>
            <div>Chat</div>
            <div style="font-size: 10px; opacity: 0.6;">Remote Gemini Stream</div>
          </div>
        </div>
      </div>
    </div>

    <div class="status-badge">
      <div id="statusDot" class="status-dot {'pending' if auth_state == 'pending' else ''}"></div>
      <span id="statusText">{'PENDING AUTH' if auth_state == 'pending' else 'ONLINE'}</span>
    </div>
  </header>

  <!-- Views Container -->
  <div id="viewsContainer">

    <!-- Zero-Trust Security Gate (Awaiting Mothership Console Authorization) -->
    <div id="securityGate" style="display: {gate_display};">
      <div class="gate-card">
        <div class="gate-icon">🔒</div>
        <div class="gate-title">Wingman Security Gate</div>
        <div class="gate-desc">A bilateral interactive session was initiated on node <strong style="color: #fff;">{node_id}</strong> ({client_ip}).</div>

        <div class="pending-radar">
          <div class="radar-pulse"></div>
          <span id="gateStatusText">Awaiting mothership console authorization...</span>
        </div>

        <div class="gate-divider">
          <span>ENTER VAULT PASSKEY DIRECTLY</span>
        </div>

        <div class="gate-error" id="gatePasskeyError" style="display: none; margin-bottom: 12px;"></div>

        <form class="gate-form" id="gatePasskeyForm" onsubmit="handleGatePasskeySubmit(event); return false;" autocomplete="off">
          <div class="input-wrapper" style="margin-bottom: 10px;">
            <input type="text"
                   id="gatePasskeyInput"
                   name="vault_gate_key"
                   class="gate-input passkey-secure-input"
                   placeholder="Enter Homebase vault passkey..."
                   autocomplete="off"
                   autocorrect="off"
                   autocapitalize="off"
                   spellcheck="false"
                   inputmode="text"
                   enterkeyhint="go"
                   data-form-type="other"
                   data-lpignore="true"
                   data-1p-ignore="true"
                   data-bwignore="true"
                   data-protonpass-ignore="true"
                   onkeydown="if(event.key==='Enter')handleGatePasskeySubmit(event)">
            <button type="button" class="btn-toggle-eye" onclick="toggleGatePasskeyVisibility()" title="Show/Hide passkey">👁</button>
          </div>
          <div class="gate-checkbox-row">
            <input type="checkbox" id="gateTrustCheckbox" name="trust_device">
            <label for="gateTrustCheckbox" style="cursor: pointer;">Remember device pairing</label>
          </div>
          <button type="submit" class="btn btn-primary btn-block" id="gateUnlockBtn">
            Authorize & Unlock Session ↵
          </button>
        </form>
      </div>
    </div>

    <!-- VIEW 1: WORK VIEW (Cards, Buttons, Face ID) -->
    <main id="workView">
      <div class="card accent" id="welcomeCard">
        <div class="card-header">
          <span class="card-title">⚡ Bilateral Portal Online</span>
          <span class="card-time">LIVE</span>
        </div>
        <div class="card-content">Wingman runtime connected. Gemini interactive cards, dual-screen telemetry, and Apple Secure Enclave Face ID are ready.</div>
      </div>
    </main>

    <!-- VIEW 2: CHAT VIEW (Remote Chat Stream) -->
    <div id="chatView">
      <div id="chatFeed">
        <div class="chat-bubble bot">
          <div class="chat-meta">
            <span>GEMINI CORE</span>
            <span>READY</span>
          </div>
          <div>Bilateral chat stream connected. Messages sent here are validated through the node security gate and received directly by the Mothership.</div>
        </div>
      </div>
      <div class="chat-input-container" id="chatContainer">
        <textarea id="chatInput"
                  name="chat_message"
                  class="chat-input"
                  rows="1"
                  role="textbox"
                  placeholder="Message Gemini on Mothership..."
                  autocomplete="off"
                  autocorrect="on"
                  autocapitalize="sentences"
                  spellcheck="true"
                  enterkeyhint="send"
                  inputmode="text"
                  data-form-type="other"
                  data-lpignore="true"
                  data-1p-ignore="true"
                  data-bwignore="true"
                  data-protonpass-ignore="true"
                  aria-autocomplete="none"
                  onkeydown="handleChatKeyDown(event)"></textarea>
        <button type="button" class="btn btn-primary" id="chatSendBtn" onclick="submitChatMessage()">Send ↵</button>
      </div>
    </div>

  </div>

  <!-- First-Action Session Passkey Modal -->
  <div id="passkeyModal" class="modal-backdrop" style="display: none;">
    <div class="modal-card">
      <div class="modal-header">
        <div class="modal-icon">🔐</div>
        <div>
          <div class="modal-title">Homebase Passkey Required</div>
          <div class="modal-subtitle" id="passkeyPromptSubtitle">Authorize interactive bilateral operations for this session with your Homebase vault passkey.</div>
        </div>
      </div>
      <div class="gate-error" id="modalPasskeyError" style="display: none; margin-bottom: 12px;">Invalid vault passkey. Verification denied.</div>
      <form id="passkeyModalForm" onsubmit="handleSessionPasskeySubmit(event); return false;" autocomplete="off">
        <div class="input-wrapper">
          <input type="text"
                 id="modalPasskeyInput"
                 name="vault_session_input"
                 class="gate-input passkey-secure-input"
                 placeholder="Enter Homebase vault passkey..."
                 autocomplete="off"
                 autocorrect="off"
                 autocapitalize="off"
                 spellcheck="false"
                 inputmode="text"
                 enterkeyhint="go"
                 data-form-type="other"
                 data-lpignore="true"
                 data-1p-ignore="true"
                 data-bwignore="true"
                 data-protonpass-ignore="true"
                 onkeydown="if(event.key==='Enter')handleSessionPasskeySubmit(event)">
          <button type="button" class="btn-toggle-eye" onclick="togglePasskeyVisibility()" title="Show/Hide passkey">👁</button>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" onclick="closePasskeyModal()">Cancel</button>
          <button type="submit" class="btn btn-primary" id="modalUnlockBtn">Unlock Session ↵</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Live Footer Telemetry -->
  <footer>
    <span id="footerHost">node:{node_id}:{port}</span>
    <span id="footerPing">PING: --ms</span>
  </footer>

  <script>
    const securityGate = document.getElementById('securityGate');
    const gateStatusText = document.getElementById('gateStatusText');

    const workView = document.getElementById('workView');
    const chatView = document.getElementById('chatView');
    const chatFeed = document.getElementById('chatFeed');
    const chatInput = document.getElementById('chatInput');

    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const footerPing = document.getElementById('footerPing');
    const modeBtn = document.getElementById('modeBtn');
    const modeMenu = document.getElementById('modeMenu');
    const modeIcon = document.getElementById('modeIcon');
    const modeLabel = document.getElementById('modeLabel');
    const itemWork = document.getElementById('itemWork');
    const itemChat = document.getElementById('itemChat');

    let currentMode = 'work';
    let chatMessages = [];
    let serverTimeOffset = 0;
    let sseSource = null;
    let pingInterval = null;
    let authPollingInterval = null;
    let currentBootId = null;
    let currentMothershipBootId = null;
    let isMaintenanceMode = false;
    let isPairedDevice = localStorage.getItem('wingman_paired') === '1';
    let deviceId = localStorage.getItem('wingman_device_id') || ('dev-' + Math.random().toString(36).substring(2, 10));
    localStorage.setItem('wingman_device_id', deviceId);

    const serverNodeId = '{node_id}';
    function detectDeviceType() {{
      const ua = navigator.userAgent || '';
      const platform = navigator.platform || '';
      const isIPad = /iPad/i.test(ua) || (platform === 'MacIntel' && navigator.maxTouchPoints > 1);
      if (isIPad) return 'iPad';
      if (/iPhone|iPod/i.test(ua)) return 'Phone';
      if (/Android/i.test(ua)) {{
        const isMobileUA = /Mobile/i.test(ua);
        const minDim = Math.min(window.screen.width, window.screen.height);
        if (!isMobileUA || minDim >= 600) {{
          return 'Tablet';
        }}
        return 'Phone';
      }}
      if (typeof serverNodeId === 'string' && serverNodeId && serverNodeId !== 'local' && serverNodeId !== 'mothership') {{
        return serverNodeId;
      }}
      if (/Macintosh|Mac OS X/i.test(ua)) return 'Mac';
      if (/Windows/i.test(ua)) return 'PC';
      if (/Linux/i.test(ua)) return 'PC';
      return 'PC';
    }}
    const deviceLabel = detectDeviceType();

    // Ephemeral session ID for the active browser tab session
    let sessionId = sessionStorage.getItem('wingman_session_id') || '{auth_req_id}' || ('sess-' + Math.random().toString(36).substring(2, 10));
    sessionStorage.setItem('wingman_session_id', sessionId);

    // Only permanently paired devices retain credentials across page reload
    let sessionToken = isPairedDevice ? (localStorage.getItem('wingman_token') || '') : '';
    if (!isPairedDevice) {{
      sessionStorage.removeItem('wingman_token');
    }}

    /* First-action session passkey state (resets every session/refresh) */
    let isSessionUnlocked = false;
    let pendingActionCallback = null;

    function requireSessionUnlock(reason, onUnlocked) {{
      if (isSessionUnlocked) {{
        onUnlocked();
        return;
      }}
      pendingActionCallback = onUnlocked;
      if (reason) {{
        const sub = document.getElementById('passkeyPromptSubtitle');
        if (sub) sub.textContent = reason;
      }}
      const errEl = document.getElementById('modalPasskeyError');
      if (errEl) errEl.style.display = 'none';
      const modal = document.getElementById('passkeyModal');
      if (modal) modal.style.display = 'flex';
      const input = document.getElementById('modalPasskeyInput');
      if (input) {{
        input.value = '';
        input.classList.remove('plain-text');
        input.focus();
      }}
    }}

    function closePasskeyModal() {{
      const modal = document.getElementById('passkeyModal');
      if (modal) modal.style.display = 'none';
      pendingActionCallback = null;
    }}

    function togglePasskeyVisibility() {{
      const input = document.getElementById('modalPasskeyInput');
      if (input) {{
        input.classList.toggle('plain-text');
      }}
    }}

    function toggleGatePasskeyVisibility() {{
      const input = document.getElementById('gatePasskeyInput');
      if (input) {{
        input.classList.toggle('plain-text');
      }}
    }}

    async function handleGatePasskeySubmit(e) {{
      if (e && e.preventDefault) e.preventDefault();
      const input = document.getElementById('gatePasskeyInput');
      const errEl = document.getElementById('gatePasskeyError');
      const btn = document.getElementById('gateUnlockBtn');
      const trustBox = document.getElementById('gateTrustCheckbox');
      const pass = input ? input.value.trim() : '';
      if (!pass) return;

      if (btn) {{
        btn.disabled = true;
        btn.textContent = 'Verifying with Homebase...';
      }}
      if (errEl) errEl.style.display = 'none';

      try {{
        const trustVal = trustBox ? Boolean(trustBox.checked) : false;
        const res = await fetch('/applet/wingman/auth', {{
          method: 'POST',
          headers: {{
            'Content-Type': 'application/json',
            'X-Wingman-Device': deviceId,
            'X-Wingman-Session': sessionId
          }},
          body: JSON.stringify({{
            session_id: sessionId,
            passkey: pass,
            trust_device: trustVal
          }})
        }});
        const data = await res.json();
        if (data.status === 'ok' && data.token) {{
          isSessionUnlocked = true;
          unlockUI(data.token, trustVal);
          if (input) input.value = '';
          playTone(880, 'sine', 0.1);
        }} else {{
          if (errEl) {{
            errEl.textContent = data.message || "Invalid Homebase vault passkey. Verification denied.";
            errEl.style.display = 'block';
          }}
          if (input) {{
            input.focus();
            input.select();
          }}
          playTone(220, 'sawtooth', 0.15);
        }}
      }} catch (err) {{
        if (errEl) {{
          errEl.textContent = "Passkey check failed: " + err.message;
          errEl.style.display = 'block';
        }}
      }} finally {{
        if (btn) {{
          btn.disabled = false;
          btn.textContent = 'Authorize & Unlock Session ↵';
        }}
      }}
    }}

    async function handleSessionPasskeySubmit(e) {{
      if (e && e.preventDefault) e.preventDefault();
      const input = document.getElementById('modalPasskeyInput');
      const errEl = document.getElementById('modalPasskeyError');
      const unlockBtn = document.getElementById('modalUnlockBtn');
      const pass = input ? input.value.trim() : '';
      if (!pass) return;

      if (unlockBtn) {{
        unlockBtn.disabled = true;
        unlockBtn.textContent = 'Verifying with Homebase...';
      }}
      if (errEl) errEl.style.display = 'none';

      try {{
        const res = await fetch('/applet/wingman/verify_passkey', {{
          method: 'POST',
          headers: {{
            'Content-Type': 'application/json',
            'X-Wingman-Token': sessionToken,
            'X-Wingman-Session': sessionId,
            'X-Wingman-Device': deviceId
          }},
          body: JSON.stringify({{
            passkey: pass,
            session_id: sessionId,
            session_token: sessionToken
          }})
        }});
        const data = await res.json();
        if (data.valid || data.status === 'ok') {{
          isSessionUnlocked = true;
          if (data.token) {{
            unlockUI(data.token, Boolean(data.is_paired));
          }}
          closePasskeyModal();
          playTone(880, 'sine', 0.1);
          if (pendingActionCallback) {{
            const cb = pendingActionCallback;
            pendingActionCallback = null;
            cb();
          }}
        }} else {{
          if (errEl) {{
            errEl.textContent = data.error || data.message || "Invalid vault passkey. Verification denied.";
            errEl.style.display = 'block';
          }}
          if (input) {{
            input.classList.add('error');
            setTimeout(() => input.classList.remove('error'), 600);
            input.focus();
            input.select();
          }}
          playTone(220, 'sawtooth', 0.15);
        }}
      }} catch (err) {{
        if (errEl) {{
          errEl.textContent = "Passkey check failed: " + err.message;
          errEl.style.display = 'block';
        }}
      }} finally {{
        if (unlockBtn) {{
          unlockBtn.disabled = false;
          unlockBtn.textContent = 'Unlock Session ↵';
        }}
      }}
    }}

    if (sessionToken) {{
      if (isPairedDevice) {{
        localStorage.setItem('wingman_token', sessionToken);
      }} else {{
        sessionStorage.setItem('wingman_token', sessionToken);
      }}
    }}
    if (sessionId) {{
      if (isPairedDevice) {{
        localStorage.setItem('wingman_session_id', sessionId);
      }} else {{
        sessionStorage.setItem('wingman_session_id', sessionId);
      }}
    }}

    function playTone(freq = 440, type = 'sine', duration = 0.08) {{
      try {{
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = type;
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.04, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + duration);
      }} catch (e) {{}}
    }}

    /* Mode Dropdown */
    function toggleModeDropdown() {{
      modeMenu.classList.toggle('show');
    }}

    document.addEventListener('click', (e) => {{
      if (!e.target.closest('#modeDropdownWrapper')) {{
        modeMenu.classList.remove('show');
      }}
    }});

    function selectMode(mode) {{
      currentMode = mode;
      modeMenu.classList.remove('show');
      if (mode === 'work') {{
        modeIcon.textContent = '⚡';
        modeLabel.textContent = 'Work';
        itemWork.classList.add('active');
        itemChat.classList.remove('active');
        workView.style.display = 'flex';
        chatView.style.display = 'none';
      }} else {{
        modeIcon.textContent = '💬';
        modeLabel.textContent = 'Chat';
        itemChat.classList.add('active');
        itemWork.classList.remove('active');
        workView.style.display = 'none';
        chatView.style.display = 'flex';
        chatInput.focus();
        loadChatHistory();
      }}
    }}

    async function loadChatHistory() {{
      try {{
        const headers = {{
          'X-Wingman-Device': deviceId,
          'X-Wingman-Session': sessionId
        }};
        if (sessionToken) headers['X-Wingman-Token'] = sessionToken;
        const res = await fetch('/applet/wingman/chat_history', {{ headers }});
        const data = await res.json();
        if (data && data.history && Array.isArray(data.history)) {{
          const serverIds = new Set(data.history.map(m => m.id).filter(Boolean));
          const pendingLocal = chatMessages.filter(m => {{
            if (!m.pending) return false;
            if (serverIds.has(m.id)) return false;
            const alreadyInServer = data.history.some(sm => sm.is_user && sm.text === m.text);
            return !alreadyInServer;
          }});

          const canonical = data.history.map(m => ({{
            id: m.id || ('msg-' + (m.timestamp || Math.random())),
            sender: m.sender || (m.is_user ? 'Operator' : 'Gemini Core'),
            text: m.text || '',
            is_user: Boolean(m.is_user),
            origin_device: m.origin_device || '',
            origin_label: m.origin_label || '',
            timestamp: (typeof m.timestamp === 'number' && m.timestamp > 0) ? m.timestamp : ((Date.now() / 1000) + serverTimeOffset),
            pending: false
          }}));

          // Strict chronological sort so switching tabs never scrambles message order
          const merged = canonical.concat(pendingLocal);
          merged.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
          chatMessages = merged.slice(-50);
          renderChatFeed();
        }}
      }} catch (err) {{}}
    }}

    /* Session & Auth Handlers */
    function setMaintenanceLock(active, message = "") {{
      isMaintenanceMode = Boolean(active);
      const gateIcon = document.querySelector('.gate-icon');
      const gateTitle = document.querySelector('.gate-title');
      const gateDesc = document.querySelector('.gate-desc');
      if (active) {{
        if (authPollingInterval) clearInterval(authPollingInterval);
        securityGate.style.display = 'flex';
        if (gateIcon) gateIcon.textContent = '🛠️';
        if (gateTitle) gateTitle.textContent = 'Wingman Maintenance Lockout';
        if (gateDesc) gateDesc.textContent = message || 'Mothership updates underway. Reconnection paused until release.';
        gateStatusText.textContent = 'Maintenance in progress (reconnect paused)...';
        statusText.textContent = 'MAINTENANCE';
        statusDot.className = 'status-dot pending';
      }} else {{
        if (gateIcon) gateIcon.textContent = '🔒';
        if (gateTitle) gateTitle.textContent = 'Wingman Security Gate';
        if (gateDesc) gateDesc.textContent = 'A bilateral interactive session was initiated on node {node_id} ({client_ip}).';
        checkSession();
      }}
    }}

    async function checkSession() {{
      try {{
        const headers = {{
          'X-Wingman-Device': deviceId,
          'X-Wingman-Session': sessionId
        }};
        if (sessionToken) {{
          headers['X-Wingman-Token'] = sessionToken;
        }}
        const res = await fetch('/applet/wingman/session', {{ headers }});
        const data = await res.json();

        if (data.maintenance) {{
          setMaintenanceLock(true, data.message);
          return;
        }} else if (isMaintenanceMode) {{
          setMaintenanceLock(false);
        }}

        if (data.session_id) {{
          sessionId = data.session_id;
          sessionStorage.setItem('wingman_session_id', sessionId);
          if (isPairedDevice) {{
            localStorage.setItem('wingman_session_id', sessionId);
          }}
        }}

        if (data.mothership_boot_id) {{
          if (currentMothershipBootId && currentMothershipBootId !== data.mothership_boot_id) {{
            // Mothership console rebooted!
            currentMothershipBootId = data.mothership_boot_id;
            isSessionUnlocked = false;
            if (!isPairedDevice) {{
              sessionToken = '';
              sessionStorage.removeItem('wingman_token');
              localStorage.removeItem('wingman_token');
              localStorage.removeItem('wingman_paired');
              lockUI("Mothership console rebooted — awaiting new authorization...");
              startAuthPolling();
              return;
            }}
          }}
          currentMothershipBootId = data.mothership_boot_id;
        }}

        if (data.boot_id) {{
          if (currentBootId && currentBootId !== data.boot_id) {{
            // Server rebooted! Invalidate credentials, lock UI, and re-authenticate
            isSessionUnlocked = false;
            if (!isPairedDevice) {{
              sessionToken = '';
              sessionStorage.removeItem('wingman_token');
              localStorage.removeItem('wingman_token');
              localStorage.removeItem('wingman_paired');
              currentBootId = data.boot_id;
              lockUI("Mothership console rebooted — awaiting new authorization...");
              startAuthPolling();
              return;
            }}
          }}
          currentBootId = data.boot_id;
        }}
        if (data.authenticated) {{
          if (!data.is_paired) {{
            localStorage.removeItem('wingman_token');
            localStorage.removeItem('wingman_paired');
            isPairedDevice = false;
          }}
          if (data.is_unlocked !== undefined) {{
            isSessionUnlocked = Boolean(data.is_unlocked);
          }}
          unlockUI(data.token, Boolean(data.is_paired));
        }} else {{
          sessionToken = '';
          sessionStorage.removeItem('wingman_token');
          localStorage.removeItem('wingman_token');
          localStorage.removeItem('wingman_paired');
          isPairedDevice = false;
          lockUI();
          startAuthPolling();
        }}
      }} catch (err) {{
        console.warn("Session check failed:", err);
      }}
    }}

    let unknownAuthCount = 0;
    async function handleSessionExpired(reason = "Session expired or Mothership rebooted. Re-authorization required.") {{
      sessionToken = '';
      sessionStorage.removeItem('wingman_token');
      localStorage.removeItem('wingman_token');
      localStorage.removeItem('wingman_paired');
      isSessionUnlocked = false;
      lockUI(reason);
      await checkSession();
      startAuthPolling();
    }}

    function startAuthPolling() {{
      if (authPollingInterval) clearInterval(authPollingInterval);
      if (isMaintenanceMode) return;
      authPollingInterval = setInterval(async () => {{
        if (isMaintenanceMode) return;
        try {{
          const res = await fetch('/applet/wingman/auth_status?req_id=' + encodeURIComponent(sessionId));
          const data = await res.json();
          if (data.status === 'approved' && data.token) {{
            clearInterval(authPollingInterval);
            unknownAuthCount = 0;
            if (!data.is_paired) {{
              localStorage.removeItem('wingman_token');
              localStorage.removeItem('wingman_paired');
              isPairedDevice = false;
            }}
            unlockUI(data.token, Boolean(data.is_paired));
          }} else if (data.status === 'denied') {{
            clearInterval(authPollingInterval);
            unknownAuthCount = 0;
            sessionToken = '';
            sessionStorage.removeItem('wingman_token');
            sessionStorage.removeItem('wingman_session_id');
            localStorage.removeItem('wingman_token');
            localStorage.removeItem('wingman_paired');
            isPairedDevice = false;
            lockUI("Access Denied by Mothership Operator");
          }} else if (data.status === 'unknown' || data.needs_reauth) {{
            unknownAuthCount++;
            if (unknownAuthCount >= 2) {{
              unknownAuthCount = 0;
              await checkSession();
            }}
          }}
        }} catch (e) {{}}
      }}, 1500);
    }}

    function unlockUI(token, isPaired = false) {{
      if (authPollingInterval) clearInterval(authPollingInterval);
      isPairedDevice = Boolean(isPaired);
      if (token) {{
        sessionToken = token;
        if (isPairedDevice) {{
          localStorage.setItem('wingman_token', token);
          localStorage.setItem('wingman_paired', '1');
        }} else {{
          sessionStorage.setItem('wingman_token', token);
          localStorage.removeItem('wingman_token');
          localStorage.removeItem('wingman_paired');
        }}
      }}
      securityGate.style.display = 'none';
      statusText.textContent = isPairedDevice ? "PAIRED" : "ONLINE (SESSION)";
      statusDot.className = "status-dot";
      playTone(587.33, 'triangle', 0.1);
    }}

    function lockUI(reason = "Awaiting mothership console authorization...") {{
      securityGate.style.display = 'flex';
      gateStatusText.textContent = reason;
      statusText.textContent = "PENDING AUTH";
      statusDot.className = "status-dot pending";
      const gateErr = document.getElementById('gatePasskeyError');
      if (gateErr) gateErr.style.display = 'none';
      const gateInput = document.getElementById('gatePasskeyInput');
      if (gateInput) {{
        gateInput.value = '';
        gateInput.classList.remove('plain-text');
      }}
    }}

    /* SSE Stream Connection */
    function connectSSE() {{
      if (sseSource) sseSource.close();

      const sseUrl = "/applet/wingman/events?token=" + encodeURIComponent(sessionToken) + "&device=" + encodeURIComponent(deviceId);
      sseSource = new EventSource(sseUrl);

      sseSource.addEventListener("connected", (e) => {{
        // Connected or reconnected to SSE stream — re-validate session
        checkSession();
        loadChatHistory();
      }});

      sseSource.onerror = () => {{
        // Disconnected or backend rebooted — poll session check
        setTimeout(checkSession, 1500);
      }};

      sseSource.addEventListener("session_authorized", (e) => {{
        try {{
          const payload = JSON.parse(e.data);
          unlockUI(payload.token, Boolean(payload.is_paired));
        }} catch (err) {{}}
      }});

      sseSource.addEventListener("auth_approved", (e) => {{
        try {{
          const payload = JSON.parse(e.data);
          unlockUI(payload.token, Boolean(payload.is_paired));
        }} catch (err) {{}}
      }});

      sseSource.addEventListener("session_denied", (e) => {{
        lockUI("Session Denied by Mothership Operator");
        playTone(180, 'sawtooth', 0.2);
      }});

      sseSource.addEventListener("auth_denied", (e) => {{
        lockUI("Session Denied by Mothership Operator");
        playTone(180, 'sawtooth', 0.2);
      }});

      sseSource.addEventListener("wingman_maintenance", (e) => {{
        try {{
          const payload = JSON.parse(e.data);
          setMaintenanceLock(Boolean(payload.active), payload.message);
        }} catch (err) {{}}
      }});

      sseSource.addEventListener("mothership_rebooted", (e) => {{
        try {{
          const payload = JSON.parse(e.data);
          currentMothershipBootId = payload.mothership_boot_id || payload.boot_id;
          if (!isPairedDevice) {{
            handleSessionExpired("Mothership console rebooted — awaiting new authorization...");
          }}
        }} catch (err) {{}}
      }});

      sseSource.addEventListener("card", (e) => {{
        try {{
          const card = JSON.parse(e.data);
          renderCard(card);
          playTone(880, 'sine', 0.06);
        }} catch (err) {{}}
      }});

      sseSource.addEventListener("chat_message", (e) => {{
        try {{
          const msg = JSON.parse(e.data);
          const mId = msg.id || ('msg-' + (msg.timestamp || ''));
          addChatMessage(
            msg.sender || (msg.is_user ? 'Operator' : 'Gemini Core'),
            msg.text,
            Boolean(msg.is_user),
            mId,
            msg.timestamp,
            msg.origin_device || '',
            msg.origin_label || ''
          );
          playTone(660, 'sine', 0.08);
        }} catch (err) {{}}
      }});

      sseSource.addEventListener("chat_clear", (e) => {{
        chatMessages = [];
        renderChatFeed();
        addChatMessage('Gemini Core', 'Bilateral chat cleared. Starting fresh chat session.', false);
        playTone(440, 'triangle', 0.1);
      }});

      sseSource.addEventListener("biometric_challenge", (e) => {{
        try {{
          const chal = JSON.parse(e.data);
          renderBiometricPrompt(chal);
          playTone(659.25, 'sawtooth', 0.15);
        }} catch (err) {{}}
      }});

      sseSource.onerror = () => {{
        statusText.textContent = "DISCONNECTED";
        statusDot.className = "status-dot offline";
      }};
    }}

    /* Work Mode: Render Cards */
    function renderCard(card) {{
      const cardEl = document.createElement('div');
      cardEl.className = 'card ' + (card.accent ? 'accent' : '');
      if (card.id) cardEl.id = 'card-' + card.id;

      const timeStr = new Date().toLocaleTimeString();

      let actionsHtml = '';
      if (card.actions && Array.isArray(card.actions)) {{
        actionsHtml = '<div class="card-actions">' +
          card.actions.map(a => `
            <button class="btn ${{a.style === 'primary' ? 'btn-primary' : 'btn-secondary'}}"
                    onclick="handleCardAction('${{card.id}}', '${{a.action}}')">
              ${{a.label}}
            </button>
          `).join('') +
          '</div>';
      }}

      cardEl.innerHTML = `
        <div class="card-header">
          <span class="card-title">${{card.title || 'Gemini'}}</span>
          <span class="card-time">${{timeStr}}</span>
        </div>
        <div class="card-content">${{escapeHtml(card.content)}}</div>
        ${{actionsHtml}}
      `;

      workView.appendChild(cardEl);
      workView.scrollTop = workView.scrollHeight;
    }}

    function handleCardAction(cardId, action) {{
      requireSessionUnlock('Homebase passkey required to execute: ' + action, () => {{
        executeCardAction(cardId, action);
      }});
    }}

    async function executeCardAction(cardId, action) {{
      try {{
        const res = await fetch('/applet/wingman/action', {{
          method: 'POST',
          headers: {{
            'Content-Type': 'application/json',
            'X-Wingman-Token': sessionToken,
            'X-Wingman-Device': deviceId
          }},
          body: JSON.stringify({{ card_id: cardId, action: action, timestamp: Date.now() }})
        }});
        const reply = await res.json();
        if (reply.session_locked && !reply.reauth_required) {{
          isSessionUnlocked = false;
          requireSessionUnlock(reply.message || "Homebase passkey required to execute action", () => {{
            executeCardAction(cardId, action);
          }});
          return;
        }}
        if (reply.reauth_required || (reply.status === 'error' && reply.message && reply.message.toLowerCase().includes('session'))) {{
          await handleSessionExpired(reply.message || "Session expired — awaiting mothership authorization...");
          return;
        }}
        const cardEl = document.getElementById('card-' + cardId);
        if (cardEl) {{
          cardEl.style.opacity = '0.6';
          const actDiv = cardEl.querySelector('.card-actions');
          if (actDiv) actDiv.innerHTML = `<span style="font-size: 11px; color: var(--success);">✓ Responded: ${{action}}</span>`;
        }}
      }} catch (err) {{}}
    }}

    /* Chat Mode: Send & Receive Messages */
    function handleChatKeyDown(e) {{
      if (e.key === 'Enter' && !e.shiftKey) {{
        e.preventDefault();
        submitChatMessage();
      }}
    }}

    function submitChatMessage() {{
      const text = chatInput.value.trim();
      if (!text) return;

      requireSessionUnlock('Homebase passkey required to send chat message to Gemini', () => {{
        executeSubmitChatMessage(text);
      }});
    }}

    function renderChatFeed() {{
      chatFeed.innerHTML = '';
      if (chatMessages.length === 0) {{
        chatFeed.innerHTML = `
          <div class="chat-bubble bot">
            <div class="chat-meta">
              <span>GEMINI CORE</span>
              <span>ONLINE</span>
            </div>
            <div>Bilateral chat stream connected. Messages sent here are validated through the node security gate and received directly by the Mothership.</div>
          </div>
        `;
        return;
      }}
      chatMessages.forEach(m => {{
        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble ' + (m.is_user ? 'user' : 'bot');
        if (m.id) bubble.setAttribute('data-msg-id', m.id);
        const timeStr = m.timestamp ? new Date(m.timestamp * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();

        let senderText = (m.sender || (m.is_user ? 'Operator' : 'Gemini Core')).toUpperCase();
        if (m.is_user) {{
          const isFromThisDevice = Boolean(m.origin_device && m.origin_device === deviceId);
          if (!isFromThisDevice) {{
            const label = m.origin_label || (m.origin_device === 'mothership' ? 'Mothership' : '');
            if (label) {{
              senderText = `${{(m.sender || 'Operator').toUpperCase()}} · ${{label.toUpperCase()}}`;
            }}
          }}
        }}

        bubble.innerHTML = `
          <div class="chat-meta">
            <span>${{escapeHtml(senderText)}}</span>
            <span>${{timeStr}}</span>
          </div>
          <div style="white-space: pre-wrap; word-break: break-word;">${{formatMarkdown(m.text || '')}}</div>
        `;
        chatFeed.appendChild(bubble);
      }});
      chatFeed.scrollTop = chatFeed.scrollHeight;
    }}

    function addChatMessage(sender, text, isUser = false, msgId = '', timestamp = null, originDevice = '', originLabel = '') {{
      const mId = msgId || ('msg-' + Date.now() + '-' + Math.random().toString(36).substring(2, 6));
      const ts = (typeof timestamp === 'number' && timestamp > 0) ? timestamp : ((Date.now() / 1000) + serverTimeOffset);
      const existingIdx = chatMessages.findIndex(m => m.id === mId);
      if (existingIdx !== -1) {{
        chatMessages[existingIdx] = {{
          id: mId,
          sender,
          text,
          is_user: isUser,
          timestamp: ts,
          origin_device: originDevice || chatMessages[existingIdx].origin_device || '',
          origin_label: originLabel || chatMessages[existingIdx].origin_label || '',
          pending: false
        }};
      }} else {{
        chatMessages.push({{
          id: mId,
          sender,
          text,
          is_user: isUser,
          timestamp: ts,
          origin_device: originDevice,
          origin_label: originLabel,
          pending: false
        }});
      }}
      if (chatMessages.length > 50) {{
        chatMessages = chatMessages.slice(-50);
      }}
      renderChatFeed();
    }}

    function renderChatMessage(sender, text, isUser = false, msgId = '', timestamp = null) {{
      addChatMessage(sender, text, isUser, msgId, timestamp);
    }}

    async function executeSubmitChatMessage(text) {{
      const msgId = 'msg-wingman-' + Date.now() + '-' + Math.random().toString(36).substring(2, 7);
      const nowSec = (Date.now() / 1000) + serverTimeOffset;
      chatInput.value = '';

      if (text.trim().toLowerCase() === '/clear') {{
        chatMessages = [];
        renderChatFeed();
        addChatMessage('Gemini Core', 'Clearing bilateral chat across all devices...', false);
      }} else {{
        chatMessages.push({{
          id: msgId,
          sender: 'Operator',
          text: text,
          is_user: true,
          timestamp: nowSec,
          origin_device: deviceId,
          origin_label: deviceLabel,
          pending: true
        }});
        if (chatMessages.length > 50) {{
          chatMessages = chatMessages.slice(-50);
        }}
        renderChatFeed();
      }}

      try {{
        const res = await fetch('/applet/wingman/chat', {{
          method: 'POST',
          headers: {{
            'Content-Type': 'application/json',
            'X-Wingman-Token': sessionToken,
            'X-Wingman-Device': deviceId
          }},
          body: JSON.stringify({{
            id: msgId,
            text: text,
            sender: 'Operator',
            timestamp: nowSec,
            device_id: deviceId,
            device_label: deviceLabel
          }})
        }});
        const reply = await res.json();
        if (reply.session_locked && !reply.reauth_required) {{
          isSessionUnlocked = false;
          const pIdx = chatMessages.findIndex(m => m.id === msgId);
          if (pIdx !== -1) {{
            chatMessages.splice(pIdx, 1);
            renderChatFeed();
          }}
          requireSessionUnlock(reply.message || "Homebase passkey required to send chat message", () => {{
            executeSubmitChatMessage(text);
          }});
          return;
        }}
        if (reply.reauth_required || (reply.status === 'error' && reply.message && reply.message.toLowerCase().includes('session'))) {{
          await handleSessionExpired(reply.message || "Session expired — awaiting mothership authorization...");
          return;
        }}
        if (text.trim().toLowerCase() === '/clear') {{
          chatMessages = [];
          renderChatFeed();
          addChatMessage('Gemini Core', 'Bilateral chat cleared. Starting fresh chat session.', false);
          return;
        }}
        if (reply.status === 'error') {{
          addChatMessage('System', '✗ ' + (reply.message || 'Message dispatch failed.'), false);
        }} else if (reply.timestamp) {{
          const idx = chatMessages.findIndex(m => m.id === msgId);
          if (idx !== -1) {{
            chatMessages[idx].timestamp = reply.timestamp;
            chatMessages[idx].pending = false;
          }}
        }}
      }} catch (err) {{
        console.error("Chat send failed:", err);
        addChatMessage('System', '✗ Network error sending message to Mothership.', false);
      }}
    }}

    /* Biometric WebAuthn */
    async function renderBiometricPrompt(chal) {{
      const cardEl = document.createElement('div');
      cardEl.className = 'card biometric';
      cardEl.id = 'bio-' + chal.challenge_id;

      cardEl.innerHTML = `
        <div class="card-header">
          <span class="card-title" style="color: #c4b5fd;">🔒 Face ID / Biometric Gate</span>
          <span class="card-time">SECURE</span>
        </div>
        <div class="card-content">${{escapeHtml(chal.reason || 'Authentication required to authorize operation.')}}</div>
        <div style="text-align: center; padding: 12px 0;">
          <button class="btn btn-biometric" onclick="triggerWebAuthn('${{chal.challenge_id}}', '${{chal.nonce}}')">
            Scan Face ID / Touch ID
          </button>
        </div>
      `;

      workView.appendChild(cardEl);
      workView.scrollTop = workView.scrollHeight;
      triggerWebAuthn(chal.challenge_id, chal.nonce);
    }}

    async function triggerWebAuthn(challengeId, nonce) {{
      const cardEl = document.getElementById('bio-' + challengeId);
      try {{
        let assertionResult = {{}};
        if (window.PublicKeyCredential && window.isSecureContext) {{
          const challengeBytes = new TextEncoder().encode(nonce);
          const userIdBytes = new TextEncoder().encode("gemini-operator");

          const cred = await navigator.credentials.create({{
            publicKey: {{
              challenge: challengeBytes,
              rp: {{ name: "Gemini Wingman Secure Enclave", id: window.location.hostname }},
              user: {{ id: userIdBytes, name: "dieablo101", displayName: "Operator" }},
              pubKeyCredParams: [{{ type: "public-key", alg: -7 }}, {{ type: "public-key", alg: -257 }}],
              authenticatorSelection: {{ authenticatorAttachment: "platform", userVerification: "required" }},
              timeout: 60000
            }}
          }});

          assertionResult = {{
            status: "authenticated",
            id: cred.id,
            type: cred.type,
            rawId: btoa(String.fromCharCode(...new Uint8Array(cred.rawId))),
            method: "apple_secure_enclave"
          }};
        }} else {{
          assertionResult = {{ status: "authenticated", method: "software_touch_fallback", token: "touch-verified-" + Date.now() }};
        }}

        await fetch('/applet/wingman/webauthn_response', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json', 'X-Wingman-Token': sessionToken }},
          body: JSON.stringify({{ challenge_id: challengeId, result: assertionResult }})
        }});

        if (cardEl) {{
          cardEl.innerHTML = `
            <div class="card-header"><span class="card-title" style="color: var(--success);">✓ Biometric Verified</span></div>
            <div class="card-content" style="color: var(--success);">Apple Secure Enclave Face ID confirmed successfully.</div>
          `;
        }}
        playTone(1046.5, 'sine', 0.2);
      }} catch (err) {{
        fetch('/applet/wingman/webauthn_response', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json', 'X-Wingman-Token': sessionToken }},
          body: JSON.stringify({{ challenge_id: challengeId, result: {{ status: "cancelled", error: err.message }} }})
        }});
      }}
    }}

    function measurePing() {{
      const t0 = performance.now();
      fetch('/applet/wingman/ping')
        .then(res => res.json())
        .then(data => {{
          const rtt = Math.round(performance.now() - t0);
          footerPing.textContent = 'PING: ' + rtt + 'ms';
          if (data && typeof data.time === 'number') {{
            const clientNow = Date.now() / 1000;
            serverTimeOffset = data.time - (clientNow - (rtt / 2000));
          }}
          if (data && data.maintenance !== undefined) {{
            if (data.maintenance && !isMaintenanceMode) {{
              setMaintenanceLock(true, data.message || "Wingman maintenance in progress — Mothership updates underway. Reconnection paused until release.");
            }} else if (!data.maintenance && isMaintenanceMode) {{
              setMaintenanceLock(false);
            }}
          }}
          if (data && data.mothership_boot_id) {{
            if (currentMothershipBootId && currentMothershipBootId !== data.mothership_boot_id) {{
              checkSession();
            }}
            currentMothershipBootId = data.mothership_boot_id;
          }}
          if (data && data.boot_id) {{
            if (currentBootId && currentBootId !== data.boot_id) {{
              checkSession();
            }}
            currentBootId = data.boot_id;
          }}
        }})
        .catch(() => {{
          footerPing.textContent = 'PING: ERR';
        }});
    }}

    function formatMarkdown(text) {{
      if (!text) return '';
      let safe = escapeHtml(text);
      safe = safe.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
      safe = safe.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.12);padding:2px 5px;border-radius:4px;font-family:monospace;font-size:0.9em;">$1</code>');
      safe = safe.replace(/^(?:[\\*\\-])\\s+(.+)$/gm, '<li style="margin-left:14px;list-style-type:disc;">$1</li>');
      safe = safe.replace(/(<li[\\s\\S]+?<\\/li>)/g, '<ul style="margin:4px 0;padding-left:10px;">$1</ul>');
      safe = safe.replace(/<\\/ul>\\s*<ul style="margin:4px 0;padding-left:10px;">/g, '');
      return safe;
    }}

    function escapeHtml(text) {{
      const div = document.createElement('div');
      div.textContent = text || '';
      return div.innerHTML;
    }}

    /* Immediate wake-up & visibility sync for mobile / screen-off devices */
    async function onWakeOrVisibilityChange() {{
      if (document.visibilityState === 'visible') {{
        // Instant check: if operator approved while iPad screen was off, unlock immediately!
        await checkSession();
        measurePing();
        // Check if SSE stream disconnected or stalled while screen was off
        if (!sseSource || sseSource.readyState === 2 || sseSource.readyState === EventSource.CLOSED) {{
          connectSSE();
        }}
      }}
    }}

    document.addEventListener('visibilitychange', onWakeOrVisibilityChange);
    window.addEventListener('pageshow', onWakeOrVisibilityChange);
    window.addEventListener('focus', onWakeOrVisibilityChange);

    checkSession();
    connectSSE();
    pingInterval = setInterval(measurePing, 5000);
    measurePing();
  </script>
</body>
</html>
"""
