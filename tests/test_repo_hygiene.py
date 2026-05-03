"""Anti-regression: prevent reintroduction of the killed-claim phrasing.

Per ``MOAT-CHECK-bcbs239.md`` and ``docs/PRD.md`` Appendix B, the following
phrases are banned across all markdown, SQL, and Python source. This test
greps the repo at every CI run and fails with file paths if any phrase
reappears.
"""

from __future__ import annotations

import pathlib

import pytest

KILLED_PHRASES = [
    "replaces collibra",
    "replaces alation",
    "replaces atlan",
    "replaces capgemini",
    "replaces big-4",
    "production-ready bcbs 239 evidence layer",
    "production-grade for regulator review",
    "big-4 alternative",
]

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
# Scan markdown, SQL, Python source AND the dashboard's TypeScript / JSX so
# the discipline applies to portfolio web copy too.
SCANNED_SUFFIXES = {".md", ".sql", ".py", ".ts", ".tsx", ".mjs"}
SKIP_PARTS = {
    ".venv",
    "node_modules",
    ".next",
    "site-packages",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "target",
    "__pycache__",
}
# Files that LEGITIMATELY quote the killed phrases as part of codifying the rule.
# Adding new files here weakens the discipline — only the rule-definition files belong.
RULE_DEFINITION_FILES = {
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "docs" / "PRD.md",
}
THIS_FILE = pathlib.Path(__file__).resolve()


def _candidate_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    rule_resolved = {p.resolve() for p in RULE_DEFINITION_FILES}
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SCANNED_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.resolve() == THIS_FILE:
            continue
        if path.resolve() in rule_resolved:
            continue
        out.append(path)
    return out


@pytest.mark.parametrize("phrase", KILLED_PHRASES)
def test_no_killed_phrasing(phrase: str) -> None:
    """No artifact may reintroduce a moat-check killed-claim phrase."""
    hits: list[str] = []
    for path in _candidate_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except (PermissionError, OSError):
            continue
        if phrase in text:
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert not hits, (
        f"Killed phrase {phrase!r} reintroduced in: {hits}. "
        "Per MOAT-CHECK-bcbs239.md this framing is banned forever."
    )
