"""Pure-Python Ruby Marshal 4.8 reader and writer for RPG Maker .rxdata/.rvdata/.rvdata2."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RubySymbol:
    name: str


@dataclass
class RubyObject:
    class_name: str
    ivars: dict[str, Any] = field(default_factory=dict)


@dataclass
class RubyUserData:
    class_name: str
    data: bytes


@dataclass
class RubyUserMarshal:
    class_name: str
    value: Any


@dataclass
class RubyString:
    """Preserves encoding metadata alongside decoded Python text."""
    text: str
    encoding: str = "utf-8"
    ivars: dict[str, Any] = field(default_factory=dict)


class _MarshalReader:
    def __init__(self, data: bytes) -> None:
        if len(data) < 2 or data[0] != 4 or data[1] != 8:
            raise ValueError("Invalid Ruby Marshal header (expected 4.8)")
        self.data = data
        self.pos = 2
        self.symbols: list[RubySymbol] = []
        self.objects: list[Any] = []

    def _read_byte(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def _read_bytes(self, n: int) -> bytes:
        chunk = self.data[self.pos : self.pos + n]
        if len(chunk) != n:
            raise EOFError("Unexpected end of Ruby Marshal stream")
        self.pos += n
        return chunk

    def _read_int(self) -> int:
        c = struct.unpack("b", self._read_bytes(1))[0]
        if c == 0:
            return 0
        if 5 <= c <= 127:
            return c - 5
        if -128 <= c <= -6:
            return c + 5
        if c > 0:
            val = 0
            for i in range(c):
                val |= self._read_byte() << (8 * i)
            return val
        size = -c
        val = -1
        for i in range(size):
            val &= ~(0xFF << (8 * i))
            val |= self._read_byte() << (8 * i)
        return val

    def _read_raw_bytes(self) -> bytes:
        length = self._read_int()
        return self._read_bytes(length)

    def _read_symbol(self) -> RubySymbol:
        raw = self._read_raw_bytes()
        sym = RubySymbol(raw.decode("utf-8", errors="replace"))
        self.symbols.append(sym)
        return sym

    def _read_sym_or_link(self) -> RubySymbol:
        tag = chr(self._read_byte())
        if tag == ":":
            return self._read_symbol()
        if tag == ";":
            idx = self._read_int()
            return self.symbols[idx]
        raise ValueError(f"Expected symbol or symlink, got {tag!r}")

    def read(self) -> Any:
        tag = chr(self._read_byte())
        if tag == "0":
            return None
        if tag == "T":
            return True
        if tag == "F":
            return False
        if tag == "i":
            return self._read_int()
        if tag == "f":
            raw = self._read_raw_bytes()
            s = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
            if s == "inf":
                return float("inf")
            if s == "-inf":
                return float("-inf")
            if s == "nan":
                return float("nan")
            return float(s)
        if tag == ":":
            return self._read_symbol()
        if tag == ";":
            return self.symbols[self._read_int()]
        if tag == "@":
            return self.objects[self._read_int()]
        if tag == '"':
            raw = self._read_raw_bytes()
            obj = RubyString(text=raw.decode("utf-8", errors="replace"), encoding="utf-8")
            self.objects.append(obj)
            return obj
        if tag == "[":
            obj: list[Any] = []
            self.objects.append(obj)
            count = self._read_int()
            for _ in range(count):
                obj.append(self.read())
            return obj
        if tag == "{":
            obj_dict: dict[Any, Any] = {}
            self.objects.append(obj_dict)
            count = self._read_int()
            for _ in range(count):
                k = self.read()
                v = self.read()
                obj_dict[k] = v
            return obj_dict
        if tag == "o":
            cls_sym = self._read_sym_or_link()
            robj = RubyObject(class_name=cls_sym.name)
            self.objects.append(robj)
            ivar_count = self._read_int()
            for _ in range(ivar_count):
                key_sym = self._read_sym_or_link()
                val = self.read()
                robj.ivars[key_sym.name] = val
            return robj
        if tag == "u":
            cls_sym = self._read_sym_or_link()
            raw = self._read_raw_bytes()
            uobj = RubyUserData(class_name=cls_sym.name, data=raw)
            self.objects.append(uobj)
            return uobj
        if tag == "U":
            cls_sym = self._read_sym_or_link()
            um_obj = RubyUserMarshal(class_name=cls_sym.name, value=None)
            self.objects.append(um_obj)
            um_obj.value = self.read()
            return um_obj
        if tag == "I":
            # Read underlying object first; if it's a RubyString, re-decode using encoding ivar
            idx = len(self.objects)
            inner = self.read()
            ivar_count = self._read_int()
            ivars: dict[str, Any] = {}
            for _ in range(ivar_count):
                key_sym = self._read_sym_or_link()
                ivars[key_sym.name] = self.read()
            if isinstance(inner, RubyString):
                enc = "utf-8"
                if "E" in ivars:
                    enc = "utf-8" if ivars["E"] else "ascii"
                elif "encoding" in ivars and isinstance(ivars["encoding"], RubyString):
                    enc = ivars["encoding"].text
                inner.encoding = enc
                inner.ivars = ivars
            return inner
        if tag in ("c", "m"):
            raw = self._read_raw_bytes()
            res = (tag, raw.decode("utf-8", errors="replace"))
            self.objects.append(res)
            return res
        raise ValueError(f"Unsupported Ruby Marshal tag: {tag!r} at pos {self.pos - 1}")


class _MarshalWriter:
    def __init__(self) -> None:
        self.buf = bytearray(b"\x04\x08")
        self.symbols: dict[str, int] = {}

    def _write_int(self, n: int) -> None:
        if n == 0:
            self.buf.append(0)
        elif 0 < n < 123:
            self.buf.append(n + 5)
        elif -124 < n < 0:
            self.buf.append((n - 5) & 0xFF)
        elif n > 0:
            parts: list[int] = []
            v = n
            while v > 0:
                parts.append(v & 0xFF)
                v >>= 8
            self.buf.append(len(parts))
            self.buf.extend(parts)
        else:
            # Negative multi-byte
            parts = []
            v = n
            while v != -1:
                parts.append(v & 0xFF)
                v >>= 8
            if not parts:
                parts = [0xFF]
            self.buf.append((-len(parts)) & 0xFF)
            self.buf.extend(parts)

    def _write_raw_bytes(self, b: bytes) -> None:
        self._write_int(len(b))
        self.buf.extend(b)

    def _write_symbol(self, name: str) -> None:
        if name in self.symbols:
            self.buf.append(ord(";"))
            self._write_int(self.symbols[name])
        else:
            idx = len(self.symbols)
            self.symbols[name] = idx
            self.buf.append(ord(":"))
            self._write_raw_bytes(name.encode("utf-8"))

    def write(self, obj: Any) -> None:
        if obj is None:
            self.buf.append(ord("0"))
        elif obj is True:
            self.buf.append(ord("T"))
        elif obj is False:
            self.buf.append(ord("F"))
        elif isinstance(obj, int):
            self.buf.append(ord("i"))
            self._write_int(obj)
        elif isinstance(obj, float):
            self.buf.append(ord("f"))
            self._write_raw_bytes(repr(obj).encode("ascii"))
        elif isinstance(obj, RubySymbol):
            self._write_symbol(obj.name)
        elif isinstance(obj, RubyString):
            if obj.ivars:
                self.buf.append(ord("I"))
                self.buf.append(ord('"'))
                self._write_raw_bytes(obj.text.encode("utf-8"))
                self._write_int(len(obj.ivars))
                for k, v in obj.ivars.items():
                    self._write_symbol(k)
                    self.write(v)
            else:
                self.buf.append(ord('"'))
                self._write_raw_bytes(obj.text.encode("utf-8"))
        elif isinstance(obj, str):
            self.buf.append(ord("I"))
            self.buf.append(ord('"'))
            self._write_raw_bytes(obj.encode("utf-8"))
            self._write_int(1)
            self._write_symbol("E")
            self.buf.append(ord("T"))
        elif isinstance(obj, list):
            self.buf.append(ord("["))
            self._write_int(len(obj))
            for item in obj:
                self.write(item)
            return
        elif isinstance(obj, dict):
            self.buf.append(ord("{"))
            self._write_int(len(obj))
            for k, v in obj.items():
                self.write(k)
                self.write(v)
        elif isinstance(obj, RubyObject):
            self.buf.append(ord("o"))
            self._write_symbol(obj.class_name)
            self._write_int(len(obj.ivars))
            for k, v in obj.ivars.items():
                self._write_symbol(k)
                self.write(v)
        elif isinstance(obj, RubyUserData):
            self.buf.append(ord("u"))
            self._write_symbol(obj.class_name)
            self._write_raw_bytes(obj.data)
        elif isinstance(obj, RubyUserMarshal):
            self.buf.append(ord("U"))
            self._write_symbol(obj.class_name)
            self.write(obj.value)
        else:
            raise TypeError(f"Unsupported type for Ruby Marshal write: {type(obj).__name__}")


def loads(data: bytes) -> Any:
    """Deserialize Ruby Marshal 4.8 bytes into Python objects."""
    return _MarshalReader(data).read()


def dumps(obj: Any) -> bytes:
    """Serialize Python/Ruby wrapper objects back into Ruby Marshal 4.8 bytes."""
    writer = _MarshalWriter()
    writer.write(obj)
    return bytes(writer.buf)
