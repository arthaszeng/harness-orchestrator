"""README quickstart command consistency checks."""

from __future__ import annotations

import re
from pathlib import Path

from harness.cli import app
from typer.testing import CliRunner


runner = CliRunner()


def test_zh_readme_quickstart_has_core_keywords():
    zh = Path(__file__).resolve().parents[1] / "README.zh-CN.md"
    content = zh.read_text(encoding="utf-8")
    assert "10 分钟" in content
    assert "git-preflight" in content
    assert "/harness-plan" in content


def test_readme_happy_path_commands_exist_in_cli():
    readme = Path(__file__).resolve().parents[1] / "README.md"
    content = readme.read_text(encoding="utf-8")
    match = re.search(
        r"### 0\. 10-minute happy path.*?```bash(.*?)```",
        content,
        flags=re.DOTALL,
    )
    assert match, "README is missing the 10-minute happy path code block"
    commands = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("harness "):
            continue
        token = line.split()[1]
        if token.startswith("-"):
            continue
        commands.append(token)
    help_output = runner.invoke(app, ["--help"]).output
    missing = sorted({c for c in commands if c not in help_output})
    assert not missing, f"README references unknown CLI commands: {missing}"
