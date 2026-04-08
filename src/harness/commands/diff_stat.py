"""harness diff-stat — branch change statistics for agents and scripts."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.core.config import HarnessConfig
from harness.integrations.git_ops import run_git

CODE_EXTENSIONS = frozenset({".py", ".ts", ".js", ".tsx", ".jsx", ".mjs"})
DOC_EXTENSIONS = frozenset({".md"})
_TEST_DIR_MARKERS = ("tests/", "__tests__/", "test/")
_TEST_FILE_MARKERS = ("test_", "_test.")


def _classify_file(path: str) -> str:
    """Return 'code', 'test', 'doc', or 'other'."""
    lower = path.lower()
    suffix = Path(lower).suffix

    is_test_dir = any(marker in lower for marker in _TEST_DIR_MARKERS)
    is_test_name = any(marker in Path(lower).name for marker in _TEST_FILE_MARKERS)
    if (is_test_dir or is_test_name) and suffix in CODE_EXTENSIONS:
        return "test"

    if suffix in CODE_EXTENSIONS:
        return "code"
    if suffix in DOC_EXTENSIONS:
        return "doc"
    return "other"


def run_diff_stat(*, as_json: bool = True) -> None:
    """Print branch diff statistics relative to trunk."""
    cwd = Path.cwd()

    try:
        cfg = HarnessConfig.load(cwd)
    except Exception:
        import warnings
        warnings.warn("Failed to load .harness-flow/config.toml; using default trunk_branch=main")
        cfg = HarnessConfig()
    trunk = cfg.workflow.trunk_branch
    diff_range = f"origin/{trunk}..HEAD"

    result = run_git(["diff", "--name-only", diff_range], cwd, timeout=10)
    if result.returncode != 0:
        err_msg = result.stderr.strip() or f"git diff failed (exit {result.returncode})"
        if as_json:
            typer.echo(json.dumps({"error": err_msg}))
        else:
            typer.echo(f"  ✗ {err_msg}", err=True)
        raise typer.Exit(1)

    files = [f for f in result.stdout.strip().splitlines() if f]
    categories: dict[str, list[str]] = {"code": [], "test": [], "doc": [], "other": []}
    for f in files:
        categories[_classify_file(f)].append(f)

    output = {
        "trunk_branch": trunk,
        "diff_range": diff_range,
        "total_files": len(files),
        "code_files": len(categories["code"]),
        "test_files": len(categories["test"]),
        "doc_files": len(categories["doc"]),
        "other_files": len(categories["other"]),
        "has_md_changes": len(categories["doc"]) > 0,
        "code_file_list": categories["code"],
        "test_file_list": categories["test"],
        "doc_file_list": categories["doc"],
    }

    if as_json:
        typer.echo(json.dumps(output))
    else:
        typer.echo(f"  {len(files)} files changed ({len(categories['code'])} code, "
                   f"{len(categories['test'])} test, {len(categories['doc'])} doc, "
                   f"{len(categories['other'])} other)")
