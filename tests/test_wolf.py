"""Tests for Wolf RPG Editor extraction, patching, and unmounting."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from rpgm_tool.detector import detect_engine
from rpgm_tool.extractor_wolf import (
    extract_common_events_file,
    extract_database_file,
    extract_game_dat_file,
    extract_mps_file,
    extract_wolf_texts,
    mount_wolf,
    unmount_wolf,
)


def _encode_t_str(s: str) -> bytes:
    encoded = s.encode("utf-8") + b"\x00"
    return struct.pack("<I", len(encoded)) + encoded


class TestWolfRpgPipeline(unittest.TestCase):
    def test_mps_extraction_and_patching(self) -> None:
        # Build synthetic minimal .mps
        buf = bytearray()
        buf.extend(b"\x00" * 10 + b"WOLFM" + b"\x00")  # magic 16b
        buf.append(0)  # version_header (v2)
        buf.extend(b"\x00\x00\x00")  # magic2
        buf.extend(struct.pack("<I", 0x64))  # unknown1
        buf.append(0x65)  # version
        buf.extend(_encode_t_str("始まりの森"))  # map title
        buf.extend(struct.pack("<IIII", 1, 20, 15, 1))  # tileset, width, height, event_count
        buf.extend(struct.pack("<I", 0xFFFFFFFF))  # empty mapdata_block

        # 1 event
        buf.append(0x6F)  # ev_header
        buf.extend(struct.pack("<II", 0x3039, 1))  # header2, ev_id
        buf.extend(_encode_t_str("村人A"))  # ev_title
        buf.extend(struct.pack("<IIII", 5, 8, 1, 0))  # map_x, map_y, page_count, sep

        # 1 page
        buf.append(0x79)  # p_header
        buf.extend(struct.pack("<I", 0))  # chipid
        buf.extend(_encode_t_str("char.png"))  # graphic
        buf.extend(b"\x00" * 4)  # meta
        buf.append(0)  # trig_cond
        buf.extend(b"\x00" * 2)  # trig_sw
        buf.extend(b"\x00" * 16)  # trig_vars
        buf.extend(b"\x00" * 16)  # trig_vals

        # route (len=0)
        buf.extend(b"\x00" * 6)
        buf.extend(struct.pack("<I", 0))

        # commands: 1 message command (code 101)
        buf.extend(struct.pack("<I", 1))  # cmd_count = 1
        # WolfEventCommand: param_count=1, cmd_type=101, param_data="", branch_depth=0, string_count=1
        buf.append(1)  # param_count
        buf.extend(struct.pack("<I", 101))  # cmd_type
        buf.append(0)  # branch_depth
        buf.append(1)  # string_count
        buf.extend(_encode_t_str("こんにちは、旅人さん！"))
        buf.append(0)  # have_route = 0

        buf.extend(b"\x00" * 8)  # page end
        buf.append(0x70)  # ev_footer
        buf.append(0x66)  # map_footer

        mps_raw = bytes(buf)
        texts, _ = extract_mps_file(mps_raw)
        self.assertIn("始まりの森", texts)
        self.assertIn("村人A", texts)
        self.assertIn("こんにちは、旅人さん！", texts)

        # Patching
        tr_map = {"始まりの森": "起始之森", "こんにちは、旅人さん！": "你好，旅行者！"}
        _, patched = extract_mps_file(mps_raw, tr_map)
        self.assertIsNotNone(patched)
        assert patched is not None
        p_texts, _ = extract_mps_file(patched)
        self.assertIn("起始之森", p_texts)
        self.assertIn("你好，旅行者！", p_texts)

    def test_wolf_full_game_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_root = Path(tmp) / "wolf_game"
            data_dir = game_root / "Data"
            basic_dir = data_dir / "BasicData"
            map_dir = data_dir / "MapData"
            basic_dir.mkdir(parents=True)
            map_dir.mkdir(parents=True)
            (game_root / "Game.exe").write_text("", encoding="utf-8")

            # 1. Game.dat
            g_buf = bytearray()
            g_buf.extend(b"\x00W\x00\x00OL\x00FM")  # magic 9b
            g_buf.append(0)  # version_header (v2)
            g_buf.extend(struct.pack("<I", 4))  # u8_len
            g_buf.extend(b"\x00" * 4)  # u8_data
            str_data = _encode_t_str("Wolf冒险记") + (_encode_t_str("") * 8)
            g_buf.extend(struct.pack("<I", len(str_data)))
            g_buf.extend(str_data)
            g_buf.extend(struct.pack("<I", len(g_buf) + 10))  # filesize
            g_buf.extend(b"\x00" * 9)  # u16 and others
            g_buf.append(0xC2)  # footer
            (data_dir / "Game.dat").write_bytes(bytes(g_buf))

            # 2. Evtext script file
            evtext_dir = data_dir / "Evtext"
            evtext_dir.mkdir(parents=True)
            (evtext_dir / "intro.txt").write_text(
                "//Header\nセリス：\nひぃいっ！？\n/fin\n", encoding="cp932"
            )

            # 3. Project database file
            (basic_dir / "DataBase.project").write_bytes(
                struct.pack("<I", 1) + _encode_t_str("システム") + _encode_t_str("主人公名")
            )

            info = detect_engine(game_root)
            self.assertEqual(info.engine, "Wolf RPG")

            texts = extract_wolf_texts(game_root)
            self.assertIn("Wolf冒险记", texts)
            self.assertIn("セリス：", texts)
            self.assertIn("ひぃいっ！？", texts)
            self.assertIn("システム", texts)
            self.assertIn("主人公名", texts)

            dict_file = game_root / "ManualTransFile.json"
            dict_file.write_text(
                '{"Wolf冒险记": "Wolf冒险奇谭", "セリス：": "塞莉丝：", "ひぃいっ！？": "噫！？", "主人公名": "主角姓名"}',
                encoding="utf-8",
            )

            # Mount
            written = mount_wolf(game_root, dict_file)
            self.assertGreaterEqual(len(written), 3)
            self.assertTrue((data_dir / "Game.dat.mtoollite.bak").is_file())
            self.assertTrue((evtext_dir / "intro.txt.mtoollite.bak").is_file())
            self.assertTrue((basic_dir / "DataBase.project.mtoollite.bak").is_file())

            p_texts = extract_wolf_texts(game_root)
            self.assertIn("Wolf冒险奇谭", p_texts)
            self.assertIn("塞莉丝：", p_texts)
            self.assertIn("噫！？", p_texts)
            self.assertIn("主角姓名", p_texts)

            # Unmount
            restored = unmount_wolf(game_root)
            self.assertGreaterEqual(restored, 3)
            self.assertFalse((data_dir / "Game.dat.mtoollite.bak").exists())
            self.assertFalse((evtext_dir / "intro.txt.mtoollite.bak").exists())
            self.assertFalse((basic_dir / "DataBase.project.mtoollite.bak").exists())
            r_texts = extract_wolf_texts(game_root)
            self.assertIn("Wolf冒险记", r_texts)
            self.assertIn("セリス：", r_texts)


if __name__ == "__main__":
    unittest.main()
