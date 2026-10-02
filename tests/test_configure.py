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


PROPERTY = "Lio/github/notenoughupdates/moulconfig/observer/Property;"


def build_class(name, fields, init=()):
    """fields: [(field name, descriptor, {annotation type: {element: str | bool}})]
    init: constructor stores [(field name, True/False, style)], style being "plain"
    (`var x = true`), "boxed" (`Property.of(true)`), "boxed-checked" (boxed plus kotlinc's
    null check, via ldc) or "boxed-checked-wide" (same, via ldc_w), or "other-class" (a
    store into a same-named field of another class, which must be ignored)."""
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

    def nat(n, d):
        return add(("nat", n, d), b"\x0c" + struct.pack(">HH", utf8(n), utf8(d)))

    def fieldref(owner, n, d):
        return add(("field", owner, n, d), b"\x09" + struct.pack(">HH", cls(owner), nat(n, d)))

    def methodref(owner, n, d):
        return add(("method", owner, n, d), b"\x0a" + struct.pack(">HH", cls(owner), nat(n, d)))

    def string(s):
        return add(("string", s), b"\x08" + struct.pack(">H", utf8(s)))

    this_index, super_index = cls(name), cls("java/lang/Object")
    descriptors = {f[0]: f[1] for f in fields}
    code = b"\x2a" + b"\xb7" + struct.pack(">H", methodref("java/lang/Object", "<init>", "()V"))
    for fname, value, style in init:
        code += b"\x2a" + (b"\x04" if value else b"\x03")  # aload_0; iconst_1/0
        if style.startswith("boxed"):
            code += b"\xb8" + struct.pack(">H", methodref("java/lang/Boolean", "valueOf", "(Z)Ljava/lang/Boolean;"))
            code += b"\xb8" + struct.pack(">H", methodref(PROPERTY[1:-1], "of", f"(Ljava/lang/Object;){PROPERTY}"))
            check = b"\xb8" + struct.pack(">H", methodref("kotlin/jvm/internal/Intrinsics", "checkNotNullExpressionValue",
                                                          "(Ljava/lang/Object;Ljava/lang/String;)V"))
            if style == "boxed-checked":
                code += b"\x59\x12" + bytes([string("of(...)")]) + check  # dup; ldc; invokestatic
            elif style == "boxed-checked-wide":
                code += b"\x59\x13" + struct.pack(">H", string("of(...)")) + check  # dup; ldc_w; invokestatic
        owner = "some/OtherClass" if style == "other-class" else name
        code += b"\xb5" + struct.pack(">H", fieldref(owner, fname, descriptors[fname]))  # putfield
    code += b"\xb1"  # return
    code_attr = struct.pack(">HHI", 4, 1, len(code)) + code + struct.pack(">HH", 0, 0)
    method = (struct.pack(">HHHH", 0x0001, utf8("<init>"), utf8("()V"), 1)
              + struct.pack(">HI", utf8("Code"), len(code_attr)) + code_attr)
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
        + struct.pack(">H", 1) + method
        + struct.pack(">H", 0)  # no class attributes
    )


PKG = "at/hannibal2/skyhanni/config/"


def fake_skyhanni_jar(path):
    """A tiny SkyHanni: root -> garden (2 toggles + 1 plain option) and fishing (1 inverted
    toggle, 1 boxed Property toggle). Defaults: visitorTimer on, trophyChat on, the rest off."""
    classes = {
        PKG + "SkyHanniConfig": ([
            ("garden", f"L{PKG}GardenConfig;", {EXPOSE: {}}),
            ("fishing", f"L{PKG}FishingConfig;", {EXPOSE: {}}),
            ("notSaved", f"L{PKG}GardenConfig;", {}),  # no @Expose: Gson skips it, so must we
        ], []),
        PKG + "GardenConfig": ([
            ("visitorTimer", "Z", {EXPOSE: {}, TOGGLE: {}, OPTION: {"name": "Visitor Timer", "desc": "d"}}),
            ("pests", f"L{PKG}PestConfig;", {EXPOSE: {}}),
            ("chatVolume", "I", {EXPOSE: {}}),  # an ordinary setting, not a feature switch
        ], [("visitorTimer", True, "plain")]),
        PKG + "PestConfig": ([("finder", "Z", {EXPOSE: {}, TOGGLE: {}})], []),  # no initialiser: false
        PKG + "FishingConfig": ([
            ("hideLobbyFish", "Z", {EXPOSE: {}, TOGGLE: {"trueIsEnabled": False}}),
            ("trophyChat", PROPERTY, {EXPOSE: {}, TOGGLE: {}}),
        ], [("hideLobbyFish", False, "plain"), ("trophyChat", True, "boxed-checked")]),
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, (fields, init) in classes.items():
            z.writestr(name + ".class", build_class(name, fields, init))
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

    def defaults(self, fields, init):
        _, parsed = classfile.parse(build_class("x/Y", fields, init))
        return {f.name: f.default for f in parsed}

    def test_reads_plain_boolean_defaults_from_the_constructor(self):
        fields = [("on", "Z", {}), ("off", "Z", {}), ("unset", "Z", {})]
        self.assertEqual(self.defaults(fields, [("on", True, "plain"), ("off", False, "plain")]),
                         {"on": True, "off": False, "unset": None})

    def test_reads_boxed_property_defaults_with_and_without_the_null_check(self):
        fields = [(n, PROPERTY, {}) for n in ("bare", "checked", "wide")]
        init = [("bare", True, "boxed"), ("checked", True, "boxed-checked"), ("wide", False, "boxed-checked-wide")]
        self.assertEqual(self.defaults(fields, init), {"bare": True, "checked": True, "wide": False})

    def test_boxed_store_right_before_the_end_of_the_constructor(self):
        self.assertEqual(self.defaults([("last", PROPERTY, {})], [("last", True, "boxed")]), {"last": True})

    def test_store_into_another_class_is_ignored(self):
        self.assertEqual(self.defaults([("on", "Z", {})], [("on", True, "other-class")]), {"on": None})

    def test_first_store_wins_like_the_initialiser(self):
        # A later reassignment in an init block isn't the declared default; keep the first.
        self.assertEqual(self.defaults([("on", "Z", {})], [("on", True, "plain"), ("on", False, "plain")]),
                         {"on": True})


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
            ("fishing.trophyChat", True),
            ("garden.pests.finder", True),
            ("garden.visitorTimer", True),
        ])  # chatVolume isn't a toggle; notSaved isn't @Expose'd

    def test_reads_each_toggles_default(self):
        defaults = {path: default for path, _, default in configure.skyhanni_toggles_with_defaults(self.jar)}
        self.assertEqual(defaults, {"garden.visitorTimer": True, "garden.pests.finder": False,
                                    "fishing.hideLobbyFish": False, "fishing.trophyChat": True})

    def test_reset_puts_only_the_chosen_sections_back_to_default(self):
        config = {"garden": {"visitorTimer": False, "pests": {"finder": True}},
                  "fishing": {"hideLobbyFish": True, "trophyChat": False}}
        toggles = configure.skyhanni_toggles_with_defaults(self.jar)
        changed = configure.reset_sections(config, toggles, ["garden"])
        self.assertEqual(sorted(changed), ["garden.pests.finder", "garden.visitorTimer"])
        self.assertEqual(config["garden"], {"visitorTimer": True, "pests": {"finder": False}})
        self.assertEqual(config["fishing"], {"hideLobbyFish": True, "trophyChat": False})  # untouched

    def test_reset_of_an_unknown_section_is_refused(self):
        with self.assertRaises(configure.ConfigError):
            configure.reset_sections({"garden": {}}, [], ["fishng"])

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


# ─── setting values by path (SkyHanni and Skyblocker) ─────────────────────────


class SetValuesTests(unittest.TestCase):
    def config(self):
        return {"general": {"enableTips": True, "scale": 1.0, "count": 3, "name": "a"},
                "gui": {"titlePosition": {"x": 212, "centerX": False}}}

    def test_sets_nested_values_and_reports_old_and_new(self):
        config = self.config()
        changes = configure.set_values(config, {"general.enableTips": False, "gui.titlePosition.x": 426}, "Mod")
        self.assertEqual(changes, ["general.enableTips: true -> false", "gui.titlePosition.x: 212 -> 426"])
        self.assertIs(config["general"]["enableTips"], False)
        self.assertEqual(config["gui"]["titlePosition"]["x"], 426)

    def test_unchanged_value_is_not_reported(self):
        self.assertEqual(configure.set_values(self.config(), {"general.enableTips": True}, "Mod"), [])

    def test_typo_in_the_path_is_refused(self):
        for path in ("general.enableTip", "genral.enableTips", "general.enableTips.deeper"):
            with self.subTest(path=path), self.assertRaises(configure.ConfigError) as caught:
                configure.set_values(self.config(), {path: False}, "Skyblocker")
            self.assertIn("Skyblocker has no setting called", str(caught.exception))

    def test_wrong_type_is_refused(self):
        for path, value in (("general.enableTips", 0), ("general.count", True), ("general.name", 1),
                            ("gui.titlePosition", False)):
            with self.subTest(path=path), self.assertRaises(configure.ConfigError):
                configure.set_values(self.config(), {path: value}, "Mod")

    def test_numbers_keep_the_settings_own_kind(self):
        config = self.config()
        configure.set_values(config, {"general.scale": 2, "general.count": 4.0}, "Mod")
        self.assertEqual((repr(config["general"]["scale"]), repr(config["general"]["count"])), ("2.0", "4"))
        with self.assertRaises(configure.ConfigError):
            configure.set_values(config, {"general.count": 4.5}, "Mod")  # no whole-number equivalent


# ─── resource packs ───────────────────────────────────────────────────────────


class ResourcePackTests(unittest.TestCase):
    AVAILABLE = {"Clean.zip", "Dark UI.zip", "Old.zip"}

    def test_adds_the_line_when_options_has_none(self):
        text, changes = configure.apply_resourcepacks(OPTIONS_TXT, ["Clean.zip", "Dark UI.zip"], self.AVAILABLE)
        self.assertTrue(text.startswith(OPTIONS_TXT))
        self.assertTrue(text.endswith('resourcePacks:["vanilla","file/Clean.zip","file/Dark UI.zip"]\r\n'))
        self.assertEqual(changes, ["resource packs: (none) -> vanilla, file/Clean.zip, file/Dark UI.zip"])

    def test_keeps_built_in_packs_and_replaces_old_file_packs(self):
        options = 'version:4671\nresourcePacks:["vanilla","fabric","file/Old.zip"]\ngamma:0.5\n'
        text, _ = configure.apply_resourcepacks(options, ["Dark UI.zip"], self.AVAILABLE)
        self.assertEqual(text, 'version:4671\nresourcePacks:["vanilla","fabric","file/Dark UI.zip"]\ngamma:0.5\n')

    def test_order_is_kept_bottom_to_top(self):
        text, _ = configure.apply_resourcepacks("resourcePacks:[]\n", ["Dark UI.zip", "Clean.zip"], self.AVAILABLE)
        self.assertEqual(text, 'resourcePacks:["vanilla","file/Dark UI.zip","file/Clean.zip"]\n')

    def test_pack_missing_from_the_folder_is_refused(self):
        with self.assertRaises(configure.ConfigError) as caught:
            configure.apply_resourcepacks(OPTIONS_TXT, ["Clean.zip", "Gone.zip"], self.AVAILABLE)
        self.assertIn("Gone.zip", str(caught.exception))

    def test_older_format_packs_are_marked_as_accepted(self):
        options = 'resourcePacks:["vanilla"]\nincompatibleResourcePacks:["vanilla-ish","file/Stale.zip"]\n'
        text, changes = configure.apply_resourcepacks(options, ["Old.zip", "Clean.zip"], self.AVAILABLE, ["Old.zip"])
        self.assertIn('incompatibleResourcePacks:["vanilla-ish","file/Old.zip"]\n', text)
        self.assertEqual(changes[1], "accepted as older-format: vanilla-ish, file/Stale.zip -> vanilla-ish, file/Old.zip")

    def test_allow_older_must_also_be_enabled(self):
        with self.assertRaises(configure.ConfigError):
            configure.apply_resourcepacks(OPTIONS_TXT, ["Clean.zip"], self.AVAILABLE, ["Old.zip"])

    def test_running_twice_changes_nothing_the_second_time(self):
        once, _ = configure.apply_resourcepacks(OPTIONS_TXT, ["Old.zip", "Clean.zip"], self.AVAILABLE, ["Old.zip"])
        twice, changes = configure.apply_resourcepacks(once, ["Old.zip", "Clean.zip"], self.AVAILABLE, ["Old.zip"])
        self.assertEqual((twice, changes), (once, []))


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
            self.assertEqual(configure.odin_names_not_in_jar(jar, ["Blood Camp", "King Relics", "King Relic", "blood camp"]),
                             ["King Relics"])

    def test_wrong_format_is_refused(self):
        with self.assertRaises(configure.ConfigError):
            configure.enable_odin_modules('{"modules": []}', ["Blood Camp"])
        with self.assertRaises(configure.ConfigError):
            configure.disable_odin_modules('{"modules": []}', ["Supply Helper"])

    def test_disable_switches_off_and_keeps_settings(self):
        existing = json.dumps([
            {"name": "Supply Helper", "enabled": True, "settings": {"Beacon": True}},
            {"name": "Blood Camp", "enabled": True, "settings": {}},
        ])
        text, changes = configure.disable_odin_modules(existing, ["supply helper"])
        modules = json.loads(text)
        self.assertEqual(modules[0], {"name": "Supply Helper", "enabled": False, "settings": {"Beacon": True}})
        self.assertTrue(modules[1]["enabled"])
        self.assertEqual(changes, ["Supply Helper: off"])

    def test_disabling_an_absent_or_already_off_module_changes_nothing(self):
        existing = json.dumps([{"name": "Pearl Waypoints", "enabled": False, "settings": {}}])
        text, changes = configure.disable_odin_modules(existing, ["Pearl Waypoints", "Build Helper"])
        self.assertEqual((json.loads(text), changes), (json.loads(existing), []))
        self.assertEqual(configure.disable_odin_modules("", ["Build Helper"])[1], [])


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

    # -- the current settings.toml shape: reset + set, Skyblocker, packs, Odin on/off

    FULL = {
        "resourcepacks": {"enable": ["Old.zip", "Dark.zip"], "allow_older": ["Old.zip"]},
        "skyhanni": {"reset_to_defaults_in": ["garden", "fishing"],
                     "set": {"garden.visitorTimer": False, "gui.titleY": 70}},
        "skyblocker": {"set": {"general.enableTips": False}},
        "odin": {"enable": ["Blood Camp"], "disable": ["Supply Helper"]},
    }

    def full_instance(self):
        (self.inst / "resourcepacks").mkdir()
        for name in ("Old.zip", "Dark.zip"):
            (self.inst / "resourcepacks" / name).write_bytes(b"PK")
        fake_odin_jar(self.inst / "mods" / "odin-0.3.4.jar", ["Blood Camp", "Supply Helper"])
        self.skyhanni.write_text(json.dumps({
            "garden": {"visitorTimer": True, "pests": {"finder": True}},  # defaults: true, false
            "fishing": {"hideLobbyFish": True, "trophyChat": True},     # defaults: false, true
            "gui": {"titleY": 160},
        }))
        (self.inst / "config" / "skyblocker.json").write_text(json.dumps({"general": {"enableTips": True}}))
        (self.inst / "config" / "odin" / "odin-config.json").write_text(json.dumps(
            [{"name": "Supply Helper", "enabled": True, "settings": {}}]))

    def test_reset_then_set_then_everything_else(self):
        self.full_instance()
        report = configure.configure(self.inst, self.FULL)
        self.assertEqual(sorted(report["SkyHanni"]), [
            "fishing.hideLobbyFish: back to default",
            "garden.pests.finder: back to default",
            "garden.visitorTimer: true -> false",  # set wins; the reset leaves it alone
            "gui.titleY: 160 -> 70",
        ])
        self.assertEqual(report["Skyblocker"], ["general.enableTips: true -> false"])
        self.assertEqual(report["Odin"], ["Blood Camp: on", "Supply Helper: off"])
        self.assertEqual(len(report["Resource packs"]), 2)

        skyhanni = json.loads(self.skyhanni.read_text())
        self.assertEqual(skyhanni, {"garden": {"visitorTimer": False, "pests": {"finder": False}},
                                    "fishing": {"hideLobbyFish": False, "trophyChat": True},
                                    "gui": {"titleY": 70}})
        options = (self.inst / "options.txt").read_bytes().decode()
        self.assertIn('resourcePacks:["vanilla","file/Old.zip","file/Dark.zip"]\r\n', options)
        self.assertIn('incompatibleResourcePacks:["file/Old.zip"]\r\n', options)
        with zipfile.ZipFile(report["_backup"][0]) as z:
            self.assertIn("config/skyblocker.json", z.namelist())

    def test_full_settings_settle_after_one_run(self):
        self.full_instance()
        configure.configure(self.inst, self.FULL)
        report = configure.configure(self.inst, self.FULL)
        self.assertEqual({k: v for k, v in report.items() if v}, {})  # no changes, no backup
        self.assertEqual(len(list((self.inst / "settings-backups").iterdir())), 1)

    def test_odin_module_in_both_lists_is_refused(self):
        self.full_instance()
        settings = dict(self.FULL, odin={"enable": ["Blood Camp"], "disable": ["blood camp"]})
        with self.assertRaises(configure.ConfigError) as caught:
            configure.configure(self.inst, settings)
        self.assertIn("both enable and disable", str(caught.exception))

    def test_missing_resource_pack_stops_the_run_before_anything_is_written(self):
        self.full_instance()
        (self.inst / "resourcepacks" / "Dark.zip").unlink()
        before = (self.inst / "options.txt").read_bytes()
        with self.assertRaises(configure.ConfigError):
            configure.configure(self.inst, self.FULL)
        self.assertEqual((self.inst / "options.txt").read_bytes(), before)
        self.assertFalse((self.inst / "settings-backups").exists())

    def test_skyblocker_typo_stops_the_run_before_anything_is_written(self):
        self.full_instance()
        settings = dict(self.FULL, skyblocker={"set": {"general.enableTip": False}})
        before = self.skyhanni.read_bytes()
        with self.assertRaises(configure.ConfigError):
            configure.configure(self.inst, settings)
        self.assertEqual(self.skyhanni.read_bytes(), before)


# ─── the real repo settings file ──────────────────────────────────────────────


class RepoSettingsTests(unittest.TestCase):
    def test_settings_toml_parses_and_has_no_duplicate_keys(self):
        import tomllib
        settings = tomllib.loads((REPO / "settings.toml").read_text(encoding="utf-8"))
        keys = list(settings["keybinds"].values())
        self.assertEqual(len(keys), len(set(keys)), "two actions bound to the same key")
        odin = [n.lower() for n in settings["odin"]["enable"] + settings["odin"]["disable"]]
        self.assertEqual(len(odin), len(set(odin)), "an Odin module listed twice, or as both on and off")
        self.assertTrue(settings["skyhanni"]["reset_to_defaults_in"])
        self.assertNotIn("enable_all_in", settings["skyhanni"], "turning on whole sections is what caused the spam")

    def test_titles_are_moved_off_the_middle_of_the_screen(self):
        import tomllib
        settings = tomllib.loads((REPO / "settings.toml").read_text(encoding="utf-8"))
        self.assertFalse(settings["skyhanni"]["set"]["gui.titlePosition.centerY"])
        self.assertGreaterEqual(settings["skyblocker"]["set"]["uiAndVisuals.titleContainer.y"], 0)

    @unittest.skipUnless((configure.DEFAULT_INSTANCE / "config" / "skyblocker.json").is_file(), "no local Modrinth instance")
    def test_settings_apply_cleanly_to_the_real_instance(self):
        # A dry run reads the real configs and jars and writes nothing; it fails on any typo,
        # renamed option, wrong type, missing pack or unknown Odin module.
        import tomllib
        settings = tomllib.loads((REPO / "settings.toml").read_text(encoding="utf-8"))
        with mock.patch.object(configure, "game_running", return_value=False):
            report = configure.configure(configure.DEFAULT_INSTANCE, settings, dry_run=True)
        self.assertNotIn("_backup", report)

    @unittest.skipUnless((configure.DEFAULT_INSTANCE / "mods").is_dir(), "no local Modrinth instance")
    def test_real_skyhanni_jar_has_the_toggles_we_rely_on(self):
        toggles = dict(configure.skyhanni_feature_toggles(configure.find_jar(configure.DEFAULT_INSTANCE, "skyhanni*.jar")))
        self.assertGreater(len(toggles), 500)
        self.assertIn("garden.visitors.timer.enabled", toggles)
        self.assertIn("event.diana.guess", toggles)

    @unittest.skipUnless((configure.DEFAULT_INSTANCE / "mods").is_dir(), "no local Modrinth instance")
    def test_every_odin_name_in_settings_exists_in_the_real_jar(self):
        import tomllib
        odin = tomllib.loads((REPO / "settings.toml").read_text(encoding="utf-8"))["odin"]
        names = odin["enable"] + odin["disable"]
        jar = configure.find_jar(configure.DEFAULT_INSTANCE, "odin*.jar")
        self.assertEqual(configure.odin_names_not_in_jar(jar, names), [])


if __name__ == "__main__":
    unittest.main()
