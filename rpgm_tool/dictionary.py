"""Dictionary (ManualTransFile.json) and Glossary management."""

from __future__ import annotations

import json
from pathlib import Path


def load_json_dict(path: str | Path) -> dict[str, str]:
    """Load a UTF-8 JSON string-to-string dictionary."""
    p = Path(path)
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {p}, got {type(data).__name__}")
    return {str(k): "" if v is None else str(v) for k, v in data.items()}


def save_json_dict(path: str | Path, data: dict[str, str]) -> Path:
    """Save a UTF-8 JSON dictionary with readable formatting."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def merge_extracted(
    existing: dict[str, str], extracted: list[str]
) -> tuple[dict[str, str], int]:
    """Merge newly extracted source strings into existing dictionary without overwriting translations."""
    merged = dict(existing)
    added = 0
    for text in extracted:
        if text and text not in merged:
            merged[text] = ""
            added += 1
    return merged, added


def get_untranslated(data: dict[str, str]) -> list[str]:
    """Return keys that do not yet have a non-empty translation and are not filtered."""
    return [k for k, v in data.items() if not v or not v.strip() if v != "__FILTERED__"]
