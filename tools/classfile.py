"""Minimal reader for compiled Java .class files. Standard library only.

It reads just enough to answer two questions: which fields does a class declare, with what
type and which runtime-visible annotations, and which true/false value does the constructor
give each boolean field. configure.py uses that to find SkyHanni's @FeatureToggle switches
inside the mod jar (the same list SkyHanni's own /shdefaultoptions works from) and to put
them back to SkyHanni's defaults.

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
    default: bool | None = None  # for booleans: the constant the constructor stores, if any


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
        elif tag in (9, 12):  # Fieldref (class, name-and-type), NameAndType (name, descriptor)
            pool[i] = ("fieldref" if tag == 9 else "nat", r.u2(), r.u2())
        elif tag in (10, 11, 17, 18):  # method refs, (Invoke)Dynamic
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

    # Constructors: `aload_0; iconst_0|iconst_1; putfield this.<boolean>` is how both javac and
    # kotlinc store a boolean field's initial value (`var enabled = true`). A boxed switch
    # (`Property.of(true)`) puts two static calls between the constant and the putfield.
    by_name = {f.name: f for f in fields}

    def store_target(code: bytes, at: int, wanted: str):
        if at + 2 >= len(code) or code[at] != 0xB5:  # putfield
            return None
        ref = pool[(code[at + 1] << 8) | code[at + 2]]
        if not (isinstance(ref, tuple) and ref[0] == "fieldref"):
            return None
        owner, nat = pool[pool[ref[1]][1]], pool[ref[2]]
        target = by_name.get(pool[nat[1]])
        if owner != class_name or not target or target.default is not None:
            return None
        return target if pool[nat[2]] == wanted or (wanted == "boxed" and pool[nat[2]].endswith("/Property;")) else None
    for _ in range(r.u2()):
        r.u2()  # access flags
        method_name = pool[r.u2()]
        r.u2()  # descriptor
        for _ in range(r.u2()):
            attr_name, length = pool[r.u2()], r.u4()
            end = r.pos + length
            if attr_name == "Code" and method_name == "<init>":
                r.u2(), r.u2()  # max stack, max locals
                code = r.take(r.u4())
                for j in range(len(code) - 4):
                    if code[j] != 0x2A or code[j + 1] not in (0x03, 0x04):  # aload_0; iconst_0/1
                        continue
                    target = store_target(code, j + 2, "Z")
                    if target is None and code[j + 2] == 0xB8 and code[j + 5 : j + 6] == b"\xb8":
                        k = j + 8  # after Boolean.valueOf + Property.of; kotlinc may add a null check:
                        if code[k : k + 2] == b"\x59\x12" and code[k + 3 : k + 4] == b"\xb8":  # dup; ldc; invokestatic
                            k += 6
                        elif code[k : k + 2] == b"\x59\x13" and code[k + 4 : k + 5] == b"\xb8":  # dup; ldc_w; invokestatic
                            k += 7
                        target = store_target(code, k, "boxed")
                    if target is not None:
                        target.default = code[j + 1] == 0x04
            r.pos = end
    return class_name, fields
