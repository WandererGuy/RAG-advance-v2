"""Jinja2 prompt loading. Prompts live in .jinja files, never inline (CLAUDE.md 6).

`render_prompt("answer_v1")` reads `app/llm/prompts/answer_v1.jinja`. The version is part of
the filename, so changing a prompt means adding `answer_v2.jinja` — never editing `v1` after a
results file has been produced with it, for the same reason a pipeline with committed results
is frozen.

`render_template` is the same machinery pointed at another directory, and exists so
`eval/judge_prompts/` gets identical treatment (strict undefined, whitespace control, the
version in the filename) without a second copy of this code.

`undefined=StrictUndefined` is the point of the module: a typo in a variable name would
otherwise render as an empty string, and a prompt silently missing its context is a run whose
numbers mean nothing and whose output looks fine.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

PROMPTS_DIR = Path(__file__).resolve().parent
SUFFIX = ".jinja"


class PromptNotFound(FileNotFoundError):
    """A named prompt does not exist. Lists what does, because it is nearly always a typo."""

    def __init__(self, name: str, directory: Path) -> None:
        available = sorted(p.stem for p in directory.glob(f"*{SUFFIX}"))
        super().__init__(
            f"no prompt {name!r} in {directory} (available: {', '.join(available) or 'none'})"
        )
        self.name = name


@lru_cache
def _environment(directory: Path) -> Environment:
    """One environment per directory, cached: templates are read once per process."""
    return Environment(
        loader=FileSystemLoader(directory),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
        autoescape=False,  # noqa: S701 - prompts are text for a model, not HTML
    )


def render_template(directory: Path, name: str, /, **context: Any) -> str:
    """Render `<directory>/<name>.jinja` with `context`. Raises on an unknown variable."""
    try:
        template = _environment(directory).get_template(f"{name}{SUFFIX}")
    except TemplateNotFound as exc:
        raise PromptNotFound(name, directory) from exc
    return template.render(**context).strip()


def render_prompt(name: str, /, **context: Any) -> str:
    """Render a prompt from this directory, e.g. `render_prompt("answer_v1", ...)`."""
    return render_template(PROMPTS_DIR, name, **context)
