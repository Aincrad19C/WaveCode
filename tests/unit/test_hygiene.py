from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_DEPENDENCIES = (
    "langchain",
    "langgraph",
    "llama-index",
    "llama_index",
    "autogen",
    "crewai",
    "openai-agents",
    "openai_agents",
    "claude-agent-sdk",
    "claude_agent_sdk",
    "deepseek-harness",
    "deepseek_harness",
)

# Real-looking keys, not the regex example `sk-[a-zA-Z0-9]+` in docs/08.
SECRET_RE = re.compile(r"sk-[a-zA-Z0-9]{16,}")

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
    ".egg-info",
}

SCAN_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".cfg", ".ini"}


def _iter_source_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.suffix.lower() in SCAN_SUFFIXES or path.name in {".gitignore", ".env.example"}:
            files.append(path)
    return files


def test_no_forbidden_agent_frameworks(repo_root: Path) -> None:
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8").lower()
    for name in FORBIDDEN_DEPENDENCIES:
        assert name not in pyproject, f"forbidden dependency {name} in pyproject.toml"

    src = repo_root / "src"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for name in FORBIDDEN_DEPENDENCIES:
            assert name not in lowered, f"{path} mentions forbidden package {name}"
        assert not re.search(r"^\s*(import openai|from openai\b)", text, re.M), (
            f"{path} imports the OpenAI SDK (not allowed in V1)"
        )


def test_no_literal_api_keys(repo_root: Path) -> None:
    hits: list[str] = []
    for path in _iter_source_files(repo_root):
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_RE.search(text):
            hits.append(str(path.relative_to(repo_root)))
    assert hits == [], f"possible API key literals in: {hits}"
