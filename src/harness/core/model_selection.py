"""Model validation and Cursor local model discovery helpers."""

from __future__ import annotations

import json
import os
import platform
import re
import sqlite3
from pathlib import Path

MODEL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]*$")

_CURSOR_MODEL_KEYS: tuple[str, ...] = (
    "cursor/lastSingleModelPreference",
    "cursor/bestOfNEnsemblePreferences",
)


def validate_model_name(value: str) -> bool:
    """Return True if value is 'inherit' or a valid model identifier."""
    value = value.strip()
    if value == "inherit":
        return True
    return bool(MODEL_RE.fullmatch(value))


def detect_cursor_recent_models(limit: int = 6) -> list[str]:
    """Best-effort read of recently used Cursor models from local state."""
    db_path = _cursor_state_db_path()
    if db_path is None or not db_path.exists():
        return []

    rows: list[tuple[str, str]] = []
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        cur = conn.cursor()
        for key in _CURSOR_MODEL_KEYS:
            cur.execute("SELECT value FROM ItemTable WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                continue
            raw_value = row[0]
            if isinstance(raw_value, bytes):
                try:
                    raw_value = raw_value.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            if isinstance(raw_value, str):
                rows.append((key, raw_value))
    except Exception:  # noqa: BLE001 — intentional broad catch for best-effort detection
        import logging
        logging.getLogger("harness.model_selection").debug(
            "Failed to read Cursor models from state.vscdb", exc_info=True,
        )
        return []
    finally:
        if conn is not None:
            conn.close()

    seen: set[str] = set()
    models: list[str] = []
    for key, raw_value in rows:
        for model in _extract_models_for_key(key, raw_value):
            if model not in seen:
                seen.add(model)
                models.append(model)
                if len(models) >= limit:
                    return models
    return models


def resolve_effective_model(*candidates: str, available_models: list[str] | None = None) -> str:
    """Return the first safe model choice or empty string for IDE default.

    Empty string means: do not pin a model in agent frontmatter, which lets
    Cursor use the IDE default model.
    """
    available = set(available_models or [])
    for candidate in candidates:
        model = candidate.strip()
        if not model or model == "inherit":
            continue
        if not validate_model_name(model):
            continue
        if available_models is not None and model not in available:
            continue
        return model
    return ""


def _cursor_state_db_path() -> Path | None:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
    if system == "Linux":
        return Path.home() / ".config/Cursor/User/globalStorage/state.vscdb"
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return None
        return Path(appdata) / "Cursor/User/globalStorage/state.vscdb"
    return None


def _extract_models_for_key(key: str, raw_value: str) -> list[str]:
    try:
        payload = json.loads(raw_value)
    except Exception:
        return []

    if key == "cursor/lastSingleModelPreference":
        return _collect_models(payload)
    if key == "cursor/bestOfNEnsemblePreferences":
        return _collect_models(payload)
    return []


def _collect_models(payload: object) -> list[str]:
    models: list[str] = []
    if isinstance(payload, str):
        model = payload.strip()
        if model and model != "inherit" and validate_model_name(model):
            models.append(model)
        return models

    if isinstance(payload, list):
        for item in payload:
            models.extend(_collect_models(item))
        return models

    if isinstance(payload, dict):
        for value in payload.values():
            models.extend(_collect_models(value))
        return models

    return models
