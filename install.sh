#!/usr/bin/env bash
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { printf "${BLUE}[harness]${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}[harness]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[harness]${NC} %s\n" "$*"; }

# ── 1. Install the package ───────────────────────────────────────────────────
info "Installing harness-orchestrator..."
pip3 install -e . 2>&1 | tail -5
echo

# ── 2. Check if `harness` is already on PATH ────────────────────────────────
if command -v harness &>/dev/null; then
    ok "harness $(harness --version 2>/dev/null || true)"
    ok "Installation complete."
    exit 0
fi

# ── 3. Locate the installed script ──────────────────────────────────────────
SCRIPT_DIR=""
# pip --user installs scripts to the user base bin
USER_BIN="$(python3 -m site --user-base 2>/dev/null)/bin"
if [ -x "${USER_BIN}/harness" ]; then
    SCRIPT_DIR="$USER_BIN"
fi

if [ -z "$SCRIPT_DIR" ]; then
    # Try the venv / system bin next to the python3 executable
    PY_BIN="$(dirname "$(python3 -c 'import sys; print(sys.executable)')")"
    if [ -x "${PY_BIN}/harness" ]; then
        SCRIPT_DIR="$PY_BIN"
    fi
fi

if [ -z "$SCRIPT_DIR" ]; then
    warn "'harness' script not found after install."
    warn "You can still use: python3 -m harness"
    exit 0
fi

# ── 4. Add to PATH in the current shell's rc file ───────────────────────────
info "harness was installed to ${SCRIPT_DIR} (not on PATH)"

SHELL_NAME="$(basename "${SHELL:-/bin/bash}")"
case "$SHELL_NAME" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash)
        if [ -f "$HOME/.bash_profile" ]; then
            RC_FILE="$HOME/.bash_profile"
        else
            RC_FILE="$HOME/.bashrc"
        fi
        ;;
    *)    RC_FILE="$HOME/.profile" ;;
esac

EXPORT_LINE="export PATH=\"${SCRIPT_DIR}:\$PATH\""

if [ -f "$RC_FILE" ] && grep -qF "$SCRIPT_DIR" "$RC_FILE" 2>/dev/null; then
    info "PATH entry already exists in ${RC_FILE}, skipping."
else
    echo "" >> "$RC_FILE"
    echo "# Added by harness-orchestrator installer" >> "$RC_FILE"
    echo "$EXPORT_LINE" >> "$RC_FILE"
    ok "Added ${SCRIPT_DIR} to PATH in ${RC_FILE}"
fi

# Apply to current session
export PATH="${SCRIPT_DIR}:$PATH"

if command -v harness &>/dev/null; then
    ok "harness $(harness --version 2>/dev/null || true)"
    ok "Installation complete."
    info "Run 'source ${RC_FILE}' or open a new terminal to use harness everywhere."
else
    warn "Something went wrong. You can still use: python3 -m harness"
fi
