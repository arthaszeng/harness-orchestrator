"""Lightweight i18n for harness-flow.

Usage::

    from harness.i18n import t, set_lang

    set_lang("zh")          # switch to Chinese
    print(t("init.complete_title"))   # "✅ 初始化完成"

    # with interpolation
    print(t("gate.no_task", suffix=" for 'task-001'"))
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_current_lang: str = "en"


def apply_project_lang_from_cwd(cwd: Path | None = None) -> None:
    """Load ``HarnessConfig`` from *cwd* and set UI language; fall back to English."""
    root = cwd if cwd is not None else Path.cwd()
    try:
        from harness.core.config import HarnessConfig

        cfg = HarnessConfig.load(root)
        set_lang(cfg.project.lang)
    except Exception:
        set_lang("en")


def set_lang(lang: str) -> None:
    global _current_lang
    if lang in ("en", "zh"):
        _current_lang = lang


def get_lang() -> str:
    return _current_lang


def t(key: str, **kwargs: Any) -> str:
    """Look up a translated string by *key*.

    Falls back to English if the key is missing in the current language.
    Supports ``str.format(**kwargs)`` interpolation.
    """
    from harness.i18n import en, zh

    catalogs = {"en": en.MESSAGES, "zh": zh.MESSAGES}
    catalog = catalogs.get(_current_lang, en.MESSAGES)
    template = catalog.get(key) or en.MESSAGES.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
