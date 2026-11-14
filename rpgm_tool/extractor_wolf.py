"""Wolf RPG Editor (.mps, .dat) binary parser, text extractor, and patcher."""

from __future__ import annotations

import re
import shutil
import struct
from pathlib import Path
from typing import Any

from .detector import GameInfo, detect_engine
from .dictionary import load_json_dict

_PURE_NUMERIC_RE = re.compile(r"^[\d\s.,+\-*/%:=()\[\]_#@><]+$")


def _is_translatable(s: str | None) -> bool:
    if not s:
        return False
    stripped = s.strip()
    if not stripped or _PURE_NUMERIC_RE.match(stripped):
        return False
    if stripped.startswith(("/", "//", "#", "@")):
        return False
    if any(ord(c) < 32 and c not in ("\r", "\n", "\t") for c in stripped):
        return False
    return True


def _has_cjk_or_kana(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" for c in s)


class BinaryReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read_u1(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_u2(self) -> int:
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def read_u4(self) -> int:
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_s4(self) -> int:
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_bytes(self, n: int) -> bytes:
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def read_t_str(self) -> tuple[str, bytes]:
        length = self.read_u4()
        raw = self.read_bytes(length)
        # null-terminated string: strip trailing null byte if present
        payload = raw[:-1] if raw and raw[-1] == 0 else raw
        for enc in ("utf-8", "cp932"):
            try:
                return payload.decode(enc), raw
            except UnicodeDecodeError:
                continue
        return payload.decode("cp932", errors="replace"), raw


def _encode_t_str(text: str, original_raw: bytes) -> bytes:
    """Encode string preserving original trailing null and encoding."""
    had_null = bool(original_raw and original_raw[-1] == 0)
    # Prefer utf-8 if original was valid utf-8, else cp932
    enc = "utf-8"
    try:
        (original_raw[:-1] if had_null else original_raw).decode("utf-8")
    except UnicodeDecodeError:
        enc = "cp932"

    try:
        encoded = text.encode(enc)
    except UnicodeEncodeError:
        encoded = text.encode("utf-8")
    if had_null:
        encoded += b"\x00"
    return struct.pack("<I", len(encoded)) + encoded


class WolfEventCommand:
    def __init__(self, param_count: int, cmd_type: int, param_data: bytes, branch_depth: int, strings: list[str], raw_strings: list[bytes], route_bytes: bytes) -> None:
        self.param_count = param_count
        self.cmd_type = cmd_type
        self.param_data = param_data
        self.branch_depth = branch_depth
        self.strings = strings
        self.raw_strings = raw_strings
        self.route_bytes = route_bytes

    @classmethod
    def read(cls, r: BinaryReader) -> WolfEventCommand:
        param_count = r.read_u1()
        if param_count == 0:
            return cls(0, 0, b"", 0, [], [], b"")

        cmd_type = r.read_u4()
        param_bytes_len = param_count * 4 - 4
        param_data = r.read_bytes(param_bytes_len)
        branch_depth = r.read_u1()
        string_count = r.read_u1()

        strings: list[str] = []
        raw_strings: list[bytes] = []
        for _ in range(string_count):
            s, raw = r.read_t_str()
            strings.append(s)
            raw_strings.append(raw)

        have_route = r.read_u1()
        route_bytes = b""
        if have_route != 0:
            # Route block
            route_start = r.pos
            r.pos += 6  # animation_freq, move_speed, move_freq, move_route_mode, behavior, route_opts
            route_len = r.read_u4()
            for _ in range(route_len):
                _rtype = r.read_u1()
                u4_len = r.read_u1()
                r.pos += u4_len * 4
                u1_len = r.read_u1()
                r.pos += u1_len
            route_bytes = r.data[route_start : r.pos]

        return cls(param_count, cmd_type, param_data, branch_depth, strings, raw_strings, route_bytes)

    def write(self) -> bytes:
        if self.param_count == 0:
            return b"\x00"
        buf = bytearray()
        buf.append(self.param_count)
        buf.extend(struct.pack("<I", self.cmd_type))
        buf.extend(self.param_data)
        buf.append(self.branch_depth)
        buf.append(len(self.strings))
        for s, raw in zip(self.strings, self.raw_strings):
            buf.extend(_encode_t_str(s, raw))
        if self.route_bytes:
            buf.append(1)
            buf.extend(self.route_bytes)
        else:
            buf.append(0)
        return bytes(buf)


def extract_mps_file(mps_bytes: bytes, translations: dict[str, str] | None = None) -> tuple[list[str], bytes | None]:
    """Parse a Wolf RPG .mps map file, collecting strings and optionally patching with translations."""
    r = BinaryReader(mps_bytes)
    collected: list[str] = []
    changed = False

    # Header check: [0*10, 'WOLFM', 0]
    magic = r.read_bytes(16)
    if b"WOLFM" not in magic:
        return [], None

    out = bytearray(magic)
    version_header = r.read_u1()
    out.append(version_header)
    magic2 = r.read_bytes(3)
    out.extend(magic2)
    unknown1 = r.read_u4()
    out.extend(struct.pack("<I", unknown1))
    version = r.read_u1()
    out.append(version)

    # Map Title
    map_title, raw_title = r.read_t_str()
    if _is_translatable(map_title):
        collected.append(map_title)
        if translations and map_title in translations and translations[map_title]:
            map_title = translations[map_title]
            changed = True
    out.extend(_encode_t_str(map_title, raw_title))

    tileset = r.read_u4()
    width = r.read_u4()
    height = r.read_u4()
    event_count = r.read_u4()
    out.extend(struct.pack("<IIII", tileset, width, height, event_count))

    # mapdata_block
    first_pixel = r.read_u4()
    out.extend(struct.pack("<I", first_pixel))
    if first_pixel != 0xFFFFFFFF:
        skip_len = width * height * 12 - 4
        out.extend(r.read_bytes(skip_len))

    # events
    for _ in range(event_count):
        ev_header = r.read_u1()
        header2 = r.read_u4()
        ev_id = r.read_u4()
        ev_title, raw_ev_title = r.read_t_str()
        if _is_translatable(ev_title):
            collected.append(ev_title)
            if translations and ev_title in translations and translations[ev_title]:
                ev_title = translations[ev_title]
                changed = True
        map_x = r.read_u4()
        map_y = r.read_u4()
        page_count = r.read_u4()
        separator = r.read_u4()

        out.append(ev_header)
        out.extend(struct.pack("<II", header2, ev_id))
        out.extend(_encode_t_str(ev_title, raw_ev_title))
        out.extend(struct.pack("<IIII", map_x, map_y, page_count, separator))

        for _ in range(page_count):
            p_header = r.read_u1()
            p_chipid = r.read_u4()
            p_graphic, raw_pg = r.read_t_str()
            p_meta = r.read_bytes(4)
            p_trig_cond = r.read_u1()
            p_trig_sw = r.read_bytes(2)  # 4 * 4 bits = 16 bits = 2 bytes
            p_trig_vars = r.read_bytes(16)
            p_trig_vals = r.read_bytes(16)

            # route_info
            r_start = r.pos
            r.pos += 6
            r_len = r.read_u4()
            for _ in range(r_len):
                _ = r.read_u1()
                u4_len = r.read_u1()
                r.pos += u4_len * 4
                u1_len = r.read_u1()
                r.pos += u1_len
            p_route = r.data[r_start : r.pos]

            out.append(p_header)
            out.extend(struct.pack("<I", p_chipid))
            out.extend(_encode_t_str(p_graphic, raw_pg))
            out.extend(p_meta)
            out.append(p_trig_cond)
            out.extend(p_trig_sw)
            out.extend(p_trig_vars)
            out.extend(p_trig_vals)
            out.extend(p_route)

            cmd_count = r.read_u4()
            out.extend(struct.pack("<I", cmd_count))

            for _ in range(cmd_count):
                cmd = WolfEventCommand.read(r)
                for idx, s in enumerate(cmd.strings):
                    if _is_translatable(s):
                        collected.append(s)
                        if translations and s in translations and translations[s]:
                            cmd.strings[idx] = translations[s]
                            changed = True
                out.extend(cmd.write())

            p_end = r.read_bytes(8)  # unknown3(4) + shadow(1) + range_x(1) + range_y(1) + footer(1)
            out.extend(p_end)

        ev_footer = r.read_u1()
        out.append(ev_footer)

    map_footer = r.read_u1()
    out.append(map_footer)

    return collected, (bytes(out) if changed else None)


def extract_common_events_file(dat_bytes: bytes, translations: dict[str, str] | None = None) -> tuple[list[str], bytes | None]:
    """Parse CommonEvent.dat, collecting strings and optionally patching with translations."""
    r = BinaryReader(dat_bytes)
    collected: list[str] = []
    changed = False

    magic = r.read_bytes(6)  # [0, 'W', 0, 0, 'O', 'L']
    version_header = r.read_u1()
    magic2 = r.read_bytes(3)  # ['F', 'C', 0]
    version = r.read_u1()
    count = r.read_u4()

    out = bytearray(magic)
    out.append(version_header)
    out.extend(magic2)
    out.append(version)
    out.extend(struct.pack("<I", count))

    for _ in range(count):
        c_header = r.read_u1()
        c_id = r.read_u4()
        c_cond = r.read_bytes(1)  # operator(4b) + run_condition(4b)
        c_var = r.read_u4()
        c_val = r.read_u4()
        c_arg_num_cnt = r.read_u1()
        c_arg_str_cnt = r.read_u1()

        out.append(c_header)
        out.extend(struct.pack("<I", c_id))
        out.extend(c_cond)
        out.extend(struct.pack("<II", c_var, c_val))
        out.append(c_arg_num_cnt)
        out.append(c_arg_str_cnt)

        c_title, raw_title = r.read_t_str()
        out.extend(_encode_t_str(c_title, raw_title))

        lines_count = r.read_u4()
        out.extend(struct.pack("<I", lines_count))

        for _ in range(lines_count):
            cmd = WolfEventCommand.read(r)
            for idx, s in enumerate(cmd.strings):
                if _is_translatable(s):
                    collected.append(s)
                    if translations and s in translations and translations[s]:
                        cmd.strings[idx] = translations[s]
                        changed = True
            out.extend(cmd.write())

        unknown4 = r.read_bytes(5)
        memo, raw_memo = r.read_t_str()
        sep1 = r.read_bytes(1)

        out.extend(unknown4)
        out.extend(_encode_t_str(memo, raw_memo))
        out.extend(sep1)

        # argument_names
        arg_names_len = r.read_u4()
        out.extend(struct.pack("<I", arg_names_len))
        for _ in range(arg_names_len):
            aname, raw_aname = r.read_t_str()
            out.extend(_encode_t_str(aname, raw_aname))

        # argument_special_spec
        mode_pagecount = r.read_u4()
        out.extend(struct.pack("<I", mode_pagecount))
        modes = r.read_bytes(mode_pagecount)
        out.extend(modes)

        opt_str_pagecount = r.read_u4()
        out.extend(struct.pack("<I", opt_str_pagecount))
        for _ in range(opt_str_pagecount):
            sub_len = r.read_u4()
            out.extend(struct.pack("<I", sub_len))
            for _ in range(sub_len):
                opt_str, raw_opt_str = r.read_t_str()
                if _is_translatable(opt_str):
                    collected.append(opt_str)
                    if translations and opt_str in translations and translations[opt_str]:
                        opt_str = translations[opt_str]
                        changed = True
                out.extend(_encode_t_str(opt_str, raw_opt_str))

        opt_val_pagecount = r.read_u4()
        out.extend(struct.pack("<I", opt_val_pagecount))
        for _ in range(opt_val_pagecount):
            sub_len = r.read_u4()
            out.extend(struct.pack("<I", sub_len))
            out.extend(r.read_bytes(sub_len * 4))

        arg_num_def_len = r.read_s4()
        out.extend(struct.pack("<i", arg_num_def_len))
        if arg_num_def_len > 0:
            out.extend(r.read_bytes(arg_num_def_len * 4))

        sep2 = r.read_bytes(1)
        color = r.read_u4()
        out.extend(sep2)
        out.extend(struct.pack("<I", color))

        for _ in range(100):
            cself_name, raw_cself = r.read_t_str()
            out.extend(_encode_t_str(cself_name, raw_cself))

        sep3 = r.read_bytes(1)
        unknown5 = r.read_bytes(5)
        sep4 = r.read_bytes(1)
        ret_name, raw_ret_name = r.read_t_str()
        ret_val_id = r.read_u4()
        sep5 = r.read_bytes(1)

        out.extend(sep3)
        out.extend(unknown5)
        out.extend(sep4)
        out.extend(_encode_t_str(ret_name, raw_ret_name))
        out.extend(struct.pack("<I", ret_val_id))
        out.extend(sep5)

    footer = r.read_u1()
    out.append(footer)

    return collected, (bytes(out) if changed else None)


def extract_database_file(dat_bytes: bytes, translations: dict[str, str] | None = None) -> tuple[list[str], bytes | None]:
    """Parse DataBase.dat / SysDataBase.dat, collecting strings and optionally patching with translations."""
    r = BinaryReader(dat_bytes)
    collected: list[str] = []
    changed = False

    magic = r.read_bytes(6)  # [0, 'W', 0, 0, 'O', 'L']
    version_header = r.read_u1()
    magic2 = r.read_bytes(3)  # ['F', 'M', 0]
    version = r.read_u1()
    type_count = r.read_u4()

    out = bytearray(magic)
    out.append(version_header)
    out.extend(magic2)
    out.append(version)
    out.extend(struct.pack("<I", type_count))

    for _ in range(type_count):
        sub_hdr = r.read_bytes(4)  # 0xFE, 0xFF, 0xFF, 0xFF
        data_id_method = r.read_u4()
        prop_count = r.read_u4()

        out.extend(sub_hdr)
        out.extend(struct.pack("<II", data_id_method, prop_count))

        prop_pos = []
        for _ in range(prop_count):
            raw_pos = r.read_u4()
            prop_pos.append(raw_pos)
            out.extend(struct.pack("<I", raw_pos))

        block1_count = 0
        if prop_count > 0:
            block1_count = sum(1 for p in prop_pos if (p // 1000) == 1)
        block2_count = prop_count - block1_count

        rec_count = r.read_u4()
        out.extend(struct.pack("<I", rec_count))

        for _ in range(rec_count):
            # number_block
            out.extend(r.read_bytes(block1_count * 4))
            # string_block
            for _ in range(block2_count):
                s, raw_s = r.read_t_str()
                if _is_translatable(s):
                    collected.append(s)
                    if translations and s in translations and translations[s]:
                        s = translations[s]
                        changed = True
                out.extend(_encode_t_str(s, raw_s))

    footer = r.read_u1()
    out.append(footer)

    return collected, (bytes(out) if changed else None)


def extract_game_dat_file(dat_bytes: bytes, translations: dict[str, str] | None = None) -> tuple[list[str], bytes | None]:
    """Parse Game.dat to extract titles and subtitles."""
    r = BinaryReader(dat_bytes)
    collected: list[str] = []
    changed = False

    magic = r.read_bytes(9)  # [0, 'W', 0, 0, 'O', 'L', 0, 'F', 'M']
    version_header = r.read_u1()
    u8_len = r.read_u4()
    u8_data = r.read_bytes(u8_len)

    out = bytearray(magic)
    out.append(version_header)
    out.extend(struct.pack("<I", u8_len))
    out.extend(u8_data)

    str_settings_len_pos = len(out)
    str_settings_len = r.read_u4()
    out.extend(struct.pack("<I", str_settings_len))

    # Read strings (title, serial, key, fonts, hero_graphic, subtitle...)
    str_start = r.pos
    str_out = bytearray()
    str_count = 13 if version_header == 0x55 else 9
    for idx in range(str_count):
        if r.remaining() <= 5:
            break
        s, raw_s = r.read_t_str()
        if idx in (0, 8, 11, 12) and _is_translatable(s):  # title, subtitle, pro_titles
            collected.append(s)
            if translations and s in translations and translations[s]:
                s = translations[s]
                changed = True
        str_out.extend(_encode_t_str(s, raw_s))

    # update str_settings_len if string sizes changed
    struct.pack_into("<I", out, str_settings_len_pos, len(str_out))
    out.extend(str_out)

    # Remaining tail: filesize + unknown + u16_settings + static_randoms + footer
    filesize = r.read_u4()
    rem = r.read_bytes(r.remaining())
    new_filesize = len(out) + 4 + len(rem) - 1
    out.extend(struct.pack("<I", new_filesize))
    out.extend(rem)

    return collected, (bytes(out) if changed else None)


def extract_text_scenario_file(fp: Path) -> list[str]:
    """Extract translatable lines from a Wolf RPG script text or CSV file."""
    collected: list[str] = []
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            content = fp.read_text(encoding=enc)
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith(("/", "//", "#", "@")):
                    continue
                if _is_translatable(line):
                    collected.append(line)
            return collected
        except UnicodeDecodeError:
            continue
    return collected


def patch_text_scenario_file(fp: Path, translations: dict[str, str]) -> bool:
    """Patch a Wolf RPG script text or CSV file with translations, saving as utf-8-sig."""
    orig_content: str | None = None
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            orig_content = fp.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if orig_content is None:
        return False

    lines = orig_content.splitlines(keepends=True)
    new_lines: list[str] = []
    changed = False

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith(("/", "//", "#", "@")):
            if stripped in translations and translations[stripped]:
                tr = translations[stripped]
                l_ws = line[: len(line) - len(line.lstrip())]
                t_nl = line[len(line.rstrip("\r\n")) :]
                new_lines.append(f"{l_ws}{tr}{t_nl}")
                changed = True
                continue
        new_lines.append(line)

    if changed:
        bak = fp.with_name(f"{fp.name}.mtoollite.bak")
        if not bak.exists():
            shutil.copy2(fp, bak)
        # Always write as utf-8-sig so Wolf RPG engine recognizes Chinese text without mojibake
        fp.write_text("".join(new_lines), encoding="utf-8-sig")
        return True
    return False


def extract_and_patch_binary_fallback(
    raw: bytes,
    translations: dict[str, str] | None = None,
) -> tuple[list[str], bytes | None]:
    """Scan and patch length-prefixed C-strings in Wolf RPG .mps/.dat/.project files."""
    collected: list[str] = []
    pos = 0
    n = len(raw)
    out = bytearray()
    last = 0
    changed = False

    while pos <= n - 4:
        length = int.from_bytes(raw[pos : pos + 4], "little")
        if 2 <= length < 4000 and pos + 4 + length <= n:
            chunk = raw[pos + 4 : pos + 4 + length]
            # Valid C-string ends with \0 and has no internal nulls
            if chunk.endswith(b"\x00") and b"\x00" not in chunk[:-1]:
                handled = False
                for enc in ("utf-8", "cp932"):
                    try:
                        s = chunk[:-1].decode(enc)
                        if _is_translatable(s) and (_has_cjk_or_kana(s) or (translations and s in translations)):
                            collected.append(s)
                            if translations and s in translations and translations[s]:
                                new_s = translations[s]
                                try:
                                    enc_bytes = new_s.encode(enc)
                                except UnicodeEncodeError:
                                    enc_bytes = new_s.encode("utf-8")
                                enc_bytes += b"\x00"

                                out.extend(raw[last:pos])
                                out.extend(struct.pack("<I", len(enc_bytes)))
                                out.extend(enc_bytes)
                                pos += 4 + length
                                last = pos
                                changed = True
                                handled = True
                                break
                            else:
                                pos += 4 + length
                                handled = True
                                break
                    except UnicodeDecodeError:
                        pass
                if handled:
                    continue
        pos += 1

    if changed:
        out.extend(raw[last:])
        return collected, bytes(out)
    return collected, None


def _find_wolf_data_dir(info: GameInfo) -> Path:
    candidates = [
        info.root_dir / "Data",
        info.root_dir / "data",
        info.root_dir,
    ]
    for c in candidates:
        if (c / "BasicData").is_dir() or (c / "MapData").is_dir() or (c / "Evtext").is_dir():
            return c
    return info.root_dir / "Data"


def extract_wolf_texts(target: str | Path | GameInfo) -> list[str]:
    """Extract unique translatable strings from all Wolf RPG Editor scenario texts, projects, maps, and dat files."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    data_dir = _find_wolf_data_dir(info)
    collected: list[str] = []

    # 1. Scenario text and CSV files (*.txt, *.csv under Data/)
    for txt in sorted(data_dir.rglob("*.txt")):
        if txt.name.endswith(".mtoollite.bak"):
            continue
        try:
            collected.extend(extract_text_scenario_file(txt))
        except Exception:
            pass

    for csv in sorted(data_dir.rglob("*.csv")):
        if csv.name.endswith(".mtoollite.bak"):
            continue
        try:
            collected.extend(extract_text_scenario_file(csv))
        except Exception:
            pass

    # 2. Database projects (*.project under Data/BasicData or Data/)
    for proj in sorted(data_dir.rglob("*.project")):
        if proj.name.endswith(".mtoollite.bak"):
            continue
        try:
            texts, _ = extract_and_patch_binary_fallback(proj.read_bytes())
            collected.extend(texts)
        except Exception:
            pass

    # 3. MapData/*.mps
    map_dir = data_dir / "MapData" if (data_dir / "MapData").is_dir() else data_dir
    for mps in sorted(map_dir.glob("*.mps")):
        if mps.name.endswith(".mtoollite.bak"):
            continue
        raw = mps.read_bytes()
        texts: list[str] = []
        try:
            texts, _ = extract_mps_file(raw)
        except Exception:
            texts = []
        if not texts:
            try:
                texts, _ = extract_and_patch_binary_fallback(raw)
            except Exception:
                texts = []
        collected.extend(texts)

    # 4. BasicData/*.dat
    basic_dir = data_dir / "BasicData" if (data_dir / "BasicData").is_dir() else data_dir
    ce_dat = basic_dir / "CommonEvent.dat"
    if ce_dat.is_file() and not ce_dat.name.endswith(".mtoollite.bak"):
        raw = ce_dat.read_bytes()
        texts = []
        try:
            texts, _ = extract_common_events_file(raw)
        except Exception:
            texts = []
        if not texts:
            try:
                texts, _ = extract_and_patch_binary_fallback(raw)
            except Exception:
                texts = []
        collected.extend(texts)

    for db_name in ("DataBase.dat", "SysDataBase.dat", "SysDatabase.dat", "CDataBase.dat", "TileSetData.dat"):
        db_file = basic_dir / db_name
        if db_file.is_file() and not db_file.name.endswith(".mtoollite.bak"):
            raw = db_file.read_bytes()
            texts = []
            try:
                texts, _ = extract_database_file(raw)
            except Exception:
                texts = []
            if not texts:
                try:
                    texts, _ = extract_and_patch_binary_fallback(raw)
                except Exception:
                    texts = []
            collected.extend(texts)

    game_dat = data_dir / "Game.dat"
    if game_dat.is_file() and not game_dat.name.endswith(".mtoollite.bak"):
        raw = game_dat.read_bytes()
        texts = []
        try:
            texts, _ = extract_game_dat_file(raw)
        except Exception:
            texts = []
        if not texts:
            try:
                texts, _ = extract_and_patch_binary_fallback(raw)
            except Exception:
                texts = []
        collected.extend(texts)

    return list(dict.fromkeys(collected))


def mount_wolf(target: str | Path | GameInfo, dict_path: str | Path) -> list[Path]:
    """Patch Wolf RPG scenario texts, projects, .mps and .dat files with translations, backing up originals to *.mtoollite.bak."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    raw_tr = load_json_dict(dict_path)
    translations = {k: ("" if v == "__FILTERED__" else v) for k, v in raw_tr.items()}
    data_dir = _find_wolf_data_dir(info)
    written: list[Path] = []

    def _patch_file(fp: Path, patcher_func) -> None:
        try:
            raw = fp.read_bytes()
            _, patched = patcher_func(raw, translations)
            if patched is not None:
                bak = fp.with_name(f"{fp.name}.mtoollite.bak")
                if not bak.exists():
                    shutil.copy2(fp, bak)
                fp.write_bytes(patched)
                written.append(fp)
        except Exception:
            # Fallback to robust binary patcher
            try:
                raw = fp.read_bytes()
                _, patched = extract_and_patch_binary_fallback(raw, translations)
                if patched is not None:
                    bak = fp.with_name(f"{fp.name}.mtoollite.bak")
                    if not bak.exists():
                        shutil.copy2(fp, bak)
                    fp.write_bytes(patched)
                    written.append(fp)
            except Exception:
                pass

    # 1. Scenario text files
    for txt in sorted(data_dir.rglob("*.txt")):
        if txt.name.endswith(".mtoollite.bak"):
            continue
        try:
            if patch_text_scenario_file(txt, translations):
                written.append(txt)
        except Exception:
            pass

    for csv in sorted(data_dir.rglob("*.csv")):
        if csv.name.endswith(".mtoollite.bak"):
            continue
        try:
            if patch_text_scenario_file(csv, translations):
                written.append(csv)
        except Exception:
            pass

    # 2. Database projects
    for proj in sorted(data_dir.rglob("*.project")):
        if proj.name.endswith(".mtoollite.bak"):
            continue
        try:
            raw = proj.read_bytes()
            _, patched = extract_and_patch_binary_fallback(raw, translations)
            if patched is not None:
                bak = proj.with_name(f"{proj.name}.mtoollite.bak")
                if not bak.exists():
                    shutil.copy2(proj, bak)
                proj.write_bytes(patched)
                written.append(proj)
        except Exception:
            pass

    # 3. Maps
    map_dir = data_dir / "MapData" if (data_dir / "MapData").is_dir() else data_dir
    for mps in sorted(map_dir.glob("*.mps")):
        if not mps.name.endswith(".mtoollite.bak"):
            _patch_file(mps, extract_mps_file)

    # 4. CommonEvents & Databases
    basic_dir = data_dir / "BasicData" if (data_dir / "BasicData").is_dir() else data_dir
    ce_dat = basic_dir / "CommonEvent.dat"
    if ce_dat.is_file() and not ce_dat.name.endswith(".mtoollite.bak"):
        _patch_file(ce_dat, extract_common_events_file)

    for db_name in ("DataBase.dat", "SysDataBase.dat", "SysDatabase.dat", "CDataBase.dat", "TileSetData.dat"):
        db_file = basic_dir / db_name
        if db_file.is_file() and not db_file.name.endswith(".mtoollite.bak"):
            _patch_file(db_file, extract_database_file)

    game_dat = data_dir / "Game.dat"
    if game_dat.is_file() and not game_dat.name.endswith(".mtoollite.bak"):
        _patch_file(game_dat, extract_game_dat_file)

    return written


def unmount_wolf(target: str | Path | GameInfo) -> int:
    """Restore backed-up Wolf RPG data files."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    data_dir = _find_wolf_data_dir(info)
    restored = 0
    for bak in sorted(data_dir.rglob("*.mtoollite.bak")):
        orig = bak.with_name(bak.name[:-len(".mtoollite.bak")])
        shutil.move(str(bak), str(orig))
        restored += 1
    return restored
