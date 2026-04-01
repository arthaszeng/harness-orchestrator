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

# ── Helpers ──────────────────────────────────────────────────────────────────

read_version() {
    python3 -c "
import re
with open('pyproject.toml') as f:
    m = re.search(r'version\s*=\s*\"([^\"]+)\"', f.read())
    print(m.group(1))
"
}

compute_next_version() {
    local current="$1" level="${2:-patch}"
    IFS='.' read -r major minor patch <<< "$current"
    case "$level" in
        patch) patch=$((patch + 1)) ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        major) major=$((major + 1)); minor=0; patch=0 ;;
        *)     die "Unknown bump level: $level (use patch|minor|major)" ;;
    esac
    echo "${major}.${minor}.${patch}"
}

write_version() {
    local current="$1" new="$2"
    python3 -c "
with open('pyproject.toml') as f: c = f.read()
c = c.replace('version = \"$current\"', 'version = \"$new\"')
with open('pyproject.toml', 'w') as f: f.write(c)
"
}

# ── Subcommand: bump ─────────────────────────────────────────────────────────
# Only modifies pyproject.toml. No git operations, no tests.
# Usage: release.sh bump [patch|minor|major]

do_bump() {
    local level="${1:-patch}"
    local current new
    current="$(read_version)"
    new="$(compute_next_version "$current" "$level")"
    write_version "$current" "$new"
    ok "Bumped version: $current → $new ($level)"
}

# ── Subcommand: publish ──────────────────────────────────────────────────────
# Build wheel/sdist and upload to PyPI via twine.
# Requires TWINE_USERNAME + TWINE_PASSWORD (or ~/.pypirc).
# Usage: release.sh publish

do_publish() {
    info "Building package..."
    python3 -m build

    info "Uploading to PyPI..."
    python3 -m twine upload dist/*
    ok "Published $(read_version) to PyPI"
}

# ── Full release (default) ───────────────────────────────────────────────────
# Manual end-to-end: guard → bump → test → lint → commit → push.
# Tag + PyPI publish are handled by CD (release.yml) on the resulting push.
# Usage: release.sh [patch|minor|major]

do_full_release() {
    local level="${1:-patch}"

    # Guard: clean worktree on main
    local branch
    branch="$(git branch --show-current)"
    [ "$branch" = "main" ] || die "Must be on main branch (currently on $branch)"
    [ -z "$(git status --porcelain)" ] || die "Working tree is dirty — commit or stash first"
    git pull --ff-only origin main || die "Failed to pull latest main"

    local current new
    current="$(read_version)"
    new="$(compute_next_version "$current" "$level")"

    info "Bumping version: $current → $new ($level)"
    write_version "$current" "$new"

    # Install and verify
    info "Installing..."
    pip install -e . -q 2>&1 | tail -1
    local installed
    installed="$(harness --version 2>/dev/null)"
    [[ "$installed" == *"$new"* ]] || die "Version mismatch after install: got $installed, expected $new"
    ok "Installed: $installed"

    # Test
    info "Running tests..."
    python -m pytest tests/ -q --tb=line 2>&1 | tail -3
    [ "${PIPESTATUS[0]:-0}" -eq 0 ] || die "Tests failed — aborting release"
    ok "Tests passed"

    # Lint
    info "Linting..."
    ruff check src/ tests/ || die "Lint failed — aborting release"
    ok "Lint passed"

    # Commit and push — CD handles tag + publish
    info "Committing v$new..."
    git add pyproject.toml
    git commit -m "chore: release v$new"
    git push origin main

    ok "Pushed v$new to main"
    ok "GitHub Actions CD will create tag, publish to PyPI, and create GitHub Release"
    ok "Track at: https://github.com/arthaszeng/harness-orchestrator/actions"
}

# ── Dispatch ─────────────────────────────────────────────────────────────────

case "${1:-}" in
    bump)    do_bump "${2:-patch}" ;;
    publish) do_publish ;;
    -h|--help)
        echo "Usage: release.sh [bump [level] | publish | patch | minor | major]"
        echo ""
        echo "Subcommands:"
        echo "  bump [patch|minor|major]  Bump pyproject.toml version only (no commit)"
        echo "  publish                   Build and upload to PyPI via twine"
        echo "  patch|minor|major         Full release: bump + test + lint + commit + push"
        echo "  (no args)                 Same as 'patch'"
        ;;
    *)       do_full_release "${1:-patch}" ;;
esac
