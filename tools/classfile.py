"""Minimal reader for compiled Java .class files. Standard library only.

It reads just enough to answer one question: which fields does a class declare, with what
type, and which runtime-visible annotations are on them. configure.py uses that to find
SkyHanni's @FeatureToggle switches inside the mod jar, which is the same list SkyHanni's own
"turn all on" button (/shdefaultoptions) works from.

Format reference: JVM spec, chapter 4 ("The class File Format").
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class Field:
    name: str
    descriptor: str  # e.g. "Z" for boolean, "Lcom/example/Foo;" for an object
    annotations: dict[str, dict] = field(default_factory=dict)  # annotation type -> {element: value}


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def u1(self) -> int:
        self.pos += 1
        return self.data[self.pos - 1]

    def u2(self) -> int:
        self.pos += 2
        return struct.unpack_from(">H", self.data, self.pos - 2)[0]

    def u4(self) -> int:
        self.pos += 4
        return struct.unpack_from(">I", self.data, self.pos - 4)[0]

    def take(self, n: int) -> bytes:
        self.pos += n
        return self.data[self.pos - n : self.pos]


def parse(data: bytes) -> tuple[str, list[Field]]:
    """Return (class name, fields) for one .class file."""
    r = _Reader(data)
    if r.u4() != 0xCAFEBABE:
        raise ValueError("not a Java class file")
    r.u2(), r.u2()  # minor, major version

    # Constant pool: we keep UTF-8 strings and class references, skip the rest.
    count = r.u2()
    pool: list = [None] * count
    i = 1
    while i < count:
        tag = r.u1()
        if tag == 1:  # Utf8
            pool[i] = r.take(r.u2()).decode("utf-8", "replace")
        elif tag == 7:  # Class -> name index
            pool[i] = ("class", r.u2())
        elif tag in (8, 16, 19, 20):  # String, MethodType, Module, Package
            r.u2()
        elif tag == 3:  # Integer (also how booleans in annotations are stored)
            pool[i] = struct.unpack(">i", r.take(4))[0]
        elif tag == 4:  # Float
            r.u4()
        elif tag in (5, 6):  # Long, Double take two slots
            r.u4(), r.u4()
            i += 1
        elif tag in (9, 10, 11, 12, 17, 18):  # refs, NameAndType, (Invoke)Dynamic
            r.u2(), r.u2()
        elif tag == 15:  # MethodHandle
            r.u1(), r.u2()
        else:
            raise ValueError(f"unknown constant pool tag {tag}")
        i += 1

    r.u2()  # access flags
    class_name = pool[pool[r.u2()][1]]
    r.u2()  # super class
    for _ in range(r.u2()):  # interfaces
        r.u2()

    def element_value():
        tag = chr(r.u1())
        if tag == "s":
            return pool[r.u2()]
        if tag == "Z":
            return bool(pool[r.u2()])
        if tag in "BCIS":
            return pool[r.u2()]
        if tag in "DFJ":  # double/float/long: not needed here
            r.u2()
            return None
        if tag == "e":  # enum: type, constant name
            r.u2()
            return pool[r.u2()]
        if tag == "c":
            return pool[r.u2()]
        if tag == "@":
            return annotation()[1]
        if tag == "[":
            return [element_value() for _ in range(r.u2())]
        raise ValueError(f"unknown annotation element tag {tag!r}")

    def annotation() -> tuple[str, dict]:
        type_name = pool[r.u2()]
        return type_name, {pool[r.u2()]: element_value() for _ in range(r.u2())}

    fields = []
    for _ in range(r.u2()):
        r.u2()  # access flags
        f = Field(pool[r.u2()], pool[r.u2()])
        for _ in range(r.u2()):  # attributes
            attr_name, length = pool[r.u2()], r.u4()
            end = r.pos + length
            if attr_name == "RuntimeVisibleAnnotations":
                for _ in range(r.u2()):
                    type_name, values = annotation()
                    f.annotations[type_name] = values
            r.pos = end
        fields.append(f)
    return class_name, fields
