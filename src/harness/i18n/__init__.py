"""Lightweight i18n for harness-flow.

Usage::

    from harness.i18n import t, set_lang

    set_lang("zh")          # switch to Chinese
    print(t("init.done"))   # "初始化完成！"

    # with interpolation
    print(t("init.found", line="pytest.ini"))  # e.g. "    Found pytest.ini"
"""

from __future__ import annotations

from typing import Any

_current_lang: str = "en"


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
