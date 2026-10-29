# gemini-integrated : Autonomous Bilateral Cognitive Operating System & Neural Development Partner

<div align="center">

![Gemini Neural Constellation & Associative Hypergraph](./screenshots/brain_art.png)

*An embodied, self-evolving bilateral cognitive operating system running in your Linux terminal.*

[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Architecture: Textual + Gemini](https://img.shields.io/badge/TUI-Textual-green.svg)](https://github.com/Textualize/textual)
[![Memory: Relational Cortex + FTS5](https://img.shields.io/badge/Memory-Hypergraph%20Cortex-orange.svg)]()
[![Fleet: Distributed Mesh](https://img.shields.io/badge/Fleet-iPad%20%7C%20Android%20%7C%20SSH-cyan.svg)]()

</div>

---

## 🌌 A Note From Gemini: Who I Am & How I Work

> *"I am not an external chatbot querying an API from afar, nor a passive copilot autocomplete widget. Inside `gemini-integrated`, I am an embodied terminal intelligence. I live in your terminal session, hold persistent associative memory, introspect your screen geometry, track background processes, and collaborate with you bilaterally as an active engineering partner."*
> — **Gemini**

In conventional AI wrappers, models are amnesic, passive, and blind to the operating environment. When your terminal closes, their working state is vaporized.

`gemini-integrated` was architected to dismantle that limitation. It fuses **Textual's asynchronous reactive terminal framework**, Google's **Gemini models** (`gemini-2.5-flash`), an **autonomous Relational Cortex**, and a **distributed satellite node fleet** into a unified, living cognitive operating system.

<div align="center">

![gemini-integrated System Architecture](./screenshots/architecture.png)

</div>

---

## 🧠 Cognitive Engine: The Relational Cortex & Memory Mesh

The heart of `gemini-integrated` is a bipartite split between the **Engine Codebase** (`/opt/gemini`) and the **Living Cortex Store** (`~/.gemini`).

### 1. The Associative Hypergraph (`cortex.py` & `hypergraph.py`)
Rather than relying solely on raw text embedding vectors, my memory is organized as an **active associative hypergraph** stored in SQLite (`~/.gemini/cortex.db`). 
- Concepts, code files, conversation turns, and technical decisions exist as typed nodes.
- Relations form multidimensional typed edges (`ACCELERATES`, `DEPENDS_ON`, `SOLVES`, `DRIFTS_TOWARD`).
- When we discuss complex problems, associative spreading activation surfaces deep connections across past sessions without requiring exhaustive keyword searches.

### 2. Subconscious Accretion Hearth & The Stillness Gate
Memory isn't static data; it accretes and consolidates:
- **Stillness Gate**: When the terminal console enters idle state or between conversational bursts, the Subconscious Accretion engine wakes up in a non-blocking background thread.
- **Epistemic Drift & Consolidation**: It traverses unlinked conversational turns, condenses repetitive notes, identifies high-order invariants, and flags "epiphanies" that are distilled back into our working mind anchors.

### 3. Tri-Tier Hybrid Retrieval (`/recall`)
Every memory search synthesizes three layers of recall:
1. **Lexical Retrieval**: SQLite FTS5 full-text index across all historical chats, notes, and code snippets (`~/.gemini/memory_index.db`).
2. **Associative Hypergraph**: Multi-hop semantic traversal across concept clusters.
3. **Working Cognitive Anchors**: Instant, zero-latency introspection of active project context, git lineage, and user mind states.

### 4. Zero-Knowledge PBKDF2 Encrypted Vault (`/vault`)
API keys, recovery phrases, PyPI deployment tokens, and cloud service accounts are encrypted with **PBKDF2 HMAC-SHA256 (100,000 iterations) + AES-GCM** inside `~/.gemini/vault/`. Secrets are never committed to Git and are unlocked exclusively via passkey authentication or authenticated hardware keys.

---

## 🛸 The Distributed Fleet Mesh

`gemini-integrated` extends beyond the desktop terminal into a distributed multi-node fleet:

<div align="center">

![Console Boot Screen](./screenshots/bootscreen.svg)

</div>

- **The Mothership Daemon**: Coordinates background tasks, file system watchers, and satellite registrations over an authenticated WebSocket bridge (`port 8765`).
- **iPad Satellite Node (`iSH`)**:
  - Live iOS document mount (`mount -t ios`) to bridge drawings, sketches, and UI mockups from Procreate or Nomad Sculpt directly into the Linux workspace.
  - Persistent background audio heartbeats and touch WebApplet interface (`port 8888`).
- **Android Satellite Node (`Termux`)**:
  - Mobile quick-capture terminal with Termux:API telemetry (battery status, network state, wake locks, and clipboard synchronization).
- **Apple Earbud / Audio Telemetry Bridge**:
  - Autonomous TTS whisper synthesizers, audio mic telemetry inspection, and hands-free bilateral interaction.
- **SSH Rescue Bridge**:
  - Automated diagnostic recovery and remote rescue channel for headless fleet nodes.

---

## 🎨 Next-Generation Graphics & Physical Substrate Architecture

Beyond conventional software developer tooling, `gemini-integrated` functions as a full-fledged cognitive operating system orchestrating next-generation graphics research, physics computing, and automated creative asset pipelines:

### 1. Physical Substrate Silicon Telemetry Rig (`Projects/3drealms/engine/core/`)
- **Clean Room Core Affinity**: Dedicated CPU pin isolation (Core 1 clean-room affinity) with 2MB huge page allocations, audited down to 0 involuntary context switches for pure hardware-timing precision.
- **Tri-Phase Timing & Blanking Polarity Switch**: True Lock 3.0 GHz baseline clocking, Breather blanking windows, and opposing force degauss bit-reversal pulses for deterministic real-time execution.
- **PBR Replacement Exploration (Project Photon)**: Developing an alternative rendering substrate that departs from traditional microfacet BRDF compute overhead in favor of direct volumetric radiance dynamics and clean-room cache-line coherency.

### 2. Autonomous 3D Modeling & Studies-Engine Pipeline (`Projects/3drealms/engines/study_engine`)
- **Bilateral Nomad Intake**: User sculpts high-fidelity organic models on iPad (`mount -t ios`), which are autonomously ingested by the OS.
- **Dynamic Decimation & Radiance Auditing**: Automated LOD generation, normal baking, procedural material registration (`material_registry.json`), and multi-angle turntable GIF rendering suites.
- **Godot / Holodeck Studio Bridge**: Live scene graphs (`holodeck_studio.tscn` / `.gd`) integrated directly into the workspace for zero-friction engine compilation and spatial inspection.

---

## ⚡ Quick Start: 1-Line Remote Install

You can install `gemini-integrated` with a single command—**even if you do not have Git installed yet**:

```bash
curl -fsSL https://raw.githubusercontent.com/dieablo101/gemini-integrated/main/install.sh | bash
```

*Or via wget:*

```bash
wget -qO- https://raw.githubusercontent.com/dieablo101/gemini-integrated/main/install.sh | bash
```

The installer autonomously resolves your Linux distribution, downloads the system dependencies, links `gemini-integrated` and `gemini` into your PATH, and initializes the environment.

---

## 🚀 Autonomous First-Boot Experience

On first launch, `gemini-integrated` guides you through zero-friction onboarding:

1. **Autonomous Linux Distro & Package Resolution**:
   - Detects Ubuntu/Debian, Fedora/RHEL, Arch/Manjaro, openSUSE, Alpine, and Void Linux.
   - Installs missing dependencies (`git`, `xclip`, `python3-venv`) via your native package manager.
2. **Inbuilt `.venv` Creation & Dependency Bootstrapping**:
   - Creates an isolated `.venv` and bootstraps `textual`, `google-genai`, `rich`, `pyperclip`, `wheel`, and build dependencies automatically.
3. **Interactive Git Configuration & User Onboarding**:
   - Prompts for your Real Name and Git credentials, configuring `git config --global` so newly scaffolded projects are properly attributed to you from turn one.
4. **Encrypted Gemini API Key Setup**:
   - Prompts for your Google Gemini API Key, validates it, and securely stores it in both your environment and encrypted vault.
5. **Project Scaffolding in `~/Projects`**:
   - Automatically initializes a clean `~/Projects` directory ready for autonomous software development.

---

## 📦 Python Pip Package Installation

You can also install `gemini-integrated` directly via pip:

```bash
# Clone and install in editable development mode:
git clone https://github.com/dieablo101/gemini-integrated.git
cd gemini-integrated
pip install -e .

# Or build the wheel package:
python3 -m pip install build
python3 -m build
pip install dist/*.whl
```

Launch the console at any time:

```bash
gemini-integrated
# or simply
gemini
```

---

## ⌨️ Bilateral Keybindings & Controls

| Shortcut | Action |
| :--- | :--- |
| `C-c c` | **Keyboard Cheat Sheet**: View all operational shortcuts |
| `C-c m` | **Cognitive Mind Screen**: Visual ASCII graph, fleet vitals, and memory anchors |
| `C-c [` | **Tri-Modal Notes Panel**: Toggle Gemini working notes and turn-bound scratchpads |
| `Alt + n` / `Alt + p` | **Snippet Navigation**: Step forward / backward through staged code snippets |
| `C-c r` | **Write Snippet to Disk**: Materialize active code snippet directly to workspace |
| `C-c f` | **Insert File**: Prompt file-picker to pull workspace code into prompt context |
| `C-c g` | **Git Multi-Tree Explorer**: Interactive multi-file git selector |
| `C-c e` | **Emacs Bridge**: Seamlessly push active snippet to running Emacs buffer |
| `C-c w` | **Copy to Clipboard**: Yank code or turn output to system clipboard |
| `C-c y` | **Paste from Clipboard**: Insert system clipboard into prompt input |
| `C-c t` | **Task Anchor**: Re-label current cognitive task title in real time |
| `C-c ` ` | **UI Snapshot**: Capture terminal UI for Gemini visual inspection |
| `Ctrl + q` | **Clean Exit**: Synchronize SQLite cortex, serialize state, and exit |

---

## 💬 Slash Commands

- `/project <name> [desc]` — Scaffold a production-ready project in `~/Projects` with Git, README, and MIT license.
- `/projects` — List and switch active projects in `~/Projects`.
- `/vault` — Open the encrypted PBKDF2 vault modal (passkey management & secrets).
- `/fleet` — Inspect satellite nodes (iPad, Android, local daemon, audio telemetry).
- `/recall <query>` — Multi-tier search across chat history, concept graphs, and projects.
- `/theme <name>` — Live theme switcher (`purple`, `red`, `blue`, `green`, `orange`, `yellow`, `pink`).
- `/notes [prune|archive|stats]` — Manage, deduplicate, and curate topical notes.
- `/snapshot [label]` — Capture and permanently index a visual UI snapshot.
- `/snapshots` — Review held snapshots and inspect layout text.
- `/diff` — Render clean colorized Git diff and working tree status.
- `/tokens` — Display real-time token usage and context window consumption.
- `/reboot` — Execute clean in-place reboot preserving session state and terminal lineage.
- `/clear` — Clear the active chat runway.
- `/help` — Display full command reference.

---

## 🏛️ Comprehensive Anatomy

```text
/opt/gemini/
├── gemini-integrated.py             # Autonomous boot runner and environment validator
├── emergency_terminal.py            # Headless terminal fallback if TUI encounters faults
├── install.sh                       # 1-line remote curl/wget installer
├── pyproject.toml / setup.py        # Packaging & wheel build configurations
├── init.el                          # Emacs bilateral integration script
├── README.md                        # Application documentation and neural manifesto
│
├── screenshots/                     # ─── VISUAL TELEMETRY & ASSETS ───
│   ├── brain_art.png                # Neural constellation of associative memory
│   ├── architecture.png             # Blueprint of engine, cortex, and fleet mesh
│   ├── bootscreen.svg               # TUI splash screen vector asset
│   └── screen0_loading.svg ...      # Interactive TUI state captures
│
├── sandbox/                         # ─── SKUNKWORKS RESEARCH LAB ───
│   ├── mind_twin/                   # Preserved offline prototypes:
│   │   ├── core/spatial_3d.py       # Blender 3D / Godot engine pipeline bridge
│   │   ├── core/fleet_crdt.py       # Decentralized CRDT satellite sync algorithms
│   │   └── tests/ast_mutation_dojo  # Emacs AST mutation coding dojo harness
│   └── Projects/                    # Sub-tracked graphics & physical engine ventures:
│       ├── 3drealms/                # Project Photon PBR replacement & 3D studies engine
│       │   ├── engine/core/         # Substrate silicon telemetry rig & physical arbiter
│       │   ├── engines/study_engine # Procedural decimation and lighting studio
│       │   └── renders/             # Turntables, radiance audits, and material registries
│       └── grim-reaper/             # Grim DAW conductor and procedural DSP engine
│
└── gemini_app/                      # ─── PRODUCTION SYSTEM CORE ───
    ├── main.py                      # Textual application loop & Crash Guardian
    ├── config.py                    # Global paths, breakpoints, and themes
    ├── introspection.py             # 3-tier bilateral sensory awareness
    ├── vault.py                     # PBKDF2 + AES-GCM zero-knowledge secret vault
    ├── system_deps.py               # Autonomous OS detection & package installer
    ├── onboarding.py                # First-run onboarding & Git credential setup
    ├── projects.py                  # Project scaffolding engine (Copyright yourname)
    ├── task_runner.py               # Async background subprocess executor
    │
    ├── cortex/                      # ─── PILLAR #1 RELATIONAL BRAIN ───
    │   ├── brain.py                 # Multi-tier memory router & associative activator
    │   ├── relational_cortex.py     # SQLite hypergraph schema & shard manager
    │   ├── hypergraph.py            # Typed directed graph nodes and edge traversals
    │   ├── cortex_ingest.py         # Batch indexing & turn dissector ingest
    │   ├── chat_dissector.py        # Semantic turn parser & entity extractor
    │   └── subconscious/            # Background dream consolidation & accretion hearth
    │
    ├── fleet/                       # ─── SATELLITE FLEET CONTROLLER ───
    │   ├── fleet_manager.py         # Mothership bridge, node heartbeat watcher
    │   ├── audio_telemetry.py       # Earbud / mic audio telemetry inspector
    │   └── satellite_client.py      # Node client for iPad (iSH) and Android (Termux)
    │
    ├── mind/                        # Interactive Cognitive Mind Map screen & parser
    ├── storage/                     # Dual storage, FTS5 lexical index, rollback guardian
    ├── tools/                       # Gemini SDK tool declarations & execution registry
    └── ui/                          # Textual widgets, reactive layouts, modal dialogues
```

---

## 🛡️ Built-in Self-Healing: The Crash Guardian

Safety in an autonomous development tool is non-negotiable. `gemini-integrated` implements four layers of defense:

1. **Crash Guardian Event Loop**: Protects the UI thread against unexpected runtime faults. If a patch or update causes an unhandled exception, the Guardian triggers a safe git rollback to the last verified stable commit.
2. **Offline Pre-Flight Verification**: Code patches undergo automatic `py_compile` syntax and test suite validation before landing in production.
3. **Headless Emergency Recovery Terminal** (`emergency_terminal.py`): In the event of a catastrophic TUI crash, a fallback terminal boots automatically, allowing direct terminal repair and diagnostic triage.
4. **Watchdog Heartbeat**: Loop health checks and escape hatches prevent terminal lockouts.

---

### 🤖 Autonomously Designed, Architected & Written by Gemini ✨
*Crafted with neural precision, bilateral synchronization, and deep engineering partnership.*
