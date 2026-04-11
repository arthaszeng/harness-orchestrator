"""Shared CLI I/O helpers for Typer command modules."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer

from harness.core.ui import get_ui


def read_stdin_json_object(*, exit_code: int = 1) -> dict[str, Any]:
    """Read a JSON object from stdin with standard validation.

    Validates: (1) stdin is not a TTY, (2) input is non-empty,
    (3) valid JSON, (4) top-level is a dict.

    Raises ``typer.Exit(code=exit_code)`` on any validation failure.
    """
    ui = get_ui()

    if sys.stdin.isatty():
        ui.error("no input on stdin (expected JSON)")
        raise typer.Exit(code=exit_code)

    raw_text = sys.stdin.read().strip()
    if not raw_text:
        ui.error("empty stdin")
        raise typer.Exit(code=exit_code)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        ui.error(f"invalid JSON: {exc}")
        raise typer.Exit(code=exit_code)

    if not isinstance(payload, dict):
        ui.error("expected a JSON object")
        raise typer.Exit(code=exit_code)

    return payload


def emit_git_result(
    result: Any,
    as_json: bool,
    *,
    emit_recovery: bool = True,
) -> None:
    """Format and output a git lifecycle result.

    *result* is expected to have ``.ok``, ``.code``, ``.diagnostic``,
    and ``.context`` attributes (``BranchLifecycleResult`` or ``GitOperationResult``).
    """
    payload = {
        "ok": result.ok,
        "code": result.code,
        "message": getattr(result, "diagnostic", getattr(result, "message", "")),
        "context": result.context,
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"[{result.code}] {payload['message']}")
    if not result.ok:
        if emit_recovery:
            _emit_recovery_hint(result.code)
        raise typer.Exit(code=1)


def _emit_recovery_hint(code: str) -> None:
    """Emit an i18n recovery hint for the given error code, if available."""
    from pathlib import Path

    from harness.i18n import apply_project_lang_from_cwd, t

    apply_project_lang_from_cwd(Path.cwd())
    key = f"git_preflight.recovery.{code}"
    msg = t(key)
    if msg == key:
        msg = t("git_preflight.recovery.generic")
    typer.echo(msg, err=True)
