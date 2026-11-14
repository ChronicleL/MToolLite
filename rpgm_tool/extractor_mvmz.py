"""Static text extractor for RPG Maker MV / MZ JSON data files."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .detector import GameInfo, detect_engine

_PURE_NUMERIC_RE = re.compile(r"^[\d\s.,+\-*/%:=()\[\]]+$")

_SIMPLE_DB_FIELDS: dict[str, tuple[str, ...]] = {
    "Actors.json": ("name", "nickname", "profile"),
    "Classes.json": ("name",),
    "Skills.json": ("name", "description", "message1", "message2"),
    "Items.json": ("name", "description"),
    "Weapons.json": ("name", "description"),
    "Armors.json": ("name", "description"),
    "Enemies.json": ("name",),
    "States.json": ("name", "description", "message1", "message2", "message3", "message4"),
}


def _is_translatable(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if _PURE_NUMERIC_RE.match(stripped):
        return False
    return True


def _add_if_valid(bucket: list[str], value: object) -> None:
    if _is_translatable(value):
        bucket.append(value)  # type: ignore[arg-type]


def _extract_event_list(commands: object, bucket: list[str]) -> None:
    if not isinstance(commands, list):
        return
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        code = cmd.get("code")
        params = cmd.get("parameters")
        if not isinstance(params, list):
            continue

        if code == 101 and len(params) > 4:
            # RPG Maker MZ Show Text speaker name
            _add_if_valid(bucket, params[4])
        elif code in (401, 405) and len(params) >= 1:
            # Show Text / Show Scrolling Text
            _add_if_valid(bucket, params[0])
        elif code == 102 and len(params) >= 1 and isinstance(params[0], list):
            # Show Choices
            for choice in params[0]:
                _add_if_valid(bucket, choice)
        elif code in (320, 324, 325) and len(params) >= 2:
            # Change Name / Nickname / Profile
            _add_if_valid(bucket, params[1])


def _extract_system(system_data: object, bucket: list[str]) -> None:
    if not isinstance(system_data, dict):
        return
    _add_if_valid(bucket, system_data.get("gameTitle"))
    _add_if_valid(bucket, system_data.get("currencyUnit"))

    for list_key in ("elements", "equipTypes", "skillTypes", "weaponTypes", "armorTypes"):
        items = system_data.get(list_key)
        if isinstance(items, list):
            for item in items:
                _add_if_valid(bucket, item)

    terms = system_data.get("terms")
    if isinstance(terms, dict):
        for term_key in ("basic", "commands", "params"):
            items = terms.get(term_key)
            if isinstance(items, list):
                for item in items:
                    _add_if_valid(bucket, item)
        messages = terms.get("messages")
        if isinstance(messages, dict):
            for msg in messages.values():
                _add_if_valid(bucket, msg)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract_mvmz_texts(target: str | Path | GameInfo) -> list[str]:
    """Extract unique translatable strings from an RPG Maker MV or MZ project."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    if not info.is_mvmz or info.data_dir is None or not info.data_dir.is_dir():
        raise ValueError(f"Target is not a valid RPG Maker MV/MZ game: {info.root_dir} ({info.engine})")

    data_dir = info.data_dir
    collected: list[str] = []

    # 1. Standard database arrays
    for filename, fields in _SIMPLE_DB_FIELDS.items():
        fp = data_dir / filename
        if not fp.is_file():
            continue
        records = _load_json(fp)
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict):
                continue
            for field in fields:
                _add_if_valid(collected, rec.get(field))

    # 2. System.json
    system_fp = data_dir / "System.json"
    if system_fp.is_file():
        _extract_system(_load_json(system_fp), collected)

    # 3. Troops.json
    troops_fp = data_dir / "Troops.json"
    if troops_fp.is_file():
        troops = _load_json(troops_fp)
        if isinstance(troops, list):
            for troop in troops:
                if not isinstance(troop, dict):
                    continue
                _add_if_valid(collected, troop.get("name"))
                for page in troop.get("pages") or []:
                    if isinstance(page, dict):
                        _extract_event_list(page.get("list"), collected)

    # 4. CommonEvents.json
    common_fp = data_dir / "CommonEvents.json"
    if common_fp.is_file():
        events = _load_json(common_fp)
        if isinstance(events, list):
            for ev in events:
                if isinstance(ev, dict):
                    _extract_event_list(ev.get("list"), collected)

    # 5. MapXXX.json
    for map_fp in sorted(data_dir.glob("Map[0-9][0-9][0-9].json")):
        map_data = _load_json(map_fp)
        if not isinstance(map_data, dict):
            continue
        _add_if_valid(collected, map_data.get("displayName"))
        for ev in map_data.get("events") or []:
            if not isinstance(ev, dict):
                continue
            for page in ev.get("pages") or []:
                if isinstance(page, dict):
                    _extract_event_list(page.get("list"), collected)

    # 6. MapInfos.json (Map names in editor / display)
    map_infos_fp = data_dir / "MapInfos.json"
    if map_infos_fp.is_file():
        map_infos = _load_json(map_infos_fp)
        if isinstance(map_infos, list):
            for info_rec in map_infos:
                if isinstance(info_rec, dict):
                    _add_if_valid(collected, info_rec.get("name"))

    # 7. Animations.json
    anim_fp = data_dir / "Animations.json"
    if anim_fp.is_file():
        anims = _load_json(anim_fp)
        if isinstance(anims, list):
            for anim in anims:
                if isinstance(anim, dict):
                    _add_if_valid(collected, anim.get("name"))

    # Preserve order while deduplicating
    return list(dict.fromkeys(collected))
