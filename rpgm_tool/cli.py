"""CLI entry point for rpgm_tool (Phase 1 & Phase 2)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .detector import detect_engine
from .dictionary import load_json_dict, merge_extracted, save_json_dict
from .extractor_2k3 import extract_2k3_texts
from .extractor_mvmz import extract_mvmz_texts
from .extractor_rgss import extract_rgss_texts, mount_rgss, unmount_rgss
from .extractor_wolf import extract_wolf_texts, mount_wolf, unmount_wolf
from .injector_mvmz import mount_mvmz, unmount_mvmz
from .modifier_mvmz import mount_cheat_mvmz, unmount_cheat_mvmz
from .translator import TranslatorConfig, translate_dictionary_file


def _cmd_detect(args: argparse.Namespace) -> int:
    info = detect_engine(args.game_path)
    print(f"Engine   : {info.engine}")
    print(f"Root Dir : {info.root_dir}")
    if info.data_dir:
        print(f"Data Dir : {info.data_dir}")
    if info.js_dir:
        print(f"JS Dir   : {info.js_dir}")
    if info.exe_path:
        print(f"Exe Path : {info.exe_path}")
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    info = detect_engine(args.game_path)
    if info.is_mvmz:
        texts = extract_mvmz_texts(info)
    elif info.engine in ("RPG Maker XP", "RPG Maker VX", "RPG Maker VX Ace"):
        texts = extract_rgss_texts(info)
    elif info.engine == "RPG Maker 2000/2003":
        texts = extract_2k3_texts(info)
    elif info.engine == "Wolf RPG":
        texts = extract_wolf_texts(info)
    else:
        print(f"Error: Extraction not yet supported for engine: {info.engine}", file=sys.stderr)
        return 1
    out_path = Path(args.output) if args.output else (info.root_dir / "ManualTransFile.json")
    existing = load_json_dict(out_path)
    merged, added = merge_extracted(existing, texts)
    save_json_dict(out_path, merged)
    print(f"Engine    : {info.engine}")
    print(f"Extracted : {len(texts)} unique strings ({added} new)")
    print(f"Saved to  : {out_path}")
    return 0


def _cmd_translate(args: argparse.Namespace) -> int:
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("Error: --api-key or OPENAI_API_KEY / DEEPSEEK_API_KEY is required.", file=sys.stderr)
        return 1

    cfg = TranslatorConfig(
        api_key=api_key,
        base_url=args.base_url,
        model=args.model,
        target_lang=args.target_lang,
        batch_size=args.batch_size,
        max_workers=args.workers,
    )

    def _progress(done: int, total: int) -> None:
        print(f"Progress: {done}/{total}")

    done, total = translate_dictionary_file(
        args.dict_path,
        cfg,
        glossary_path=args.glossary,
        on_progress=_progress,
    )
    print(f"Completed: {done}/{total} entries translated.")
    return 0


def _cmd_mount(args: argparse.Namespace) -> int:
    info = detect_engine(args.game_path)
    if info.is_mvmz:
        res = mount_mvmz(
            info,
            dict_path=args.dict,
            capture_untranslated=args.capture,
        )
        print("Mounted MToolLite_Translator successfully:")
        for k, v in res.items():
            print(f"  {k}: {v}")
        return 0
    if info.engine in ("RPG Maker XP", "RPG Maker VX", "RPG Maker VX Ace"):
        dict_file = args.dict or (info.root_dir / "ManualTransFile.json")
        written = mount_rgss(info, dict_file)
        print(f"Patched {len(written)} RGSS data files (backups saved as *.mtoollite.bak).")
        return 0
    if info.engine == "Wolf RPG":
        dict_file = args.dict or (info.root_dir / "ManualTransFile.json")
        written = mount_wolf(info, dict_file)
        print(f"Patched {len(written)} Wolf RPG data files (backups saved as *.mtoollite.bak).")
        return 0
    print(f"Error: Mount not supported for engine: {info.engine}", file=sys.stderr)
    return 1


def _cmd_unmount(args: argparse.Namespace) -> int:
    info = detect_engine(args.game_path)
    if info.is_mvmz:
        changed = unmount_mvmz(info)
        if changed:
            print("Unmounted MToolLite_Translator and restored plugins.js.")
        else:
            print("Nothing to unmount.")
        return 0
    if info.engine in ("RPG Maker XP", "RPG Maker VX", "RPG Maker VX Ace"):
        restored = unmount_rgss(info)
        print(f"Restored {restored} RGSS data files from backups.")
        return 0
    if info.engine == "Wolf RPG":
        restored = unmount_wolf(info)
        print(f"Restored {restored} Wolf RPG data files from backups.")
        return 0
    print(f"Error: Unmount not supported for engine: {info.engine}", file=sys.stderr)
    return 1


def _cmd_cheat(args: argparse.Namespace) -> int:
    res = mount_cheat_mvmz(args.game_path)
    print("Mounted MToolLite_Cheat (Press F9 in-game to toggle):")
    for k, v in res.items():
        print(f"  {k}: {v}")
    return 0


def _cmd_uncheat(args: argparse.Namespace) -> int:
    changed = unmount_cheat_mvmz(args.game_path)
    print("Unmounted MToolLite_Cheat." if changed else "MToolLite_Cheat was not mounted.")
    return 0


def _cmd_gui(_args: argparse.Namespace) -> int:
    from .gui import launch_gui

    return launch_gui()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpgm_tool",
        description="RPG Maker Translation Tool (Phase 1 & 2: Extract, Translate, Non-destructive Mount)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_det = sub.add_parser("detect", help="Detect game engine")
    p_det.add_argument("game_path", help="Path to game directory or .exe")
    p_det.set_defaults(func=_cmd_detect)

    p_ext = sub.add_parser("extract", help="Extract MV/MZ text into ManualTransFile.json")
    p_ext.add_argument("game_path", help="Path to game directory or .exe")
    p_ext.add_argument("-o", "--output", help="Output JSON path (default: <game>/ManualTransFile.json)")
    p_ext.set_defaults(func=_cmd_extract)

    p_tr = sub.add_parser("translate", help="Translate untranslated entries in ManualTransFile.json")
    p_tr.add_argument("dict_path", help="Path to ManualTransFile.json")
    p_tr.add_argument("--glossary", help="Optional glossary JSON file")
    p_tr.add_argument("--api-key", help="API key (or set OPENAI_API_KEY / DEEPSEEK_API_KEY)")
    p_tr.add_argument("--base-url", default="https://api.deepseek.com/v1", help="OpenAI-compatible base URL")
    p_tr.add_argument("--model", default="deepseek-chat", help="Model name")
    p_tr.add_argument("--target-lang", default="Simplified Chinese", help="Target language")
    p_tr.add_argument("--batch-size", type=int, default=20, help="Strings per API request")
    p_tr.add_argument("--workers", type=int, default=4, help="Concurrent worker threads")
    p_tr.set_defaults(func=_cmd_translate)

    p_mnt = sub.add_parser("mount", help="Mount non-destructive translation plugin into MV/MZ game")
    p_mnt.add_argument("game_path", help="Path to game directory or .exe")
    p_mnt.add_argument("--dict", help="Path to ManualTransFile.json to copy into game")
    p_mnt.add_argument("--capture", action="store_true", help="Capture untranslated runtime strings")
    p_mnt.set_defaults(func=_cmd_mount)

    p_unmnt = sub.add_parser("unmount", help="Unmount translator and restore backups")
    p_unmnt.add_argument("game_path", help="Path to game directory or .exe")
    p_unmnt.set_defaults(func=_cmd_unmount)

    p_cht = sub.add_parser("cheat", help="Mount built-in QoL/Modifier overlay (MV/MZ, press F9)")
    p_cht.add_argument("game_path", help="Path to game directory or .exe")
    p_cht.set_defaults(func=_cmd_cheat)

    p_uncht = sub.add_parser("uncheat", help="Unmount built-in QoL/Modifier overlay")
    p_uncht.add_argument("game_path", help="Path to game directory or .exe")
    p_uncht.set_defaults(func=_cmd_uncheat)

    p_gui = sub.add_parser("gui", help="Launch PySide6 desktop GUI")
    p_gui.set_defaults(func=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
