#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { printf "${BLUE}[release]${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}[release]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[release]${NC} %s\n" "$*"; }
die()   { printf "${RED}[release]${NC} %s\n" "$*" >&2; exit 1; }

BUMP="${1:-patch}"  # patch | minor | major

# ── Guard: clean worktree on main ────────────────────────────────────────────
BRANCH="$(git branch --show-current)"
[ "$BRANCH" = "main" ] || die "Must be on main branch (currently on $BRANCH)"
[ -z "$(git status --porcelain)" ] || die "Working tree is dirty — commit or stash first"
git pull --ff-only origin main || die "Failed to pull latest main"

# ── Read current version ─────────────────────────────────────────────────────
CURRENT=$(python3 -c "
import re
with open('pyproject.toml') as f:
    m = re.search(r'version\s*=\s*\"([^\"]+)\"', f.read())
    print(m.group(1))
")
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

case "$BUMP" in
    patch) PATCH=$((PATCH + 1)) ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    *)     die "Usage: $0 [patch|minor|major]" ;;
esac
NEW="${MAJOR}.${MINOR}.${PATCH}"

info "Bumping version: $CURRENT -> $NEW ($BUMP)"

# ── Bump version in pyproject.toml ───────────────────────────────────────────
python3 -c "
with open('pyproject.toml') as f: c = f.read()
c = c.replace('version = \"$CURRENT\"', 'version = \"$NEW\"')
with open('pyproject.toml', 'w') as f: f.write(c)
"

# ── Install and verify ───────────────────────────────────────────────────────
info "Installing..."
pip install -e . -q 2>&1 | tail -1
INSTALLED="$(harness --version 2>/dev/null)"
[[ "$INSTALLED" == *"$NEW"* ]] || die "Version mismatch after install: got $INSTALLED, expected $NEW"
ok "Installed: $INSTALLED"

# ── Run tests ────────────────────────────────────────────────────────────────
info "Running tests..."
python -m pytest tests/ -q --tb=line 2>&1 | tail -3
[ "${PIPESTATUS[0]:-0}" -eq 0 ] || die "Tests failed — aborting release"
ok "Tests passed"

# ── Lint ─────────────────────────────────────────────────────────────────────
info "Linting..."
ruff check src/ tests/ || die "Lint failed — aborting release"
ok "Lint passed"

# ── Commit and push ──────────────────────────────────────────────────────────
# Tag creation and PyPI publish are handled by GitHub Actions (release.yml)
# when this push lands on main with the pyproject.toml version change.
info "Committing v$NEW..."
git add pyproject.toml
git commit -m "chore: release v$NEW"
git push origin main

ok "Pushed v$NEW to main"
ok "GitHub Actions will create tag, publish to PyPI, and create GitHub Release"
ok "Track at: https://github.com/arthaszeng/harness-orchestrator/actions"
