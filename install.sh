#!/usr/bin/env bash
# Icarus Agent Universal Installer for macOS and Linux
set -euo pipefail

# ANSI color codes
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "  ___                                 _                    _   "
echo " |_ _|___ __ _ _ _ _  _ ___   /\_/\  /_\   __ _ ___ _ _  _| |_ "
echo "  | |/ _ / _\` | '_| || (_-<  ( o.o )/ _ \ / _\` / -_) ' \|  _| "
echo " |___\___\__,_|_|  \_,_/__/   > ^ </_/ \_\\__, \___|_||_|\__| "
echo "                                          |___/                "
echo "        Autonomous Personal Executive Agent (Jarvis)          "
echo -e "${NC}"

echo -e "${CYAN}==>${NC} Checking dependencies..."

# 1. Ensure uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo -e "${YELLOW}==>${NC} Installing uv package manager..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo -e "${RED}Error: curl or wget is required to install uv.${NC}" >&2
        exit 1
    fi

    # Add standard uv bin directories to PATH for current subshell
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
    echo -e "${RED}Error: uv was installed but could not be located in PATH.${NC}" >&2
    echo "Please add \$HOME/.local/bin or \$HOME/.cargo/bin to your PATH and re-run."
    exit 1
fi

echo -e "${GREEN}==>${NC} uv is ready: $(uv --version)"

# 2. Install icarus-agent via uv tool
PACKAGE_SPEC="${ICARUS_PACKAGE_SPEC:-icarus-agent}"
echo -e "${CYAN}==>${NC} Installing Icarus Agent (${PACKAGE_SPEC})..."
uv tool install --force "${PACKAGE_SPEC}"

echo ""
echo -e "${GREEN}================================================================${NC}"
echo -e "${GREEN}       Icarus Agent successfully installed!                    ${NC}"
echo -e "${GREEN}================================================================${NC}"
echo ""
echo -e "To start your autonomous personal assistant, run:"
echo -e "    ${CYAN}icarus${NC}           (Full-Screen Interactive TUI Workspace)"
echo -e "    ${CYAN}icarus doctor${NC}    (Verify local storage and credentials)"
echo -e "    ${CYAN}icarus init${NC}      (Configure your AI provider API key)"
echo ""
