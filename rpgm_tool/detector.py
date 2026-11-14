"""Game engine detection for RPG Maker and other indie game engines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import configparser


@dataclass(frozen=True)
class GameInfo:
    engine: str
    root_dir: Path
    data_dir: Path | None = None
    js_dir: Path | None = None
    exe_path: Path | None = None
    is_mvmz: bool = False


def _resolve_root(target: str | Path) -> tuple[Path, Path | None]:
    p = Path(target).resolve()
    if p.is_file():
        return p.parent, p
    # Find primary exe if directory was passed
    for candidate in ("Game.exe", "RPG_RT.exe"):
        exe = p / candidate
        if exe.is_file():
            return p, exe
    exes = sorted(p.glob("*.exe"))
    return p, (exes[0] if exes else None)


def detect_engine(target: str | Path) -> GameInfo:
    """Detect the game engine from a game directory or executable path."""
    root, exe = _resolve_root(target)
    if not root.exists():
        raise FileNotFoundError(f"Game path does not exist: {root}")

    # 1. RPG Maker MZ (flat layout: js/rmmz_core.js + data/System.json)
    if (root / "js" / "rmmz_core.js").is_file() or (
        (root / "data" / "System.json").is_file()
        and (root / "js" / "main.js").is_file()
        and not (root / "www").is_dir()
    ):
        return GameInfo(
            engine="RPG Maker MZ",
            root_dir=root,
            data_dir=root / "data",
            js_dir=root / "js",
            exe_path=exe,
            is_mvmz=True,
        )

    # 2. RPG Maker MV (www/ layout or flat layout with rpg_core.js)
    if (root / "www" / "data" / "System.json").is_file() or (
        root / "www" / "js" / "rpg_core.js"
    ).is_file():
        return GameInfo(
            engine="RPG Maker MV",
            root_dir=root,
            data_dir=root / "www" / "data",
            js_dir=root / "www" / "js",
            exe_path=exe,
            is_mvmz=True,
        )
    if (root / "js" / "rpg_core.js").is_file() or (root / "data" / "System.json").is_file():
        return GameInfo(
            engine="RPG Maker MV",
            root_dir=root,
            data_dir=root / "data",
            js_dir=root / "js",
            exe_path=exe,
            is_mvmz=True,
        )

    # 3. RPG Maker XP / VX / VX Ace (Game.ini + RGSS*.dll or Data/*.rxdata|rvdata|rvdata2)
    game_ini = root / "Game.ini"
    if game_ini.is_file():
        parser = configparser.ConfigParser()
        try:
            parser.read(game_ini, encoding="utf-8-sig")
        except UnicodeDecodeError:
            parser.read(game_ini, encoding="cp932", errors="ignore")
        library = parser.get("Game", "Library", fallback="").upper()
        if "RGSS3" in library or any(root.glob("*.rgss3a")):
            return GameInfo(engine="RPG Maker VX Ace", root_dir=root, data_dir=root / "Data", exe_path=exe)
        if "RGSS2" in library or any(root.glob("*.rgss2a")):
            return GameInfo(engine="RPG Maker VX", root_dir=root, data_dir=root / "Data", exe_path=exe)
        if "RGSS1" in library or any(root.glob("*.rgssad")):
            return GameInfo(engine="RPG Maker XP", root_dir=root, data_dir=root / "Data", exe_path=exe)

    # 4. RPG Maker 2000 / 2003
    if (root / "RPG_RT.exe").is_file() or (root / "RPG_RT.ldb").is_file():
        return GameInfo(engine="RPG Maker 2000/2003", root_dir=root, data_dir=root, exe_path=exe)

    # 5. Wolf RPG Editor
    if (
        (root / "Data.wolf").is_file()
        or any(root.glob("*.wolf"))
        or (root / "Data" / "BasicData").is_dir()
        or (root / "data" / "BasicData").is_dir()
        or (root / "Data" / "MapData").is_dir()
        or (root / "data" / "MapData").is_dir()
        or (root / "Data" / "Game.dat").is_file()
        or (root / "data" / "Game.dat").is_file()
    ):
        data_d = (root / "Data") if (root / "Data").exists() else (root / "data")
        return GameInfo(engine="Wolf RPG", root_dir=root, data_dir=data_d, exe_path=exe)

    # 6. Ren'Py
    if (root / "renpy").is_dir() and (root / "game").is_dir():
        return GameInfo(engine="Ren'Py", root_dir=root, data_dir=root / "game", exe_path=exe)

    # 7. TyranoBuilder / TyranoScript
    if (root / "tyrano").is_dir():
        return GameInfo(engine="TyranoBuilder", root_dir=root, data_dir=root / "data", exe_path=exe)

    return GameInfo(engine="Unknown", root_dir=root, exe_path=exe)
