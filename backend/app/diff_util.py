"""Unified diff helpers for fix review."""

from __future__ import annotations

import difflib


def unified_diff_text(
    original: str,
    revised: str,
    path: str,
    *,
    context_lines: int = 3,
    max_chars: int = 80_000,
) -> str:
    """Return a unified diff string suitable for API responses and UI display."""
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(),
            revised.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
            n=context_lines,
        )
    )
    if not diff_lines:
        return ""
    text = "\n".join(diff_lines)
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n… diff truncated …"
    return text


def diff_line_stats(diff_text: str) -> tuple[int, int]:
    """Return (additions, deletions) counts from a unified diff."""
    if not diff_text:
        return 0, 0
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions
