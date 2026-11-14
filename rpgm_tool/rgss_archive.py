"""Pure-Python unpacker for RPG Maker XP/VX/VXAce archives (.rgssad, .rgss2a, .rgss3a)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveEntry:
    name: str
    offset: int
    size: int
    key: int


def _advance_key(key: int) -> int:
    return (key * 7 + 3) & 0xFFFFFFFF


def _decrypt_data(raw: bytes, initial_key: int) -> bytes:
    """Decrypt RGSS entry payload in 4-byte little-endian blocks."""
    out = bytearray(raw)
    key = initial_key
    length = len(out)
    idx = 0
    while idx + 4 <= length:
        val = struct.unpack_from("<I", out, idx)[0] ^ key
        struct.pack_into("<I", out, idx, val)
        key = _advance_key(key)
        idx += 4
    if idx < length:
        key_bytes = struct.pack("<I", key)
        for j in range(length - idx):
            out[idx + j] ^= key_bytes[j]
    return bytes(out)


def read_rgss_archive(archive_path: str | Path) -> dict[str, bytes]:
    """Read all files from an .rgssad, .rgss2a, or .rgss3a archive into memory."""
    p = Path(archive_path)
    data = p.read_bytes()
    if len(data) < 8 or data[:7] != b"RGSSAD\x00":
        raise ValueError(f"Not a valid RGSS archive: {p}")

    version = data[7]
    pos = 8
    files: dict[str, bytes] = {}

    if version == 1:
        key = 0xDEADCAFE
        total = len(data)
        while pos < total:
            if pos + 4 > total:
                break
            name_len = struct.unpack_from("<I", data, pos)[0] ^ key
            pos += 4
            key = _advance_key(key)

            if pos + name_len > total:
                break
            name_bytes = bytearray(data[pos : pos + name_len])
            pos += name_len
            for i in range(name_len):
                name_bytes[i] ^= key & 0xFF
                key = _advance_key(key)
            name = name_bytes.decode("utf-8", errors="replace").replace("\\", "/")

            size = struct.unpack_from("<I", data, pos)[0] ^ key
            pos += 4
            key = _advance_key(key)

            payload = _decrypt_data(data[pos : pos + size], key)
            pos += size
            files[name] = payload
        return files

    if version == 3:
        base_key = (struct.unpack_from("<I", data, pos)[0] * 9 + 3) & 0xFFFFFFFF
        pos += 4
        entries: list[ArchiveEntry] = []
        while pos + 16 <= len(data):
            offset = struct.unpack_from("<I", data, pos)[0] ^ base_key
            pos += 4
            if offset == 0:
                break
            size = struct.unpack_from("<I", data, pos)[0] ^ base_key
            pos += 4
            file_key = struct.unpack_from("<I", data, pos)[0] ^ base_key
            pos += 4
            name_len = struct.unpack_from("<I", data, pos)[0] ^ base_key
            pos += 4

            name_bytes = bytearray(data[pos : pos + name_len])
            pos += name_len
            for i in range(name_len):
                name_bytes[i] ^= (base_key >> ((i % 4) * 8)) & 0xFF
            name = name_bytes.decode("utf-8", errors="replace").replace("\\", "/")
            entries.append(ArchiveEntry(name=name, offset=offset, size=size, key=file_key))

        for entry in entries:
            raw = data[entry.offset : entry.offset + entry.size]
            files[entry.name] = _decrypt_data(raw, entry.key)
        return files

    raise ValueError(f"Unsupported RGSS archive version: {version}")
