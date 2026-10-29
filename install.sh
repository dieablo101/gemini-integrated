#!/usr/bin/env bash
# ==============================================================================
# Gemini Integrated — Remote One-Line Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dieablo101/gemini-integrated/main/install.sh | bash
#   or
#   wget -qO- https://raw.githubusercontent.com/dieablo101/gemini-integrated/main/install.sh | bash
# ==============================================================================

set -e

# Terminal colors
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                  GEMINI INTEGRATED INSTALLER                     ║"
echo "║      Autonomous Bilateral Terminal Console & LLM Dev Tool        ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

REPO_URL="https://github.com/dieablo101/gemini-integrated.git"
TARBALL_URL="https://github.com/dieablo101/gemini-integrated/archive/refs/heads/main.tar.gz"

# Determine target directory
if [ -n "$GEMINI_INSTALL_DIR" ]; then
    INSTALL_DIR="$GEMINI_INSTALL_DIR"
elif [ "$EUID" -eq 0 ] && [ -d "/opt" ]; then
    INSTALL_DIR="/opt/gemini"
elif [ -d "/opt/gemini" ] && [ -w "/opt/gemini" ]; then
    INSTALL_DIR="/opt/gemini"
else
    INSTALL_DIR="$HOME/.local/share/gemini-integrated"
fi

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

echo -e "⚡ Target Installation Directory: ${BOLD}${INSTALL_DIR}${NC}"

# Check for git or curl/wget
if command -v git >/dev/null 2>&1; then
    echo -e "✓ Found git in PATH. Cloning/updating repository..."
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo -e "⚡ Updating existing installation in ${INSTALL_DIR}..."
        git -C "$INSTALL_DIR" pull --ff-only || true
    else
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
else
    echo -e "${YELLOW}ℹ git is not currently installed.${NC}"
    echo -e "⚡ Pulling repository tarball directly from GitHub..."
    mkdir -p "$INSTALL_DIR"
    TMP_DIR=$(mktemp -d)

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$TARBALL_URL" | tar -xz -C "$TMP_DIR"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$TARBALL_URL" | tar -xz -C "$TMP_DIR"
    else
        echo -e "${RED}✗ Error: Neither curl, wget, nor git was found. Please install curl or git to continue.${NC}"
        exit 1
    fi

    # Unpack contents of the root folder in archive to INSTALL_DIR
    EXTRACTED_SUBDIR=$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)
    if [ -n "$EXTRACTED_SUBDIR" ]; then
        cp -a "$EXTRACTED_SUBDIR"/. "$INSTALL_DIR"/
    fi
    rm -rf "$TMP_DIR"
    echo -e "✓ Repository files successfully extracted."
fi

# Ensure executable permissions on runners
chmod +x "$INSTALL_DIR/gemini-integrated.py"
chmod +x "$INSTALL_DIR/emergency_terminal.py"

# Pre-install emergency CLI dependency (google-genai) so recovery works out-of-the-box in any shell
if command -v python3 >/dev/null 2>&1; then
    if ! python3 -c "import google.genai" >/dev/null 2>&1; then
        echo -e "⚡ Installing emergency recovery dependency (google-genai)..."
        python3 -m pip install --break-system-packages google-genai >/dev/null 2>&1 || \
        python3 -m pip install --user google-genai >/dev/null 2>&1 || true
    fi
fi

# Create symlinks in ~/.local/bin
echo -e "⚡ Creating executable links in ${BIN_DIR}..."
ln -sf "$INSTALL_DIR/gemini-integrated.py" "$BIN_DIR/gemini-integrated"
ln -sf "$INSTALL_DIR/gemini-integrated.py" "$BIN_DIR/gemini"
ln -sf "$INSTALL_DIR/emergency_terminal.py" "$BIN_DIR/gemini-emergency"
ln -sf "$INSTALL_DIR/emergency_terminal.py" "$BIN_DIR/gemini-recovery"

# Ensure ~/.local/bin is in PATH in shell rc files
SHELL_RC=""
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -n "$ZSH_VERSION" ] && [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.profile" ]; then
    SHELL_RC="$HOME/.profile"
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q 'PATH=.*\.local/bin' "$SHELL_RC" 2>/dev/null && ! grep -q 'PATH=.*\$HOME/\.local/bin' "$SHELL_RC" 2>/dev/null; then
        echo -e "\n# Added by Gemini Integrated Installer\nexport PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$SHELL_RC"
        echo -e "✓ Added ~/.local/bin to PATH in ${SHELL_RC}"
    fi
fi

# Export PATH for current session
export PATH="$BIN_DIR:$PATH"

# Provision Default Shipped Projects (~/Projects/3drealms and ~/Projects/grim-reaper)
USER_PROJECTS_DIR="$HOME/Projects"
mkdir -p "$USER_PROJECTS_DIR"
if [ -d "$INSTALL_DIR/Projects/3drealms" ] && [ ! -d "$USER_PROJECTS_DIR/3drealms" ]; then
    echo -e "⚡ Provisioning default Project: 3drealms in ${USER_PROJECTS_DIR}..."
    cp -a "$INSTALL_DIR/Projects/3drealms" "$USER_PROJECTS_DIR/"
fi
if [ -d "$INSTALL_DIR/Projects/grim-reaper" ] && [ ! -d "$USER_PROJECTS_DIR/grim-reaper" ]; then
    echo -e "⚡ Provisioning default Project: grim-reaper in ${USER_PROJECTS_DIR}..."
    cp -a "$INSTALL_DIR/Projects/grim-reaper" "$USER_PROJECTS_DIR/"
fi

echo -e "\n${GREEN}${BOLD}✓ Gemini Integrated successfully installed!${NC}\n"
echo -e "Launch it from any terminal by typing:"
echo -e "  ${CYAN}${BOLD}gemini-integrated${NC}  or  ${CYAN}${BOLD}gemini${NC}\n"
echo -e "Note: On your first run, Gemini will autonomously:"
echo -e "  1. Check your Linux distro and install system tools (git, etc.)"
echo -e "  2. Configure your virtual environment (.venv) and Python packages"
echo -e "  3. Prompt for your Real Name and Git credentials to setup Git properly"
echo -e "  4. Prompt for and persist your Google Gemini API Key"
echo -e "  5. Scaffold projects directly in ~/Projects with Git, README, and Copyright yourname\n"
