"""Protect and restore RPG Maker escape/control codes around translation."""

from __future__ import annotations

import re

# Matches RPG Maker escape codes, printf-style placeholders, HTML line breaks, and newlines.
# Order matters: longer / parameterized tokens before single-char tokens.
_CONTROL_PATTERN = re.compile(
    r"(?:"
    r"\\[A-Za-z]+\[[^\]]*\]"   # \V[1], \C[10], \N[1], \I[5], \af[1], \px[10]
    r"|\\[A-Za-z]+<[^>]*>"     # \fs<20> etc.
    r"|\\[{}$\.|!><\^\\G]"     # \{, \}, \$, \., \|, \!, \>, \<, \^, \\, \G
    r"|%\d+"                   # %1, %2
    r"|<br\s*/?>"              # <br>, <br/>
    r"|\r?\n"                  # newlines
    r")"
)

_PLACEHOLDER_RE = re.compile(r"⟦(\d+)⟧")


def protect_text(text: str) -> tuple[str, list[str]]:
    """Replace control codes with indexed placeholders `⟦0⟧`, `⟦1⟧`, ..."""
    tokens: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        idx = len(tokens)
        tokens.append(match.group(0))
        return f"⟦{idx}⟧"

    protected = _CONTROL_PATTERN.sub(_replace, text)
    return protected, tokens


def restore_text(translated: str, tokens: list[str]) -> str:
    """Restore indexed placeholders back to original control codes."""
    if not tokens:
        return translated

    def _replace(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if 0 <= idx < len(tokens):
            return tokens[idx]
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, translated)
