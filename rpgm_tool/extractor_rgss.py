"""Text extractor and patcher for RPG Maker XP / VX / VXAce (.rxdata / .rvdata / .rvdata2 & RGSS archives)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from .detector import GameInfo, detect_engine
from .dictionary import load_json_dict
from .rgss_archive import read_rgss_archive
from .ruby_marshal import RubyObject, RubyString, dumps, loads

_PURE_NUMERIC_RE = re.compile(r"^[\d\s.,+\-*/%:=()\[\]]+$")

_RGSS_DB_FIELDS: dict[str, tuple[str, ...]] = {
    "Actors": ("@name", "@nickname", "@description"),
    "Classes": ("@name",),
    "Skills": ("@name", "@description", "@message1", "@message2"),
    "Items": ("@name", "@description"),
    "Weapons": ("@name", "@description"),
    "Armors": ("@name", "@description"),
    "Enemies": ("@name",),
    "States": ("@name", "@description", "@message1", "@message2", "@message3", "@message4"),
}

_EXT_MAP = {
    "RPG Maker XP": ".rxdata",
    "RPG Maker VX": ".rvdata",
    "RPG Maker VX Ace": ".rvdata2",
}


def _to_str(val: Any) -> str | None:
    if isinstance(val, RubyString):
        return val.text
    if isinstance(val, str):
        return val
    return None


def _set_str(val: Any, new_text: str) -> Any:
    if isinstance(val, RubyString):
        val.text = new_text
        return val
    return new_text


def _is_translatable(s: str | None) -> bool:
    if not s:
        return False
    stripped = s.strip()
    if not stripped or _PURE_NUMERIC_RE.match(stripped):
        return False
    return True


def _walk_rgss_data(
    stem: str,
    root_obj: Any,
    bucket: list[str],
    translations: dict[str, str] | None = None,
) -> bool:
    """Walk an RGSS data object to extract strings and optionally apply translations in-place."""
    changed = False

    def handle_val(val: Any) -> Any:
        nonlocal changed
        s = _to_str(val)
        if not _is_translatable(s):
            return val
        assert s is not None
        bucket.append(s)
        if translations is not None:
            tr = translations.get(s)
            if tr:
                changed = True
                return _set_str(val, tr)
        return val

    def handle_event_list(cmds: Any) -> None:
        if not isinstance(cmds, list):
            return
        for cmd in cmds:
            if not isinstance(cmd, RubyObject):
                continue
            code = cmd.ivars.get("@code")
            params = cmd.ivars.get("@parameters")
            if not isinstance(params, list):
                continue
            if code in (401, 405) and len(params) >= 1:
                params[0] = handle_val(params[0])
            elif code == 102 and len(params) >= 1 and isinstance(params[0], list):
                for i in range(len(params[0])):
                    params[0][i] = handle_val(params[0][i])
            elif code in (320, 324) and len(params) >= 2:
                params[1] = handle_val(params[1])

    if stem in _RGSS_DB_FIELDS and isinstance(root_obj, list):
        fields = _RGSS_DB_FIELDS[stem]
        for rec in root_obj:
            if isinstance(rec, RubyObject):
                for f in fields:
                    if f in rec.ivars:
                        rec.ivars[f] = handle_val(rec.ivars[f])
    elif stem == "System" and isinstance(root_obj, RubyObject):
        for f in ("@game_title", "@currency_unit"):
            if f in root_obj.ivars:
                root_obj.ivars[f] = handle_val(root_obj.ivars[f])
        for arr_f in ("@elements", "@skill_types", "@weapon_types", "@armor_types"):
            arr = root_obj.ivars.get(arr_f)
            if isinstance(arr, list):
                for i in range(len(arr)):
                    arr[i] = handle_val(arr[i])
        terms = root_obj.ivars.get("@terms")
        if isinstance(terms, RubyObject):
            for k, v in list(terms.ivars.items()):
                if isinstance(v, list):
                    for i in range(len(v)):
                        v[i] = handle_val(v[i])
                else:
                    terms.ivars[k] = handle_val(v)
    elif stem == "Troops" and isinstance(root_obj, list):
        for troop in root_obj:
            if isinstance(troop, RubyObject):
                if "@name" in troop.ivars:
                    troop.ivars["@name"] = handle_val(troop.ivars["@name"])
                pages = troop.ivars.get("@pages")
                if isinstance(pages, list):
                    for page in pages:
                        if isinstance(page, RubyObject):
                            handle_event_list(page.ivars.get("@list"))
    elif stem == "CommonEvents" and isinstance(root_obj, list):
        for ev in root_obj:
            if isinstance(ev, RubyObject):
                handle_event_list(ev.ivars.get("@list"))
    elif stem.startswith("Map") and stem != "MapInfos" and isinstance(root_obj, RubyObject):
        if "@display_name" in root_obj.ivars:
            root_obj.ivars["@display_name"] = handle_val(root_obj.ivars["@display_name"])
        events = root_obj.ivars.get("@events")
        if isinstance(events, dict):
            for ev in events.values():
                if isinstance(ev, RubyObject):
                    pages = ev.ivars.get("@pages")
                    if isinstance(pages, list):
                        for page in pages:
                            if isinstance(page, RubyObject):
                                handle_event_list(page.ivars.get("@list"))

    return changed


def _load_rgss_data_files(info: GameInfo) -> dict[str, bytes]:
    """Load Data/*.rxdata|rvdata|rvdata2 from loose Data/ dir and/or RGSS archive."""
    ext = _EXT_MAP.get(info.engine)
    if not ext:
        raise ValueError(f"Unsupported RGSS engine: {info.engine}")

    files: dict[str, bytes] = {}
    # 1. Check encrypted archive first
    for archive_glob in ("*.rgss3a", "*.rgss2a", "*.rgssad"):
        for arch in sorted(info.root_dir.glob(archive_glob)):
            for rel, payload in read_rgss_archive(arch).items():
                if rel.lower().startswith("data/") and rel.lower().endswith(ext):
                    files[Path(rel).name] = payload

    # 2. Loose Data/ files take precedence in RGSS
    if info.data_dir and info.data_dir.is_dir():
        for fp in sorted(info.data_dir.glob(f"*{ext}")):
            files[fp.name] = fp.read_bytes()

    return files


def extract_rgss_texts(target: str | Path | GameInfo) -> list[str]:
    """Extract unique translatable strings from RPG Maker XP / VX / VXAce."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    raw_files = _load_rgss_data_files(info)
    collected: list[str] = []

    for fname, raw in sorted(raw_files.items()):
        stem = Path(fname).stem
        if stem == "Scripts":
            continue
        obj = loads(raw)
        _walk_rgss_data(stem, obj, collected, translations=None)

    return list(dict.fromkeys(collected))


def mount_rgss(
    target: str | Path | GameInfo,
    dict_path: str | Path,
) -> list[Path]:
    """Patch RGSS Data/ files with translations, backing up originals to *.mtoollite.bak."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    raw_tr = load_json_dict(dict_path)
    translations = {k: ("" if v == "__FILTERED__" else v) for k, v in raw_tr.items()}
    raw_files = _load_rgss_data_files(info)

    data_dir = info.data_dir or (info.root_dir / "Data")
    data_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for fname, raw in sorted(raw_files.items()):
        stem = Path(fname).stem
        if stem == "Scripts":
            continue
        obj = loads(raw)
        bucket: list[str] = []
        changed = _walk_rgss_data(stem, obj, bucket, translations=translations)
        if not changed:
            continue

        out_fp = data_dir / fname
        bak_fp = data_dir / f"{fname}.mtoollite.bak"
        if out_fp.is_file() and not bak_fp.exists():
            shutil.copy2(out_fp, bak_fp)
        out_fp.write_bytes(dumps(obj))
        written.append(out_fp)

    return written


def unmount_rgss(target: str | Path | GameInfo) -> int:
    """Restore backed-up RGSS Data/ files and remove patched files."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    data_dir = info.data_dir or (info.root_dir / "Data")
    if not data_dir.is_dir():
        return 0

    restored = 0
    for bak_fp in sorted(data_dir.glob("*.mtoollite.bak")):
        orig_fp = data_dir / bak_fp.name[: -len(".mtoollite.bak")]
        shutil.move(str(bak_fp), str(orig_fp))
        restored += 1
    return restored
