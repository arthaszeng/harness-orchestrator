"""harness-flow: Cursor-native multi-agent development framework."""

from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("harness-flow")
except Exception:
    __version__ = "0.0.0-dev"
