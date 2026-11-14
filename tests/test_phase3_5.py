"""Unit tests for Phase 3 (RGSS / 2000-2003) and Phase 5 (Modifier/QoL)."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from rpgm_tool.extractor_2k3 import extract_2k3_texts
from rpgm_tool.extractor_rgss import extract_rgss_texts, mount_rgss, unmount_rgss
from rpgm_tool.injector_mvmz import mount_mvmz, unmount_mvmz
from rpgm_tool.modifier_mvmz import CHEAT_PLUGIN_NAME, mount_cheat_mvmz, unmount_cheat_mvmz
from rpgm_tool.rgss_archive import read_rgss_archive
from rpgm_tool.ruby_marshal import RubyObject, RubyString, RubyUserData, dumps, loads


def _ber(n: int) -> bytes:
    if n == 0:
        return b"\x00"
    parts = []
    while n > 0:
        parts.append(n & 0x7F)
        n >>= 7
    parts.reverse()
    for i in range(len(parts) - 1):
        parts[i] |= 0x80
    return bytes(parts)


class TestPhase3And5(unittest.TestCase):
    def test_ruby_marshal_roundtrip_and_rgss_pipeline(self) -> None:
        actor = RubyObject(
            class_name="RPG::Actor",
            ivars={
                "@id": 1,
                "@name": RubyString("ハロルド", ivars={"E": True}),
                "@nickname": RubyString("勇者", ivars={"E": True}),
                "@description": RubyString("王国の騎士", ivars={"E": True}),
                "@table": RubyUserData("Table", b"\x01\x00\x00\x00\x02\x00"),
            },
        )
        raw_actors = dumps([None, actor])
        decoded = loads(raw_actors)
        self.assertEqual(decoded[1].ivars["@name"].text, "ハロルド")
        self.assertEqual(decoded[1].ivars["@table"].data, b"\x01\x00\x00\x00\x02\x00")

        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "vxa_game"
            data_dir = game / "Data"
            data_dir.mkdir(parents=True)
            (game / "Game.ini").write_text("[Game]\nLibrary=System\\RGSS301.dll\n", encoding="utf-8")
            actors_fp = data_dir / "Actors.rvdata2"
            actors_fp.write_bytes(raw_actors)

            texts = extract_rgss_texts(game)
            self.assertEqual(texts, ["ハロルド", "勇者", "王国の騎士"])

            dict_fp = game / "ManualTransFile.json"
            dict_fp.write_text('{"ハロルド": "哈罗德", "勇者": "勇者大人"}', encoding="utf-8")

            written = mount_rgss(game, dict_fp)
            self.assertEqual(written, [actors_fp])

            patched = loads(actors_fp.read_bytes())
            self.assertEqual(patched[1].ivars["@name"].text, "哈罗德")
            self.assertEqual(patched[1].ivars["@nickname"].text, "勇者大人")

            restored_count = unmount_rgss(game)
            self.assertEqual(restored_count, 1)
            restored = loads(actors_fp.read_bytes())
            self.assertEqual(restored[1].ivars["@name"].text, "ハロルド")

    def test_rgss3a_archive_unpack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arch = Path(tmp) / "Game.rgss3a"
            raw_key = 0x12345678
            base_key = (raw_key * 9 + 3) & 0xFFFFFFFF
            file_key = 0xABCDEF01
            payload = b"hello rgss3a!!"

            # Encrypt payload
            enc_payload = bytearray(payload)
            k = file_key
            for i in range(0, len(enc_payload) - (len(enc_payload) % 4), 4):
                val = struct.unpack_from("<I", enc_payload, i)[0] ^ k
                struct.pack_into("<I", enc_payload, i, val)
                k = (k * 7 + 3) & 0xFFFFFFFF
            rem = len(enc_payload) % 4
            if rem:
                kb = struct.pack("<I", k)
                for j in range(rem):
                    enc_payload[len(enc_payload) - rem + j] ^= kb[j]

            name_bytes = b"Data/Test.rvdata2"
            enc_name = bytes(b ^ ((base_key >> ((i % 4) * 8)) & 0xFF) for i, b in enumerate(name_bytes))

            header = b"RGSSAD\x00\x03" + struct.pack("<I", raw_key)
            # offset will be len(header) + 16 + len(enc_name) + 16
            offset = len(header) + 16 + len(enc_name) + 16
            entry = (
                struct.pack("<IIII", offset ^ base_key, len(payload) ^ base_key, file_key ^ base_key, len(name_bytes) ^ base_key)
                + enc_name
                + struct.pack("<IIII", 0 ^ base_key, 0, 0, 0)
            )
            arch.write_bytes(header + entry + bytes(enc_payload))

            files = read_rgss_archive(arch)
            self.assertEqual(files["Data/Test.rvdata2"], payload)

    def test_2k3_lmu_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "rm2k3"
            game.mkdir()
            (game / "RPG_RT.exe").write_text("", encoding="utf-8")

            # Build minimal LcfMapUnit with chunk 81 -> event 1 -> chunk 5 (pages) -> page 1 -> chunk 52 (cmds)
            msg = "ようこそ！".encode("cp932")
            cmd_bytes = _ber(10110) + _ber(0) + _ber(len(msg)) + msg + _ber(0)
            page_bytes = _ber(52) + _ber(len(cmd_bytes)) + cmd_bytes + _ber(0)
            pages_chunk = _ber(1) + _ber(1) + page_bytes
            ev_bytes = _ber(5) + _ber(len(pages_chunk)) + pages_chunk + _ber(0)
            events_chunk = _ber(1) + _ber(1) + ev_bytes
            lmu_bytes = _ber(10) + b"LcfMapUnit" + _ber(81) + _ber(len(events_chunk)) + events_chunk + _ber(0)

            (game / "Map0001.lmu").write_bytes(lmu_bytes)
            texts = extract_2k3_texts(game)
            self.assertEqual(texts, ["ようこそ！"])

    def test_cheat_mount_and_unmount_alongside_translator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "mz_game"
            (game / "js").mkdir(parents=True)
            (game / "data").mkdir(parents=True)
            (game / "js" / "rmmz_core.js").write_text("", encoding="utf-8")
            (game / "data" / "System.json").write_text("{}", encoding="utf-8")
            plugins_js = game / "js" / "plugins.js"
            orig = '// Generated\nvar $plugins =\n[{"name":"Base","status":true,"description":"","parameters":{}}];\n'
            plugins_js.write_text(orig, encoding="utf-8")

            mount_mvmz(game)
            res = mount_cheat_mvmz(game)
            self.assertTrue(res["plugin"].is_file())
            self.assertIn(CHEAT_PLUGIN_NAME, plugins_js.read_text(encoding="utf-8"))

            self.assertTrue(unmount_cheat_mvmz(game))
            self.assertFalse(res["plugin"].is_file())
            self.assertNotIn(CHEAT_PLUGIN_NAME, plugins_js.read_text(encoding="utf-8"))
            self.assertIn("MToolLite_Translator", plugins_js.read_text(encoding="utf-8"))

            self.assertTrue(unmount_mvmz(game))
            self.assertEqual(plugins_js.read_text(encoding="utf-8"), orig)


if __name__ == "__main__":
    unittest.main()
