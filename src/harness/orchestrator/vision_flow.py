"""Vision generation orchestration — Advisor-driven vision create/update."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from harness.drivers.base import AgentDriver
from harness.i18n import t


@dataclass
class ProjectContext:
    """Project context gathered for the Advisor."""
    project_name: str = ""
    existing_vision: str = ""
    reflection: str = ""
    progress: str = ""
    doc_summaries: list[str] = field(default_factory=list)
    directory_tree: str = ""


@dataclass
class AdvisorOutput:
    """Parsed output from the Advisor agent."""
    vision_content: str
    questions: list[str] = field(default_factory=list)


def gather_context(project_root: Path) -> ProjectContext:
    """Collect project context for the Advisor."""
    agents_dir = project_root / ".agents"
    ctx = ProjectContext()

    ctx.project_name = project_root.name

    # Existing vision
    vision_path = agents_dir / "vision.md"
    if vision_path.exists():
        ctx.existing_vision = vision_path.read_text(encoding="utf-8")[:3000]

    # Reflector output
    reflection_path = agents_dir / "reflection.md"
    if reflection_path.exists():
        ctx.reflection = reflection_path.read_text(encoding="utf-8")[:3000]

    # Progress
    progress_path = agents_dir / "progress.md"
    if progress_path.exists():
        ctx.progress = progress_path.read_text(encoding="utf-8")[:3000]

    # Summaries from doc/*.md
    doc_dir = project_root / "doc"
    if doc_dir.is_dir():
        for md_file in sorted(doc_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")[:2000]
            ctx.doc_summaries.append(f"### {md_file.name}\n{content}")

    # Shallow directory structure
    ctx.directory_tree = _get_directory_tree(project_root)

    return ctx


def build_advisor_prompt(ctx: ProjectContext, user_input: str) -> str:
    """Build the Advisor LLM prompt from context."""
    sections: list[str] = []

    sections.append(t("prompt.advisor_project", name=ctx.project_name))
    sections.append(t("prompt.advisor_input", input=user_input))

    if ctx.existing_vision:
        sections.append(t("prompt.advisor_vision", vision=ctx.existing_vision))

    if ctx.progress:
        sections.append(t("prompt.advisor_progress", progress=ctx.progress))

    if ctx.reflection:
        sections.append(t("prompt.advisor_reflection", reflection=ctx.reflection))

    if ctx.doc_summaries:
        docs = "\n\n".join(ctx.doc_summaries[:3])
        sections.append(t("prompt.advisor_docs", docs=docs))

    if ctx.directory_tree:
        sections.append(t("prompt.advisor_tree", tree=ctx.directory_tree))

    sections.append(t("prompt.advisor_instruction"))

    return "\n\n".join(sections)


def invoke_advisor(
    driver: AgentDriver,
    agent_name: str,
    ctx: ProjectContext,
    user_input: str,
    cwd: Path,
    *,
    timeout: int = 300,
    on_output: Callable[[str], None] | None = None,
    model: str = "",
) -> AdvisorOutput:
    """Invoke the Advisor agent and return parsed output."""
    prompt = build_advisor_prompt(ctx, user_input)
    result = driver.invoke(
        agent_name, prompt, cwd,
        readonly=True, timeout=timeout, on_output=on_output, model=model,
    )

    if not result.success:
        return AdvisorOutput(
            vision_content="",
            questions=[t("prompt.advisor_failed")],
        )

    return parse_advisor_output(result.output)


def parse_advisor_output(output: str) -> AdvisorOutput:
    """Parse Advisor output into vision text and follow-up questions."""
    questions: list[str] = []
    vision_content = output.strip()

    # Split off follow-up questions
    marker = "ADVISOR_QUESTIONS:"
    if marker in output:
        parts = output.split(marker, 1)
        vision_content = parts[0].strip()
        q_section = parts[1].strip()
        for line in q_section.split("\n"):
            line = line.strip()
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
            if cleaned:
                questions.append(cleaned)

    return AdvisorOutput(vision_content=vision_content, questions=questions)


def write_vision(agents_dir: Path, content: str) -> int:
    """Write vision.md and return the encoded byte length."""
    vision_path = agents_dir / "vision.md"
    vision_path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def _get_directory_tree(project_root: Path, max_depth: int = 2) -> str:
    """Return a directory listing, excluding common noise paths."""
    try:
        result = subprocess.run(
            [
                "find", str(project_root),
                "-maxdepth", str(max_depth),
                "-type", "d",
                "-not", "-path", "*/.git/*",
                "-not", "-path", "*/__pycache__/*",
                "-not", "-path", "*/node_modules/*",
                "-not", "-path", "*/.next/*",
                "-not", "-path", "*/.agents/tasks/*",
                "-not", "-path", "*/.agents/archive/*",
                "-not", "-name", ".git",
                "-not", "-name", "__pycache__",
                "-not", "-name", "node_modules",
                "-not", "-name", ".next",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            # Normalize to paths relative to project root
            rel = []
            for line in lines:
                p = Path(line)
                try:
                    rel.append(str(p.relative_to(project_root)))
                except ValueError:
                    rel.append(line)
            return "\n".join(sorted(rel))[:1500]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: shallow scan
    dirs = []
    for p in sorted(project_root.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and p.name not in {
            "__pycache__", "node_modules", ".next",
        }:
            dirs.append(p.name + "/")
    return "\n".join(dirs)[:1500]
