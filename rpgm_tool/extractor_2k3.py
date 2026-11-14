"""Pure-Python LCF BER reader & text extractor for RPG Maker 2000 / 2003 (.ldb, .lmt, .lmu)."""

from __future__ import annotations

from pathlib import Path

from .detector import GameInfo, detect_engine


def _read_ber(data: bytes, pos: int) -> tuple[int, int]:
    val = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, pos
    raise EOFError("Unexpected EOF while reading LCF BER integer")


def _decode_lcf_str(raw: bytes, encoding: str = "cp932") -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(encoding, errors="replace")


def extract_lmu_event_texts(lmu_bytes: bytes, encoding: str = "cp932") -> list[str]:
    """Extract Show Message (10110/20110) and Show Choice (10140) strings from a .lmu file."""
    pos = 0
    header_len, pos = _read_ber(lmu_bytes, pos)
    pos += header_len  # skip "LcfMapUnit"

    texts: list[str] = []

    # Scan for LCF EventCommand pattern inside .lmu:
    # EventCommand: code (BER), indent (BER), str_len (BER), string_bytes, ...
    # Top-level chunk 0x51 (81) holds Map Events array.
    while pos < len(lmu_bytes):
        chunk_id, pos = _read_ber(lmu_bytes, pos)
        if chunk_id == 0:
            break
        chunk_len, pos = _read_ber(lmu_bytes, pos)
        chunk_end = pos + chunk_len
        if chunk_id == 81:
            # Events array: count (BER), then each event ID + event chunks
            ev_count, p = _read_ber(lmu_bytes, pos)
            for _ in range(ev_count):
                if p >= chunk_end:
                    break
                _ev_id, p = _read_ber(lmu_bytes, p)
                while p < chunk_end:
                    ec_id, p = _read_ber(lmu_bytes, p)
                    if ec_id == 0:
                        break
                    ec_len, p = _read_ber(lmu_bytes, p)
                    ec_end = p + ec_len
                    if ec_id == 5:  # Event pages
                        pg_count, pp = _read_ber(lmu_bytes, p)
                        for _ in range(pg_count):
                            if pp >= ec_end:
                                break
                            _pg_id, pp = _read_ber(lmu_bytes, pp)
                            while pp < ec_end:
                                pc_id, pp = _read_ber(lmu_bytes, pp)
                                if pc_id == 0:
                                    break
                                pc_len, pp = _read_ber(lmu_bytes, pp)
                                pc_end = pp + pc_len
                                if pc_id == 52:  # Event commands bytes
                                    cp = pp
                                    while cp < pc_end:
                                        cmd_code, cp = _read_ber(lmu_bytes, cp)
                                        if cmd_code == 0:
                                            # End of command list (indent, str_len, param_count)
                                            _indent, cp = _read_ber(lmu_bytes, cp)
                                            _slen, cp = _read_ber(lmu_bytes, cp)
                                            cp += _slen
                                            _pcnt, cp = _read_ber(lmu_bytes, cp)
                                            for _ in range(_pcnt):
                                                _, cp = _read_ber(lmu_bytes, cp)
                                            continue
                                        _indent, cp = _read_ber(lmu_bytes, cp)
                                        slen, cp = _read_ber(lmu_bytes, cp)
                                        sbytes = lmu_bytes[cp : cp + slen]
                                        cp += slen
                                        pcnt, cp = _read_ber(lmu_bytes, cp)
                                        for _ in range(pcnt):
                                            _, cp = _read_ber(lmu_bytes, cp)
                                        if cmd_code in (10110, 20110, 10140) and slen > 0:
                                            txt = _decode_lcf_str(sbytes, encoding=encoding)
                                            if txt.strip():
                                                texts.append(txt)
                                pp = pc_end
                    p = ec_end
        pos = chunk_end

    return texts


def extract_2k3_texts(target: str | Path | GameInfo, encoding: str = "cp932") -> list[str]:
    """Extract unique event strings from an RPG Maker 2000 / 2003 game directory."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    if info.engine != "RPG Maker 2000/2003":
        raise ValueError(f"Target is not RPG Maker 2000/2003: {info.root_dir} ({info.engine})")

    collected: list[str] = []
    for lmu in sorted(info.root_dir.glob("Map[0-9][0-9][0-9][0-9].lmu")):
        collected.extend(extract_lmu_event_texts(lmu.read_bytes(), encoding=encoding))
    return list(dict.fromkeys(collected))
