"""Tests for tools/modpack.py. Standard library only, and no network: Modrinth and the
Fabric meta server are replaced by FakeModrinth below.

Run from the repo root:
    python -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import modpack  # noqa: E402

MC = "26.2"


# ─── fakes & builders ─────────────────────────────────────────────────────────


def make_version(slug, number, channel="release", date="2026-09-01", requires=(), incompatible=()):
    """A Modrinth version object with just the fields modpack.py reads."""
    return {
        "id": f"v-{slug}-{number}",
        "version_number": number,
        "version_type": channel,
        "date_published": f"{date}T12:00:00.000Z",
        "files": [
            {
                "filename": f"{slug}-{number}.jar",
                "url": f"https://cdn.modrinth.com/data/{slug}/{number}.jar",
                "size": 1000 + len(number),
                "primary": True,
                "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
            }
        ],
        "dependencies": [{"project_id": f"id-{d}", "dependency_type": "required"} for d in requires]
        + [{"project_id": f"id-{d}", "dependency_type": "incompatible"} for d in incompatible]
        + [{"project_id": "id-ignored", "dependency_type": "optional"}],
    }


class FakeModrinth:
    """Stands in for modpack.fetch_json. Routes URLs to in-memory projects/versions."""

    def __init__(self):
        self.projects = {}  # project id -> project
        self.versions = {}  # project id -> [versions]
        self.loaders = [
            {"loader": {"version": "0.20.0-beta.1", "stable": False}},
            {"loader": {"version": "0.19.5", "stable": True}},
            {"loader": {"version": "0.19.4", "stable": True}},
        ]

    def add(self, slug, *versions, server_side="unsupported"):
        project = {"id": f"id-{slug}", "slug": slug, "title": slug.replace("-", " ").title(),
                   "client_side": "required", "server_side": server_side}
        self.projects[project["id"]] = project
        self.versions[project["id"]] = list(versions)
        return project

    def __call__(self, url):
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.netloc == "meta.fabricmc.net":
            return self.loaders if parsed.path.endswith(f"/loader/{MC}") else []
        path = parsed.path.removeprefix("/v2")
        if path == "/projects":
            wanted = json.loads(query["ids"][0])
            return [p for p in self.projects.values() if p["id"] in wanted or p["slug"] in wanted]
        if m := re.fullmatch(r"/project/([^/]+)/version", path):
            # The script must always ask for Fabric builds of the pack's Minecraft version.
            assert json.loads(query["loaders"][0]) == ["fabric"], url
            assert json.loads(query["game_versions"][0]) == [MC], url
            return self.versions.get(m.group(1))
        if m := re.fullmatch(r"/project/([^/]+)", path):
            return self.projects.get(m.group(1))
        raise AssertionError(f"unexpected URL: {url}")


class PackTestCase(unittest.TestCase):
    """Runs modpack.py against a throwaway pack folder and a fake Modrinth."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.fake = FakeModrinth()
        patcher = mock.patch.multiple(
            modpack,
            ROOT=self.root,
            PACK_FILE=self.root / "pack.toml",
            MODS_FILE=self.root / "mods.toml",
            LOCK_FILE=self.root / "modpack.lock.json",
            README_FILE=self.root / "README.md",
            OVERRIDES_DIR=self.root / "overrides",
            DIST_DIR=self.root / "dist",
            fetch_json=self.fake,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write_pack()

    # -- helpers

    def write_pack(self, mc=MC, loader_version="latest"):
        (self.root / "pack.toml").write_text(
            f'[pack]\nname = "Test Pack"\nversion = "1.0.0"\nsummary = "for tests"\n\n'
            f'[minecraft]\nversion = "{mc}"\n\n[loader]\nname = "fabric"\nversion = "{loader_version}"\n',
            encoding="utf-8",
        )

    def write_mods(self, *entries):
        """entries: slug strings, or dicts of mods.toml fields."""
        blocks = []
        for e in entries:
            e = {"slug": e} if isinstance(e, str) else e
            e.setdefault("category", "Main")
            e.setdefault("why", f"does {e['slug']} things")
            blocks.append("[[mod]]\n" + "".join(f'{k} = "{v}"\n' for k, v in e.items()))
        (self.root / "mods.toml").write_text("\n".join(blocks), encoding="utf-8")

    def run_quiet(self, fn, *args):
        """Call fn, swallowing its stdout. Returns (stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fn(*args)
        return out.getvalue(), err.getvalue()

    def assert_fails(self, fn, *args, message):
        """fn must exit with status 1 and print an error containing `message`."""
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                fn(*args)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn(message, err.getvalue())

    def lock(self):
        return json.loads((self.root / "modpack.lock.json").read_text(encoding="utf-8"))

    def locked_versions(self):
        return {m["slug"]: m["version"] for m in self.lock()["mods"]}


# ─── choosing a version ───────────────────────────────────────────────────────


class PickVersionTests(unittest.TestCase):
    project = {"slug": "demo"}

    def test_prefers_release_over_a_newer_beta(self):
        versions = [make_version("demo", "2.0-beta", "beta", "2026-09-10"),
                    make_version("demo", "1.0", "release", "2026-09-01")]
        chosen, warning = modpack.pick_version(self.project, versions, {})
        self.assertEqual(chosen["version_number"], "1.0")
        self.assertIsNone(warning)

    def test_newest_release_wins_even_if_api_order_is_shuffled(self):
        versions = [make_version("demo", "1.0", date="2026-08-01"),
                    make_version("demo", "1.2", date="2026-09-20"),
                    make_version("demo", "1.1", date="2026-09-01")]
        chosen, _ = modpack.pick_version(self.project, versions, {})
        self.assertEqual(chosen["version_number"], "1.2")

    def test_falls_back_to_beta_with_a_warning_when_no_release_exists(self):
        versions = [make_version("demo", "0.9-alpha", "alpha", "2026-09-10"),
                    make_version("demo", "0.8-beta", "beta", "2026-09-01")]
        chosen, warning = modpack.pick_version(self.project, versions, {})
        self.assertEqual(chosen["version_number"], "0.8-beta")  # beta beats a newer alpha
        self.assertIn("no release build", warning)

    def test_channel_beta_takes_the_newest_beta_over_an_older_release(self):
        versions = [make_version("demo", "2.0-beta", "beta", "2026-09-10"),
                    make_version("demo", "1.0", "release", "2026-09-01")]
        chosen, warning = modpack.pick_version(self.project, versions, {"channel": "beta"})
        self.assertEqual(chosen["version_number"], "2.0-beta")
        self.assertIsNone(warning)

    def test_pin_selects_that_exact_version(self):
        versions = [make_version("demo", "1.1", date="2026-09-10"), make_version("demo", "1.0")]
        chosen, _ = modpack.pick_version(self.project, versions, {"pin": "1.0"})
        self.assertEqual(chosen["version_number"], "1.0")

    def test_pin_that_does_not_exist_fails(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            modpack.pick_version(self.project, [make_version("demo", "1.0")], {"pin": "9.9"})


# ─── reading mods.toml ────────────────────────────────────────────────────────


class ModListTests(PackTestCase):
    def test_duplicate_slug_fails(self):
        self.write_mods("alpha", "alpha")
        self.assert_fails(modpack.load_mod_list, message="listed twice")

    def test_unknown_channel_fails(self):
        self.write_mods({"slug": "alpha", "channel": "nightly"})
        self.assert_fails(modpack.load_mod_list, message="channel must be one of")

    def test_entry_without_slug_fails(self):
        (self.root / "mods.toml").write_text('[[mod]]\nwhy = "oops"\n', encoding="utf-8")
        self.assert_fails(modpack.load_mod_list, message="without a slug")


# ─── update ───────────────────────────────────────────────────────────────────


class UpdateTests(PackTestCase):
    def test_pulls_in_dependencies_of_dependencies(self):
        self.fake.add("app", make_version("app", "1.0", requires=["lib-a"]))
        self.fake.add("lib-a", make_version("lib-a", "1.0", requires=["lib-b"]))
        self.fake.add("lib-b", make_version("lib-b", "1.0"))
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])

        mods = {m["slug"]: m for m in self.lock()["mods"]}
        self.assertEqual(set(mods), {"app", "lib-a", "lib-b"})
        self.assertEqual(mods["app"]["category"], "Main")
        self.assertNotIn("required_by", mods["app"])
        self.assertEqual(mods["lib-a"]["required_by"], ["app"])
        self.assertEqual(mods["lib-b"]["required_by"], ["lib-a"])
        self.assertNotIn("category", mods["lib-b"])

    def test_shared_library_is_locked_once_and_lists_every_dependent(self):
        self.fake.add("one", make_version("one", "1.0", requires=["kotlin"]))
        self.fake.add("two", make_version("two", "1.0", requires=["kotlin"]))
        self.fake.add("kotlin", make_version("kotlin", "1.0"))
        self.write_mods("one", "two")
        self.run_quiet(modpack.cmd_update, [])

        slugs = [m["slug"] for m in self.lock()["mods"]]
        self.assertEqual(slugs.count("kotlin"), 1)
        kotlin = next(m for m in self.lock()["mods"] if m["slug"] == "kotlin")
        self.assertEqual(kotlin["required_by"], ["one", "two"])

    def test_lock_keeps_mods_toml_order_then_libraries_alphabetically(self):
        self.fake.add("zeta", make_version("zeta", "1.0", requires=["lib-y", "lib-x"]))
        self.fake.add("alpha", make_version("alpha", "1.0"))
        self.fake.add("lib-x", make_version("lib-x", "1.0"))
        self.fake.add("lib-y", make_version("lib-y", "1.0"))
        self.write_mods("zeta", "alpha")
        self.run_quiet(modpack.cmd_update, [])
        self.assertEqual([m["slug"] for m in self.lock()["mods"]], ["zeta", "alpha", "lib-x", "lib-y"])

    def test_lock_records_the_exact_file(self):
        self.fake.add("app", make_version("app", "1.0"))
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])
        app = self.lock()["mods"][0]
        self.assertEqual(app["file"], "app-1.0.jar")
        self.assertEqual(app["url"], "https://cdn.modrinth.com/data/app/1.0.jar")
        self.assertEqual((app["sha1"], app["sha512"]), ("a" * 40, "b" * 128))
        self.assertEqual(app["channel"], "release")

    def test_server_side_is_mapped_to_mrpack_env_values(self):
        for side, expected in [("required", "required"), ("optional", "optional"),
                               ("unsupported", "unsupported"), ("unknown", "unsupported")]:
            self.fake.add(f"mod-{side}", make_version(f"mod-{side}", "1.0"), server_side=side)
        self.write_mods(*[f"mod-{s}" for s in ["required", "optional", "unsupported", "unknown"]])
        self.run_quiet(modpack.cmd_update, [])
        env = {m["slug"]: m["env"] for m in self.lock()["mods"]}
        self.assertEqual(env["mod-required"], {"client": "required", "server": "required"})
        self.assertEqual(env["mod-optional"]["server"], "optional")
        self.assertEqual(env["mod-unsupported"]["server"], "unsupported")
        self.assertEqual(env["mod-unknown"]["server"], "unsupported")

    def test_latest_loader_means_newest_stable_not_newest_beta(self):
        self.fake.add("app", make_version("app", "1.0"))
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])
        self.assertEqual(self.lock()["loader"], {"name": "fabric", "version": "0.19.5"})

    def test_explicit_loader_version_is_used_as_is(self):
        self.write_pack(loader_version="0.19.4")
        self.fake.add("app", make_version("app", "1.0"))
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])
        self.assertEqual(self.lock()["loader"]["version"], "0.19.4")

    def test_mods_that_declare_each_other_incompatible_are_refused(self):
        self.fake.add("optifine-ish", make_version("optifine-ish", "1.0", incompatible=["sodium-ish"]))
        self.fake.add("sodium-ish", make_version("sodium-ish", "1.0"))
        self.write_mods("optifine-ish", "sodium-ish")
        self.assert_fails(modpack.cmd_update, [], message="incompatible with sodium-ish")
        self.assertFalse((self.root / "modpack.lock.json").exists())

    def test_incompatibility_with_a_mod_not_in_the_pack_is_fine(self):
        self.fake.add("app", make_version("app", "1.0", incompatible=["not-in-pack"]))
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])
        self.assertEqual(self.locked_versions(), {"app": "1.0"})

    def test_mod_missing_from_modrinth_fails(self):
        self.write_mods("does-not-exist")
        self.assert_fails(modpack.cmd_update, [], message="not found on Modrinth: does-not-exist")

    def test_mod_without_a_build_for_this_version_fails(self):
        self.fake.add("old-mod")  # exists, but no 26.2 Fabric versions
        self.write_mods("old-mod")
        self.assert_fails(modpack.cmd_update, [], message="old-mod has no fabric build")

    def test_warns_when_falling_back_to_a_beta(self):
        self.fake.add("app", make_version("app", "0.3-beta", "beta"))
        self.write_mods("app")
        out, _ = self.run_quiet(modpack.cmd_update, [])
        self.assertIn("no release build", out)
        self.assertEqual(self.lock()["mods"][0]["channel"], "beta")

    def test_second_update_reports_nothing_changed(self):
        self.fake.add("app", make_version("app", "1.0"))
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])
        out, _ = self.run_quiet(modpack.cmd_update, [])
        self.assertIn("already up to date", out)

    def test_update_reports_version_changes(self):
        self.fake.add("app", make_version("app", "1.0", date="2026-09-01"))
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])
        self.fake.versions["id-app"].append(make_version("app", "1.1", date="2026-09-20"))
        out, _ = self.run_quiet(modpack.cmd_update, [])
        self.assertIn("~ app  1.0 -> 1.1", out)


class PartialUpdateTests(PackTestCase):
    def setUp(self):
        super().setUp()
        self.fake.add("alpha", make_version("alpha", "1.0", date="2026-09-01"))
        self.fake.add("beta", make_version("beta", "1.0", date="2026-09-01"))
        self.write_mods("alpha", "beta")
        self.run_quiet(modpack.cmd_update, [])
        # Both mods publish an update afterwards.
        self.fake.versions["id-alpha"].append(make_version("alpha", "2.0", date="2026-09-20"))
        self.fake.versions["id-beta"].append(make_version("beta", "2.0", date="2026-09-20"))

    def test_only_the_named_mod_moves(self):
        self.run_quiet(modpack.cmd_update, ["alpha"])
        self.assertEqual(self.locked_versions(), {"alpha": "2.0", "beta": "1.0"})

    def test_full_update_moves_everything(self):
        self.run_quiet(modpack.cmd_update, [])
        self.assertEqual(self.locked_versions(), {"alpha": "2.0", "beta": "2.0"})

    def test_unknown_slug_is_rejected(self):
        self.assert_fails(modpack.cmd_update, ["gamma"], message="not in mods.toml or the lock file: gamma")

    def test_refused_after_minecraft_version_changes(self):
        self.write_pack(mc="26.3")
        self.assert_fails(modpack.cmd_update, ["alpha"], message="run a full `update` first")


class ReadmeTableTests(PackTestCase):
    def test_table_is_rewritten_between_the_markers_only(self):
        (self.root / "README.md").write_text(
            "# Title\n\nbefore\n\n<!-- mods:start -->\nstale table\n<!-- mods:end -->\n\nafter\n",
            encoding="utf-8",
        )
        self.fake.add("app", make_version("app", "0.5-beta", "beta", requires=["lib"]))
        self.fake.add("lib", make_version("lib", "1.0"))
        self.write_mods({"slug": "app", "category": "Dungeons", "why": "solves puzzles"})
        self.run_quiet(modpack.cmd_update, [])

        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# Title\n\nbefore\n\n<!-- mods:start -->"))
        self.assertTrue(readme.endswith("<!-- mods:end -->\n\nafter\n"))
        self.assertNotIn("stale table", readme)
        self.assertIn("#### Dungeons", readme)
        self.assertIn("| [App](https://modrinth.com/mod/app) | `0.5-beta` _(beta)_ | solves puzzles |", readme)
        self.assertIn("Plus 1 libraries pulled in automatically: [Lib](https://modrinth.com/mod/lib).", readme)
        self.assertIn(f"Minecraft **{MC}**, Fabric Loader **0.19.5**", readme)


# ─── build ────────────────────────────────────────────────────────────────────


class BuildTests(PackTestCase):
    def setUp(self):
        super().setUp()
        self.fake.add("app", make_version("app", "1.0", requires=["lib"]))
        self.fake.add("lib", make_version("lib", "2.0"), server_side="required")
        self.write_mods("app")
        self.run_quiet(modpack.cmd_update, [])

    def read_pack(self, name="Test-Pack-1.0.0.mrpack"):
        path = self.root / "dist" / name
        self.assertTrue(path.exists(), f"{name} was not built")
        return zipfile.ZipFile(path)

    def test_writes_a_valid_modrinth_index(self):
        self.run_quiet(modpack.cmd_build, None)
        with self.read_pack() as z:
            index = json.loads(z.read("modrinth.index.json"))
        self.assertEqual(index["formatVersion"], 1)
        self.assertEqual(index["game"], "minecraft")
        self.assertEqual(index["name"], "Test Pack")
        self.assertEqual(index["versionId"], "1.0.0")
        self.assertEqual(index["dependencies"], {"minecraft": MC, "fabric-loader": "0.19.5"})
        files = {f["path"]: f for f in index["files"]}
        self.assertEqual(set(files), {"mods/app-1.0.jar", "mods/lib-2.0.jar"})
        lib = files["mods/lib-2.0.jar"]
        self.assertEqual(lib["downloads"], ["https://cdn.modrinth.com/data/lib/2.0.jar"])
        self.assertEqual(lib["hashes"], {"sha1": "a" * 40, "sha512": "b" * 128})
        self.assertEqual(lib["env"], {"client": "required", "server": "required"})
        self.assertEqual(lib["fileSize"], 1003)

    def test_version_override_changes_file_name_and_index(self):
        self.run_quiet(modpack.cmd_build, "2.5.0")
        with self.read_pack("Test-Pack-2.5.0.mrpack") as z:
            self.assertEqual(json.loads(z.read("modrinth.index.json"))["versionId"], "2.5.0")

    def test_overrides_are_packed_but_gitkeep_is_not(self):
        (self.root / "overrides" / "config").mkdir(parents=True)
        (self.root / "overrides" / ".gitkeep").write_text("")
        (self.root / "overrides" / "config" / "demo.json").write_text('{"on": true}')
        self.run_quiet(modpack.cmd_build, None)
        with self.read_pack() as z:
            self.assertEqual(sorted(z.namelist()), ["modrinth.index.json", "overrides/config/demo.json"])
            self.assertEqual(z.read("overrides/config/demo.json"), b'{"on": true}')

    def add_companion(self, *jar_names):
        with open(self.root / "pack.toml", "a", encoding="utf-8") as f:
            f.write('\n[companion]\njar_glob = "companion-mod/build/libs/menus-*.jar"\ninstall_as = "mods/menus.jar"\n')
        libs = self.root / "companion-mod" / "build" / "libs"
        libs.mkdir(parents=True)
        for name in jar_names:
            (libs / name).write_bytes(f"jar bytes of {name}".encode())

    def test_companion_jar_is_shipped_under_its_fixed_name(self):
        self.add_companion("menus-1.2.0.jar", "menus-1.2.0-sources.jar")
        self.run_quiet(modpack.cmd_build, None)
        with self.read_pack() as z:
            self.assertEqual(z.read("overrides/mods/menus.jar"), b"jar bytes of menus-1.2.0.jar")
            self.assertFalse([n for n in z.namelist() if "sources" in n])

    def test_build_fails_when_the_companion_is_not_built(self):
        self.add_companion()
        self.assert_fails(modpack.cmd_build, None, message="companion mod not built yet")
        self.assertFalse((self.root / "dist").exists())

    def test_build_fails_with_two_companion_versions_lying_around(self):
        self.add_companion("menus-1.0.0.jar", "menus-1.1.0.jar")
        self.assert_fails(modpack.cmd_build, None, message="more than one companion jar")

    def test_fails_without_a_lock_file(self):
        (self.root / "modpack.lock.json").unlink()
        self.assert_fails(modpack.cmd_build, None, message="no modpack.lock.json yet")

    def test_fails_when_mods_toml_has_a_mod_that_is_not_locked(self):
        self.write_mods("app", "brand-new")
        self.assert_fails(modpack.cmd_build, None, message="aren't locked yet (brand-new)")

    def test_fails_when_minecraft_version_changed_since_the_lock(self):
        self.write_pack(mc="26.3")
        self.assert_fails(modpack.cmd_build, None, message="changed Minecraft version/loader")


# ─── the real, committed pack ─────────────────────────────────────────────────


class CommittedPackTests(unittest.TestCase):
    """Checks the actual pack.toml / mods.toml / modpack.lock.json in this repo."""

    @classmethod
    def setUpClass(cls):
        cls.pack = modpack.load_pack()
        cls.listed = modpack.load_mod_list()
        cls.lock = modpack.load_lock()

    def test_lock_matches_pack_toml(self):
        self.assertEqual(self.lock["minecraft"], self.pack["minecraft"]["version"])
        self.assertEqual(self.lock["loader"]["name"], self.pack["loader"]["name"])

    def test_every_listed_mod_is_locked_with_its_category(self):
        locked = {m["slug"]: m for m in self.lock["mods"]}
        for entry in self.listed:
            with self.subTest(mod=entry["slug"]):
                self.assertIn(entry["slug"], locked)
                self.assertEqual(locked[entry["slug"]]["category"], entry["category"])

    def test_every_dependency_is_in_the_lock(self):
        ids = {m["project_id"] for m in self.lock["mods"]}
        for m in self.lock["mods"]:
            with self.subTest(mod=m["slug"]):
                self.assertLessEqual(set(m["requires"]), ids)

    def test_no_locked_mod_is_incompatible_with_another(self):
        ids = {m["project_id"] for m in self.lock["mods"]}
        for m in self.lock["mods"]:
            with self.subTest(mod=m["slug"]):
                self.assertFalse(set(m["incompatible"]) & ids)

    def test_downloads_are_modrinth_cdn_with_full_hashes(self):
        for m in self.lock["mods"]:
            with self.subTest(mod=m["slug"]):
                self.assertTrue(m["url"].startswith("https://cdn.modrinth.com/"))
                self.assertRegex(m["sha1"], r"^[0-9a-f]{40}$")
                self.assertRegex(m["sha512"], r"^[0-9a-f]{128}$")
                self.assertGreater(m["size"], 0)

    def test_no_two_mods_share_a_file_name(self):
        files = [m["file"] for m in self.lock["mods"]]
        self.assertEqual(len(files), len(set(files)))

    def test_known_risky_mods_stay_out(self):
        # Mouse Tweaks' scroll-to-move sends real clicks in SkyBlock's chest menus.
        slugs = {m["slug"] for m in self.lock["mods"]}
        self.assertNotIn("mouse-tweaks", slugs)


if __name__ == "__main__":
    unittest.main()
