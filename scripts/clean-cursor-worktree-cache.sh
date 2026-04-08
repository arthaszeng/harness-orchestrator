#!/usr/bin/env bash
set -euo pipefail

DB="$HOME/Library/Application Support/Cursor/User/globalStorage/state.vscdb"

if ! [ -f "$DB" ]; then
  echo "ERROR: state.vscdb not found at: $DB"
  exit 1
fi

MAX_WAIT=15
waited=0
while pgrep -xq "Cursor" 2>/dev/null; do
  if [ "$waited" -eq 0 ]; then
    echo "Waiting for Cursor to exit..."
  fi
  sleep 1
  waited=$((waited + 1))
  if [ "$waited" -ge "$MAX_WAIT" ]; then
    echo "⚠️  Cursor is still running after ${MAX_WAIT}s."
    exit 1
  fi
done
if [ "$waited" -gt 0 ]; then
  echo "Cursor exited after ${waited}s."
fi

echo "=== Backing up state.vscdb ==="
BACKUP="${DB}.bak.$(date +%Y%m%d%H%M%S)"
cp "$DB" "$BACKUP"
echo "Backup: $BACKUP"

echo ""
echo "=== Cleaning all worktree references from state.vscdb ==="

python3 << 'PYEOF'
import json, sqlite3, os, re, sys

db_path = os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

worktree_patterns = [
    "lint-check-y1m", "review-code-hye", "explore-structure-64a",
    "analyze-r2h", "explore-zdb", "fix-user-create-422-wyg",
    "dashboard-stats-kxt", "worktree-test-0ln",
    "harness-flow-wt-task-037",
]

def has_worktree_ref(text):
    t = text.lower()
    if "worktree" in t:
        return True
    for p in worktree_patterns:
        if p in t:
            return True
    return False

# --- 1. workspaceMetadata.entries ---
cur.execute("SELECT value FROM ItemTable WHERE key = 'workspaceMetadata.entries'")
row = cur.fetchone()
if row:
    data = json.loads(row[0])
    before = len(data["entries"])
    data["entries"] = [
        e for e in data["entries"]
        if not e.get("worktreeInfo", {}).get("isWorktree", False)
        and not has_worktree_ref(e.get("folderUri", ""))
        and not has_worktree_ref(e.get("displayPath", ""))
    ]
    after = len(data["entries"])
    cur.execute("UPDATE ItemTable SET value = ? WHERE key = 'workspaceMetadata.entries'",
                (json.dumps(data),))
    print(f"[1] workspaceMetadata.entries: {before} → {after} (removed {before - after})")

# --- 2. glass.localAgentProjects.v1 — remove entries whose workspace uri points to worktree ---
cur.execute("SELECT value FROM ItemTable WHERE key = 'glass.localAgentProjects.v1'")
row = cur.fetchone()
if row:
    projects = json.loads(row[0])
    before = len(projects)
    projects = [
        p for p in projects
        if not has_worktree_ref(
            p.get("workspace", {}).get("uri", {}).get("fsPath", "")
        )
    ]
    after = len(projects)
    cur.execute("UPDATE ItemTable SET value = ? WHERE key = 'glass.localAgentProjects.v1'",
                (json.dumps(projects),))
    print(f"[2] glass.localAgentProjects.v1: {before} → {after} (removed {before - after})")

# --- 3. composer.composerHeaders — remove composers tied to worktree workspaces ---
cur.execute("SELECT value FROM ItemTable WHERE key = 'composer.composerHeaders'")
row = cur.fetchone()
if row:
    data = json.loads(row[0])
    composers = data.get("allComposers", [])
    before = len(composers)
    composers = [c for c in composers if not has_worktree_ref(json.dumps(c))]
    data["allComposers"] = composers
    after = len(composers)
    cur.execute("UPDATE ItemTable SET value = ? WHERE key = 'composer.composerHeaders'",
                (json.dumps(data),))
    print(f"[3] composer.composerHeaders: {before} → {after} (removed {before - after})")

# --- 4. terminal.history — remove worktree paths from terminal history ---
for hist_key in ("terminal.history.entries.dirs", "terminal.history.entries.commands"):
    cur.execute("SELECT value FROM ItemTable WHERE key = ?", (hist_key,))
    row = cur.fetchone()
    if row:
        data = json.loads(row[0])
        entries = data.get("entries", [])
        before = len(entries)
        entries = [e for e in entries if not has_worktree_ref(e.get("key", ""))]
        data["entries"] = entries
        after = len(entries)
        if before != after:
            cur.execute("UPDATE ItemTable SET value = ? WHERE key = ?",
                        (json.dumps(data), hist_key))
            print(f"[4] {hist_key}: {before} → {after} (removed {before - after})")

# --- 5. cursorDiskKV — remove worktree-related keys ---
cur.execute("SELECT key FROM cursorDiskKV WHERE key LIKE '%worktree%'")
wt_keys = [r[0] for r in cur.fetchall()]
if wt_keys:
    for k in wt_keys:
        cur.execute("DELETE FROM cursorDiskKV WHERE key = ?", (k,))
    print(f"[5] cursorDiskKV: deleted {len(wt_keys)} worktree keys")

# --- 6. Remove glass.tabs entries for worktree workspaces ---
cur.execute("SELECT key FROM cursorDiskKV WHERE key LIKE 'cursor/glass.tabs%'")
tab_keys = [r[0] for r in cur.fetchall()]
deleted_tabs = 0
for k in tab_keys:
    cur.execute("SELECT value FROM cursorDiskKV WHERE key = ?", (k,))
    row = cur.fetchone()
    if row and has_worktree_ref(row[0]):
        cur.execute("DELETE FROM cursorDiskKV WHERE key = ?", (k,))
        deleted_tabs += 1
if deleted_tabs:
    print(f"[6] glass.tabs in cursorDiskKV: deleted {deleted_tabs} entries")

# --- 7. Remove glass.fileTab.viewState entries for worktree files ---
cur.execute("SELECT key FROM ItemTable WHERE key LIKE 'cursor/glass.fileTab.viewState%'")
view_keys = [r[0] for r in cur.fetchall()]
deleted_views = 0
for k in view_keys:
    if has_worktree_ref(k):
        cur.execute("DELETE FROM ItemTable WHERE key = ?", (k,))
        deleted_views += 1
if deleted_views:
    print(f"[7] glass.fileTab.viewState in ItemTable: deleted {deleted_views} entries")

conn.commit()
conn.close()
print("\nDatabase cleanup complete.")
PYEOF

echo ""
echo "=== Cleaning workspaceStorage directories ==="
WS_DIR="$HOME/Library/Application Support/Cursor/User/workspaceStorage"
cleaned=0
for dir in "$WS_DIR"/*/; do
  if [ -f "$dir/workspace.json" ]; then
    folder=$(python3 -c "import json; print(json.load(open('$dir/workspace.json')).get('folder',''))" 2>/dev/null || true)
    if echo "$folder" | grep -qi "worktree"; then
      echo "  Removing: $(basename "$dir") → $folder"
      rm -rf "$dir"
      cleaned=$((cleaned + 1))
    fi
  fi
done
echo "  Cleaned $cleaned workspaceStorage directories."

echo ""
echo "=== Cleaning ~/.cursor/projects/ worktree caches ==="
proj_cleaned=0
for dir in "$HOME/.cursor/projects/"*worktree*/ "$HOME/.cursor/projects/"*-wt-*/ ; do
  if [ -d "$dir" ]; then
    echo "  Removing: $dir"
    rm -rf "$dir"
    proj_cleaned=$((proj_cleaned + 1))
  fi
done
echo "  Cleaned $proj_cleaned project cache directories."

echo ""
echo "=== Verification ==="
sqlite3 "$DB" "SELECT value FROM ItemTable WHERE key = 'workspaceMetadata.entries';" | python3 -m json.tool 2>/dev/null
echo ""
echo "✅ Done! Start Cursor — worktree entries should be gone from Recents."
