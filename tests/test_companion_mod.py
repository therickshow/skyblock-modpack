"""Checks on companion-mod/ (the Mod Menu buttons mod). Standard library only.

The Java code is checked by compiling it (Gradle) against the exact mod versions the pack
ships. These tests make sure those versions really are the pack's, and, when the Modrinth
instance is on this PC, that every mod ID and library version the code relies on is really
in the pack. The final check is clicking the buttons in game.

Run from the repo root:
    python -m unittest discover -s tests -v
"""

import io
import json
import os
import re
import sys
import tomllib
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOD = REPO / "companion-mod"
JAVA_SOURCES = sorted((MOD / "src" / "main" / "java").rglob("*.java"))
INSTANCE = Path(os.environ.get("APPDATA", "~")) / "ModrinthApp" / "profiles" / "SkyBlock-QoL-1.0.0"
HAVE_INSTANCE = (INSTANCE / "mods").is_dir()


def gradle_properties() -> dict[str, str]:
    props = {}
    for line in (MOD / "gradle.properties").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
    return props


def locked_versions() -> dict[str, str]:
    lock = json.loads((REPO / "modpack.lock.json").read_text(encoding="utf-8"))
    return {m["slug"]: m["version"] for m in lock["mods"]} | {"<loader>": lock["loader"]["version"]}


def instance_mod_versions() -> dict[str, str]:
    """mod id -> version for every mod in the instance, including ones nested inside jars."""
    found = {}

    def scan(z):
        try:
            meta = json.loads(z.read("fabric.mod.json").decode("utf-8-sig"), strict=False)
        except KeyError:
            return
        found.setdefault(meta["id"], meta.get("version"))
        for nested in meta.get("jars", []):
            scan(zipfile.ZipFile(io.BytesIO(z.read(nested["file"]))))

    for jar in (INSTANCE / "mods").glob("*.jar"):
        with zipfile.ZipFile(jar) as z:
            scan(z)
    return found


def mod_ids_in_java_code() -> set[str]:
    """Every mod ID the Java code checks for with isModLoaded or lists in List.of(...)."""
    ids = set()
    for source in JAVA_SOURCES:
        text = source.read_text(encoding="utf-8")
        ids |= set(re.findall(r'isModLoaded\("([^"]+)"\)', text))
        for group in re.findall(r"List\.of\(([^)]*)\)", text):
            ids |= set(re.findall(r'"([^"]+)"', group))
    return ids


class VersionTests(unittest.TestCase):
    def test_minecraft_and_loader_match_the_pack(self):
        props = gradle_properties()
        pack = tomllib.loads((REPO / "pack.toml").read_text(encoding="utf-8"))
        self.assertEqual(props["minecraft_version"], pack["minecraft"]["version"])
        self.assertEqual(props["loader_version"], locked_versions()["<loader>"])

    def test_compiled_against_the_versions_the_pack_ships(self):
        props, locked = gradle_properties(), locked_versions()
        self.assertEqual(props["modmenu_version"], locked["modmenu"])
        self.assertEqual(props["sodium_version"], locked["sodium"])


class MetadataTests(unittest.TestCase):
    def setUp(self):
        text = (MOD / "src" / "main" / "resources" / "fabric.mod.json").read_text(encoding="utf-8")
        self.meta = json.loads(text.replace("${version}", "0.0.0"))

    def test_is_client_only_and_targets_the_packs_minecraft(self):
        mc = tomllib.loads((REPO / "pack.toml").read_text(encoding="utf-8"))["minecraft"]["version"]
        self.assertEqual(self.meta["environment"], "client")
        self.assertEqual(self.meta["depends"]["minecraft"], f"~{mc}")
        self.assertIn("modmenu", self.meta["depends"])

    def test_modmenu_entrypoint_class_exists(self):
        (entrypoint,) = self.meta["entrypoints"]["modmenu"]
        source = MOD / "src" / "main" / "java" / (entrypoint.replace(".", "/") + ".java")
        self.assertTrue(source.exists(), source)
        self.assertIn("implements ModMenuApi", source.read_text(encoding="utf-8"))

    def test_mod_id_is_valid(self):
        self.assertRegex(self.meta["id"], r"^[a-z][a-z0-9_-]{1,63}$")


class ModIdTests(unittest.TestCase):
    def test_the_code_names_the_mods_we_expect(self):
        self.assertEqual(mod_ids_in_java_code(), {
            "sodium", "sodium-extra", "reeses-sodium-options", "catharsis",
        })

    @unittest.skipUnless(HAVE_INSTANCE, "no local Modrinth instance")
    def test_every_mod_id_in_the_code_is_really_in_the_pack(self):
        # A typo here would silently mean "that button never appears".
        missing = mod_ids_in_java_code() - set(instance_mod_versions())
        self.assertEqual(missing, set())


class BuiltJarTests(unittest.TestCase):
    """Only runs after `gradlew build`."""

    @classmethod
    def setUpClass(cls):
        props = gradle_properties()
        cls.version = props["mod_version"]
        cls.jar = MOD / "build" / "libs" / f"{props['archives_base_name']}-{cls.version}.jar"
        if not cls.jar.exists():
            raise unittest.SkipTest("companion mod not built")

    def test_version_was_filled_in(self):
        with zipfile.ZipFile(self.jar) as z:
            meta = json.loads(z.read("fabric.mod.json"))
        self.assertEqual(meta["version"], self.version)

    def test_contains_every_class_compiled_for_java_25(self):
        expected = {p.stem for p in JAVA_SOURCES}
        with zipfile.ZipFile(self.jar) as z:
            classes = {n: z.read(n) for n in z.namelist() if n.endswith(".class")}
        self.assertEqual({Path(n).stem for n in classes if "$" not in n}, expected)
        for name, data in classes.items():
            major = int.from_bytes(data[6:8], "big")
            self.assertEqual(major, 69, f"{name} is class version {major}, not Java 25 (69)")


if __name__ == "__main__":
    unittest.main()
