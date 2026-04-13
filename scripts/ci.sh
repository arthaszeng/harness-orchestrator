#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

step() { printf "\n${GREEN}[ci]${NC} %s\n" "$*"; }
die()  { printf "${RED}[ci]${NC} %s\n" "$*" >&2; exit 1; }

# ── Lint ────────────────────────────────────────────────────────────────────
step "Lint with ruff"
ruff check src/ tests/ || die "ruff check failed"

# ── Format ──────────────────────────────────────────────────────────────────
step "Check formatting with ruff"
ruff format --check src/ tests/ || die "ruff format check failed"

# ── Tests ───────────────────────────────────────────────────────────────────
step "Run tests"
python3 -m pytest tests/ -v --tb=short || die "pytest failed"

step "All checks passed ✓"
