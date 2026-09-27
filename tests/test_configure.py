"""Tests for tools/configure.py and tools/classfile.py. Standard library only, no network,
no game needed: class files and mod jars are built by hand below.

Run from the repo root:
    python -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import classfile  # noqa: E402
import configure  # noqa: E402

EXPOSE = configure.GSON_EXPOSE
TOGGLE = configure.FEATURE_TOGGLE
OPTION = "Lat/hannibal2/skyhanni/deps/moulconfig/annotations/ConfigOption;"


# ─── building .class files by hand (JVM spec, chapter 4) ──────────────────────


def build_class(name, fields):
    """fields: [(field name, descriptor, {annotation type: {element: str | bool}})]"""
    pool, index = [], {}

    def add(key, entry):
        if key not in index:
            pool.append(entry)
            index[key] = len(pool)  # constant pool indices start at 1
        return index[key]

    def utf8(s):
        b = s.encode("utf-8")
        return add(("utf8", s), b"\x01" + struct.pack(">H", len(b)) + b)

    def cls(s):
        return add(("class", s), b"\x07" + struct.pack(">H", utf8(s)))

    def integer(v):
        return add(("int", v), b"\x03" + struct.pack(">i", v))

    this_index, super_index = cls(name), cls("java/lang/Object")
    encoded_fields = []
    for fname, descriptor, annotations in fields:
        attrs = b""
        if annotations:
            body = struct.pack(">H", len(annotations))
            for type_name, elements in annotations.items():
                body += struct.pack(">HH", utf8(type_name), len(elements))
                for key, value in elements.items():
                    if isinstance(value, bool):
                        body += struct.pack(">H", utf8(key)) + b"Z" + struct.pack(">H", integer(int(value)))
                    else:
                        body += struct.pack(">H", utf8(key)) + b"s" + struct.pack(">H", utf8(value))
            attrs = struct.pack(">HI", utf8("RuntimeVisibleAnnotations"), len(body)) + body
        encoded_fields.append(
            struct.pack(">HHHH", 0x0001, utf8(fname), utf8(descriptor), 1 if annotations else 0) + attrs
        )
    return (
        b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 65)
        + struct.pack(">H", len(pool) + 1) + b"".join(pool)
        + struct.pack(">HHHH", 0x0021, this_index, super_index, 0)
        + struct.pack(">H", len(encoded_fields)) + b"".join(encoded_fields)
        + struct.pack(">HH", 0, 0)  # no methods, no class attributes
    )


PKG = "at/hannibal2/skyhanni/config/"


def fake_skyhanni_jar(path):
    """A tiny SkyHanni: root -> garden (2 toggles + 1 plain option) and fishing (1 inverted toggle)."""
    classes = {
        PKG + "SkyHanniConfig": [
            ("garden", f"L{PKG}GardenConfig;", {EXPOSE: {}}),
            ("fishing", f"L{PKG}FishingConfig;", {EXPOSE: {}}),
            ("notSaved", f"L{PKG}GardenConfig;", {}),  # no @Expose: Gson skips it, so must we
        ],
        PKG + "GardenConfig": [
            ("visitorTimer", "Z", {EXPOSE: {}, TOGGLE: {}, OPTION: {"name": "Visitor Timer", "desc": "d"}}),
            ("pests", f"L{PKG}PestConfig;", {EXPOSE: {}}),
            ("chatVolume", "I", {EXPOSE: {}}),  # an ordinary setting, not a feature switch
        ],
        PKG + "PestConfig": [("finder", "Z", {EXPOSE: {}, TOGGLE: {}})],
        PKG + "FishingConfig": [("hideLobbyFish", "Z", {EXPOSE: {}, TOGGLE: {"trueIsEnabled": False}})],
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, fields in classes.items():
            z.writestr(name + ".class", build_class(name, fields))
        z.writestr("fabric.mod.json", "{}")
    return path


def fake_odin_jar(path, module_names):
    with zipfile.ZipFile(path, "w") as z:
        for i, name in enumerate(module_names):
            # The display name sits in the class's constant pool, like in the real jar.
            z.writestr(f"{configure.ODIN_MODULE_PACKAGE}dungeon/Mod{i}.class",
                       build_class(f"Mod{i}", [(name.replace(" ", ""), "Z", {})]) + name.encode())
    return path


OPTIONS_TXT = (
    "version:4671\r\n"
    "gamma:0.5\r\n"
    "key_key.modmenu.open_menu:key.keyboard.unknown\r\n"
    "key_key.gammautils.nightVisionToggle:key.keyboard.h\r\n"
    "key_key.btrbz.toggle_bazaar_orders_hud:key.keyboard.h\r\n"
    "key_Click GUI:key.keyboard.right.shift\r\n"
    "key_key.debug.showAdvancedTooltips:key.keyboard.h\r\n"
    "key_key.jump:key.keyboard.space\r\n"
)


# ─── classfile ────────────────────────────────────────────────────────────────


class ClassFileTests(unittest.TestCase):
    def test_reads_fields_descriptors_and_annotations(self):
        data = build_class("demo/Thing", [
            ("enabled", "Z", {EXPOSE: {}, OPTION: {"name": "Enable", "desc": "Turns it on"}}),
            ("child", "Ldemo/Child;", {}),
        ])
        name, fields = classfile.parse(data)
        self.assertEqual(name, "demo/Thing")
        self.assertEqual([(f.name, f.descriptor) for f in fields], [("enabled", "Z"), ("child", "Ldemo/Child;")])
        self.assertEqual(fields[0].annotations[OPTION], {"name": "Enable", "desc": "Turns it on"})
        self.assertIn(EXPOSE, fields[0].annotations)
        self.assertEqual(fields[1].annotations, {})

    def test_reads_boolean_annotation_values(self):
        _, fields = classfile.parse(build_class("x/Y", [
            ("a", "Z", {TOGGLE: {"trueIsEnabled": False}}),
            ("b", "Z", {TOGGLE: {"trueIsEnabled": True}}),
        ]))
        self.assertIs(fields[0].annotations[TOGGLE]["trueIsEnabled"], False)
        self.assertIs(fields[1].annotations[TOGGLE]["trueIsEnabled"], True)

    def test_rejects_non_class_data(self):
        with self.assertRaises(ValueError):
            classfile.parse(b"PK\x03\x04 definitely a zip, not a class")


# ─── keybinds ─────────────────────────────────────────────────────────────────


class KeybindTests(unittest.TestCase):
    def test_moves_a_bind_and_keeps_everything_else_byte_for_byte(self):
        text, changes = configure.apply_keybinds(
            OPTIONS_TXT, {"key.btrbz.toggle_bazaar_orders_hud": "key.keyboard.end"})
        self.assertEqual(changes, ["key.btrbz.toggle_bazaar_orders_hud: key.keyboard.h -> key.keyboard.end"])
        expected = OPTIONS_TXT.replace("toggle_bazaar_orders_hud:key.keyboard.h", "toggle_bazaar_orders_hud:key.keyboard.end")
        self.assertEqual(text, expected)  # CRLF line endings and every other line preserved

    def test_binds_a_previously_unbound_action(self):
        text, _ = configure.apply_keybinds(OPTIONS_TXT, {"key.modmenu.open_menu": "key.keyboard.right.control"})
        self.assertIn("key_key.modmenu.open_menu:key.keyboard.right.control\r\n", text)

    def test_refuses_a_key_that_is_already_used(self):
        with self.assertRaises(configure.ConfigError) as caught:
            configure.apply_keybinds(OPTIONS_TXT, {"key.modmenu.open_menu": "key.keyboard.right.shift"})
        self.assertIn("already used by Click GUI", str(caught.exception))

    def test_moving_one_bind_off_a_key_frees_it_in_the_same_run(self):
        # H is shared by night vision and BtrBz; moving BtrBz away leaves night vision alone on H.
        text, changes = configure.apply_keybinds(OPTIONS_TXT, {
            "key.btrbz.toggle_bazaar_orders_hud": "key.keyboard.end",
            "key.gammautils.nightVisionToggle": "key.keyboard.h",
        })
        self.assertEqual(len(changes), 1)

    def test_debug_combos_do_not_count_as_clashes(self):
        # F3+H (advanced tooltips) is a different key press from plain H.
        configure.apply_keybinds(OPTIONS_TXT, {"key.btrbz.toggle_bazaar_orders_hud": "key.keyboard.end",
                                               "key.gammautils.nightVisionToggle": "key.keyboard.h"})

    def test_unknown_action_is_refused(self):
        with self.assertRaises(configure.ConfigError) as caught:
            configure.apply_keybinds(OPTIONS_TXT, {"key.typo.action": "key.keyboard.j"})
        self.assertIn("no keybind called key.typo.action", str(caught.exception))

    def test_running_twice_changes_nothing_the_second_time(self):
        wanted = {"key.modmenu.open_menu": "key.keyboard.right.control"}
        once, _ = configure.apply_keybinds(OPTIONS_TXT, wanted)
        twice, changes = configure.apply_keybinds(once, wanted)
        self.assertEqual((twice, changes), (once, []))


# ─── SkyHanni ─────────────────────────────────────────────────────────────────


class SkyHanniTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.jar = fake_skyhanni_jar(Path(tmp.name) / "skyhanni.jar")

    def test_finds_toggles_by_walking_exposed_fields(self):
        toggles = configure.skyhanni_feature_toggles(self.jar)
        self.assertEqual(sorted(toggles), [
            ("fishing.hideLobbyFish", False),   # inverted: "on" is false
            ("garden.pests.finder", True),
            ("garden.visitorTimer", True),
        ])  # chatVolume isn't a toggle; notSaved isn't @Expose'd

    def test_turns_on_only_the_chosen_sections(self):
        config = {"garden": {"visitorTimer": False, "pests": {"finder": False}, "chatVolume": 3},
                  "fishing": {"hideLobbyFish": True}}
        toggles = configure.skyhanni_feature_toggles(self.jar)
        changed = configure.enable_sections(config, toggles, ["garden"])
        self.assertEqual(sorted(changed), ["garden.pests.finder", "garden.visitorTimer"])
        self.assertEqual(config["garden"], {"visitorTimer": True, "pests": {"finder": True}, "chatVolume": 3})
        self.assertIs(config["fishing"]["hideLobbyFish"], True)  # untouched

    def test_inverted_toggle_is_set_to_false(self):
        config = {"garden": {}, "fishing": {"hideLobbyFish": True}}
        changed = configure.enable_sections(config, [("fishing.hideLobbyFish", False)], ["fishing"])
        self.assertEqual(changed, ["fishing.hideLobbyFish"])
        self.assertIs(config["fishing"]["hideLobbyFish"], False)

    def test_section_name_must_match_a_whole_path_segment(self):
        config = {"garden": {"a": False}, "gardenPlots": {"b": False}}
        changed = configure.enable_sections(config, [("garden.a", True), ("gardenPlots.b", True)], ["garden"])
        self.assertEqual(changed, ["garden.a"])

    def test_nested_section_like_event_diana(self):
        config = {"event": {"diana": {"guess": False}, "hoppity": {"eggs": False}}}
        toggles = [("event.diana.guess", True), ("event.hoppity.eggs", True)]
        self.assertEqual(configure.enable_sections(config, toggles, ["event.diana"]), ["event.diana.guess"])

    def test_missing_or_non_boolean_values_are_left_alone(self):
        config = {"garden": {"visitorTimer": "yes"}}
        changed = configure.enable_sections(config, [("garden.visitorTimer", True), ("garden.gone", True)], ["garden"])
        self.assertEqual(changed, [])
        self.assertEqual(config, {"garden": {"visitorTimer": "yes"}})

    def test_unknown_section_is_refused(self):
        with self.assertRaises(configure.ConfigError):
            configure.enable_sections({"garden": {}}, [], ["gardn"])

    def test_jar_without_the_config_root_is_refused(self):
        with zipfile.ZipFile(self.jar, "w") as z:
            z.writestr(PKG + "Other.class", build_class(PKG + "Other", []))
        with self.assertRaises(configure.ConfigError):
            configure.skyhanni_feature_toggles(self.jar)


# ─── Odin ─────────────────────────────────────────────────────────────────────


class OdinTests(unittest.TestCase):
    def test_empty_file_gets_the_modules_added_on(self):
        text, changes = configure.enable_odin_modules("", ["Blood Camp", "Tick Timers"])
        self.assertEqual(json.loads(text), [
            {"name": "Blood Camp", "enabled": True, "settings": {}},
            {"name": "Tick Timers", "enabled": True, "settings": {}},
        ])
        self.assertEqual(changes, ["Blood Camp: on", "Tick Timers: on"])

    def test_existing_module_is_switched_on_and_keeps_its_settings(self):
        existing = json.dumps([
            {"name": "Blood Camp", "enabled": False, "settings": {"Watcher Bar": True}},
            {"name": "Dungeon Map", "enabled": False, "settings": {}},
        ])
        text, changes = configure.enable_odin_modules(existing, ["blood camp"])  # case-insensitive, like Odin
        modules = json.loads(text)
        self.assertEqual(modules[0], {"name": "Blood Camp", "enabled": True, "settings": {"Watcher Bar": True}})
        self.assertEqual(modules[1]["enabled"], False)  # not asked for, left off
        self.assertEqual(changes, ["blood camp: on"])

    def test_already_on_means_no_change(self):
        existing = json.dumps([{"name": "Blood Camp", "enabled": True, "settings": {}}])
        self.assertEqual(configure.enable_odin_modules(existing, ["Blood Camp"])[1], [])

    def test_names_are_checked_against_the_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = fake_odin_jar(Path(tmp) / "odin.jar", ["Blood Camp", "King Relic"])
            self.assertEqual(configure.odin_names_not_in_jar(jar, ["Blood Camp", "King Relics", "King Relic"]),
                             ["King Relics"])

    def test_wrong_format_is_refused(self):
        with self.assertRaises(configure.ConfigError):
            configure.enable_odin_modules('{"modules": []}', ["Blood Camp"])


# ─── the whole run against a fake instance ────────────────────────────────────


class ConfigureInstanceTests(unittest.TestCase):
    SETTINGS = {
        "keybinds": {"key.modmenu.open_menu": "key.keyboard.right.control",
                     "key.btrbz.toggle_bazaar_orders_hud": "key.keyboard.end"},
        "skyhanni": {"enable_all_in": ["garden"]},
        "odin": {"enable": ["Blood Camp"]},
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.inst = Path(tmp.name)
        (self.inst / "mods").mkdir()
        fake_skyhanni_jar(self.inst / "mods" / "SkyHanni-9.0.0-mc26.2.jar")
        fake_odin_jar(self.inst / "mods" / "odin-0.3.4.jar", ["Blood Camp"])
        (self.inst / "options.txt").write_bytes(OPTIONS_TXT.encode())
        (self.inst / "config" / "skyhanni").mkdir(parents=True)
        (self.inst / "config" / "odin").mkdir()
        self.skyhanni = self.inst / "config" / "skyhanni" / "config.json"
        self.skyhanni.write_text(json.dumps({"garden": {"visitorTimer": False, "pests": {"finder": False}},
                                             "fishing": {"hideLobbyFish": True}}))
        (self.inst / "config" / "odin" / "odin-config.json").write_text("")
        patcher = mock.patch.object(configure, "game_running", return_value=False)
        self.game_running = patcher.start()
        self.addCleanup(patcher.stop)

    def run_configure(self, dry_run=False):
        return configure.configure(self.inst, self.SETTINGS, dry_run)

    def test_applies_everything_and_backs_up_the_originals_first(self):
        report = self.run_configure()
        self.assertEqual(len(report["Keybinds"]), 2)
        self.assertEqual(sorted(report["SkyHanni"]), ["garden.pests.finder: on", "garden.visitorTimer: on"])
        self.assertEqual(report["Odin"], ["Blood Camp: on"])

        options = (self.inst / "options.txt").read_bytes().decode()
        self.assertIn("key_key.modmenu.open_menu:key.keyboard.right.control\r\n", options)
        self.assertTrue(json.loads(self.skyhanni.read_text())["garden"]["visitorTimer"])
        self.assertTrue(json.loads((self.inst / "config/odin/odin-config.json").read_text())[0]["enabled"])

        with zipfile.ZipFile(report["_backup"][0]) as z:
            self.assertEqual(sorted(z.namelist()), ["config/odin/odin-config.json", "config/skyhanni/config.json", "options.txt"])
            self.assertEqual(z.read("options.txt").decode(), OPTIONS_TXT)  # the untouched original

    def test_second_run_changes_nothing_and_makes_no_backup(self):
        self.run_configure()
        report = self.run_configure()
        self.assertEqual({k: v for k, v in report.items()}, {"Keybinds": [], "SkyHanni": [], "Odin": []})
        self.assertEqual(len(list((self.inst / "settings-backups").iterdir())), 1)

    def test_dry_run_writes_nothing(self):
        before = {p: p.read_bytes() for p in self.inst.rglob("*") if p.is_file()}
        report = self.run_configure(dry_run=True)
        self.assertTrue(report["Keybinds"] and report["SkyHanni"] and report["Odin"])
        self.assertNotIn("_backup", report)
        after = {p: p.read_bytes() for p in self.inst.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_refuses_while_the_game_is_running(self):
        self.game_running.return_value = True
        with self.assertRaises(configure.ConfigError) as caught:
            self.run_configure()
        self.assertIn("close it first", str(caught.exception))

    def test_refuses_before_the_first_launch(self):
        (self.inst / "options.txt").unlink()
        with self.assertRaises(configure.ConfigError) as caught:
            self.run_configure()
        self.assertIn("start the game once", str(caught.exception))

    def test_a_clash_stops_the_run_before_anything_is_written(self):
        settings = dict(self.SETTINGS, keybinds={"key.modmenu.open_menu": "key.keyboard.space"})
        before = self.skyhanni.read_bytes()
        with self.assertRaises(configure.ConfigError):
            configure.configure(self.inst, settings)
        self.assertEqual(self.skyhanni.read_bytes(), before)
        self.assertFalse((self.inst / "settings-backups").exists())


# ─── the real repo settings file ──────────────────────────────────────────────


class RepoSettingsTests(unittest.TestCase):
    def test_settings_toml_parses_and_has_no_duplicate_keys(self):
        import tomllib
        settings = tomllib.loads((REPO / "settings.toml").read_text(encoding="utf-8"))
        keys = list(settings["keybinds"].values())
        self.assertEqual(len(keys), len(set(keys)), "two actions bound to the same key")
        self.assertEqual(len(settings["odin"]["enable"]), len(set(settings["odin"]["enable"])))
        self.assertTrue(settings["skyhanni"]["enable_all_in"])

    @unittest.skipUnless((configure.DEFAULT_INSTANCE / "mods").is_dir(), "no local Modrinth instance")
    def test_real_skyhanni_jar_has_the_toggles_we_rely_on(self):
        toggles = dict(configure.skyhanni_feature_toggles(configure.find_jar(configure.DEFAULT_INSTANCE, "skyhanni*.jar")))
        self.assertGreater(len(toggles), 500)
        self.assertIn("garden.visitors.timer.enabled", toggles)
        self.assertIn("event.diana.guess", toggles)

    @unittest.skipUnless((configure.DEFAULT_INSTANCE / "mods").is_dir(), "no local Modrinth instance")
    def test_every_odin_name_in_settings_exists_in_the_real_jar(self):
        import tomllib
        names = tomllib.loads((REPO / "settings.toml").read_text(encoding="utf-8"))["odin"]["enable"]
        jar = configure.find_jar(configure.DEFAULT_INSTANCE, "odin*.jar")
        self.assertEqual(configure.odin_names_not_in_jar(jar, names), [])


if __name__ == "__main__":
    unittest.main()
