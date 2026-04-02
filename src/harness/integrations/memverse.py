"""Memverse integration — MCP-only architecture.

Memverse search/add/delete operations run via Cursor MCP tools in the IDE.
Python does not call MCP directly; the generated skill/agent templates
include Memverse instructions when ``integrations.memverse.enabled`` is true.

Configuration lives in ``HarnessConfig.integrations.memverse`` and is
projected into the Jinja2 template context as ``memverse_enabled`` and
``memverse_domain`` (Layer 0 / Base).

This module is intentionally minimal — it serves as the package anchor
for the ``harness.integrations`` namespace and a future home for any
Python-side memory utilities that may be added later.
"""
