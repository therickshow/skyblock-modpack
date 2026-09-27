#!/usr/bin/env python3
"""Apply settings.toml to an installed copy of the pack. Standard library only (Python 3.11+).

  python tools/configure.py                       apply to the Modrinth App instance
  python tools/configure.py --instance <folder>   apply to a different instance folder
  python tools/configure.py --dry-run             show what would change, write nothing

Start the game once before the first run (mods create their config files on launch), and
close it before every run (Minecraft rewrites options.txt when it exits). Each run saves the
files it is about to change to <instance>/settings-backups/<date_time>.zip first.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tomllib
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classfile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "settings.toml"
DEFAULT_INSTANCE = Path(os.environ.get("APPDATA", "~")) / "ModrinthApp" / "profiles" / "SkyBlock-QoL-1.0.0"

SKYHANNI_CONFIG_PACKAGE = "at/hannibal2/skyhanni/config/"
SKYHANNI_ROOT = "at/hannibal2/skyhanni/config/SkyHanniConfig"
GSON_EXPOSE = "Lcom/google/gson/annotations/Expose;"
FEATURE_TOGGLE = "Lat/hannibal2/skyhanni/config/FeatureToggle;"
ODIN_MODULE_PACKAGE = "com/odtheking/odin/features/impl/"


class ConfigError(Exception):
    """A problem the user needs to fix; printed without a traceback."""


def read_exact(path: Path) -> str:
    """Read a text file without translating line endings (Path.read_text turns \\r\\n into \\n)."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


# ─── keybinds: options.txt ────────────────────────────────────────────────────


def apply_keybinds(text: str, wanted: dict[str, str]) -> tuple[str, list[str]]:
    """Rebind actions in options.txt text. Returns (new text, list of changes).

    Refuses to bind a key another action already uses (debug keys are F3+key combos, so
    they don't count), and refuses action names that don't exist in the file.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    current: dict[str, tuple[int, str]] = {}  # action -> (line number, key)
    for i, line in enumerate(lines):
        if line.startswith("key_") and ":" in line:
            action, key = line[len("key_"):].rsplit(":", 1)
            current[action] = (i, key)

    unknown = sorted(set(wanted) - set(current))
    if unknown:
        raise ConfigError(
            f"options.txt has no keybind called {', '.join(unknown)} "
            "(typo, or the game hasn't been started since that mod was added)"
        )

    final = {action: key for action, (_, key) in current.items()} | wanted
    for action, key in wanted.items():
        if key.endswith(".unknown"):  # unbinding never clashes
            continue
        clash = sorted(a for a, k in final.items() if k == key and a != action and not a.startswith("key.debug."))
        if clash:
            raise ConfigError(f"can't bind {action} to {key}: already used by {', '.join(clash)}")

    changes = []
    for action, key in wanted.items():
        i, old = current[action]
        if old != key:
            lines[i] = f"key_{action}:{key}"
            changes.append(f"{action}: {old} -> {key}")
    return newline.join(lines) + (newline if text.endswith(("\n", "\r\n")) else ""), changes


# ─── SkyHanni: turn on @FeatureToggle switches by section ─────────────────────


def skyhanni_feature_toggles(jar: Path) -> list[tuple[str, bool]]:
    """(config path, value that means "on") for every @FeatureToggle in SkyHanni's config.

    Walks the config classes from the root the same way Gson serialises them (only @Expose
    fields), so the dotted paths match config/skyhanni/config.json.
    """
    classes: dict[str, list[classfile.Field]] = {}
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            if name.startswith(SKYHANNI_CONFIG_PACKAGE) and name.endswith(".class"):
                try:
                    class_name, fields = classfile.parse(z.read(name))
                except Exception as e:
                    raise ConfigError(f"couldn't read {name} in {jar.name}: {e}") from e
                classes[class_name] = fields
    if SKYHANNI_ROOT not in classes:
        raise ConfigError(f"{jar.name} has no {SKYHANNI_ROOT}; SkyHanni's layout changed, update configure.py")

    toggles: list[tuple[str, bool]] = []

    def walk(class_name: str, prefix: list[str], depth: int):
        for f in classes[class_name]:
            if GSON_EXPOSE not in f.annotations:
                continue
            path = prefix + [f.name]
            if FEATURE_TOGGLE in f.annotations:
                # trueIsEnabled=false marks an inverted switch, where false means "on".
                on_value = f.annotations[FEATURE_TOGGLE].get("trueIsEnabled", True)
                toggles.append((".".join(path), on_value))
            child = f.descriptor[1:-1] if f.descriptor.startswith("L") else None
            if child in classes and depth < 20:
                walk(child, path, depth + 1)

    walk(SKYHANNI_ROOT, [], 0)
    return toggles


def enable_sections(config: dict, toggles: list[tuple[str, bool]], sections: list[str]) -> list[str]:
    """Set every toggle inside `sections` to its "on" value. Returns the paths changed."""
    for section in sections:
        node = config
        for key in section.split("."):
            node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            raise ConfigError(f"SkyHanni config has no section called {section!r}")

    changed = []
    for path, on_value in toggles:
        if not any(path == s or path.startswith(s + ".") for s in sections):
            continue
        *parents, leaf = path.split(".")
        node = config
        for key in parents:
            node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict) or not isinstance(node.get(leaf), bool):
            continue  # not in this config file (or not a plain on/off value): leave it alone
        if node[leaf] != on_value:
            node[leaf] = on_value
            changed.append(path)
    return changed


# ─── Odin: enable modules by display name ─────────────────────────────────────


def enable_odin_modules(text: str, names: list[str]) -> tuple[str, list[str]]:
    """Turn modules on in odin-config.json text. Returns (new text, list of changes)."""
    modules = json.loads(text) if text.strip() else []
    if not isinstance(modules, list):
        raise ConfigError("odin-config.json isn't a list of modules; Odin's format changed")
    by_name = {m["name"].lower(): m for m in modules if isinstance(m, dict) and isinstance(m.get("name"), str)}
    changes = []
    for name in names:
        module = by_name.get(name.lower())
        if module is None:
            # Odin matches on the name, applies "enabled", and treats empty settings as "keep defaults".
            modules.append({"name": name, "enabled": True, "settings": {}})
            changes.append(f"{name}: on")
        elif module.get("enabled") is not True:
            module["enabled"] = True
            changes.append(f"{name}: on")
    return json.dumps(modules, indent=2, ensure_ascii=False), changes


def odin_names_not_in_jar(jar: Path, names: list[str]) -> list[str]:
    """Module names that appear in none of Odin's feature classes (i.e. typos)."""
    with zipfile.ZipFile(jar) as z:
        blob = b"".join(z.read(n) for n in z.namelist() if n.startswith(ODIN_MODULE_PACKAGE) and n.endswith(".class"))
    return [n for n in names if n.encode("utf-8") not in blob]


# ─── instance helpers ─────────────────────────────────────────────────────────


def find_jar(instance: Path, pattern: str) -> Path:
    mods = instance / "mods"
    matches = [p for p in mods.iterdir() if fnmatch.fnmatch(p.name.lower(), pattern)] if mods.is_dir() else []
    if len(matches) != 1:
        raise ConfigError(f"expected exactly one {pattern} in {mods}, found {len(matches)}")
    return matches[0]


def game_running(instance: Path) -> bool:
    """True if a Java process was started with this instance folder (Windows only)."""
    if os.name != "nt":
        return False
    query = ("Get-CimInstance Win32_Process -Filter \"Name='javaw.exe' or Name='java.exe'\" "
             "| ForEach-Object { $_.CommandLine }")
    result = subprocess.run(["powershell", "-NoProfile", "-Command", query],
                            capture_output=True, text=True, timeout=60)
    normalise = lambda s: s.lower().replace("/", "\\")
    return normalise(str(instance.resolve())) in normalise(result.stdout)


def backup(instance: Path, files: list[Path]) -> Path:
    dest = instance / "settings-backups" / f"{datetime.now():%Y-%m-%d_%H-%M-%S}.zip"
    dest.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(instance).as_posix())
    return dest


# ─── main ─────────────────────────────────────────────────────────────────────


def configure(instance: Path, settings: dict, dry_run: bool = False) -> dict[str, list[str]]:
    """Apply settings to the instance. Returns {section: [changes]}."""
    if not (instance / "options.txt").exists():
        raise ConfigError(f"no options.txt in {instance}; start the game once so the mods create their configs")
    if game_running(instance):
        raise ConfigError("the game is running; close it first (Minecraft rewrites options.txt on exit)")

    report: dict[str, list[str]] = {}
    writes: dict[Path, str] = {}

    if keybinds := settings.get("keybinds"):
        path = instance / "options.txt"
        text, report["Keybinds"] = apply_keybinds(read_exact(path), keybinds)
        if report["Keybinds"]:
            writes[path] = text

    if sections := settings.get("skyhanni", {}).get("enable_all_in"):
        path = instance / "config" / "skyhanni" / "config.json"
        if not path.exists():
            raise ConfigError(f"{path} doesn't exist yet; start and close the game once")
        toggles = skyhanni_feature_toggles(find_jar(instance, "skyhanni*.jar"))
        config = json.loads(read_exact(path))
        changed = enable_sections(config, toggles, sections)
        report["SkyHanni"] = [f"{p}: on" for p in changed]
        if changed:
            writes[path] = json.dumps(config, indent=2, ensure_ascii=False)

    if names := settings.get("odin", {}).get("enable"):
        jar = find_jar(instance, "odin*.jar")
        if missing := odin_names_not_in_jar(jar, names):
            raise ConfigError(f"Odin has no module called {', '.join(missing)}")
        path = instance / "config" / "odin" / "odin-config.json"
        text = read_exact(path) if path.exists() else ""
        new_text, report["Odin"] = enable_odin_modules(text, names)
        if report["Odin"]:
            writes[path] = new_text

    if writes and not dry_run:
        report["_backup"] = [str(backup(instance, [p for p in writes if p.exists()]))]
        for path, text in writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
    return report


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE, help="instance folder (has options.txt)")
    parser.add_argument("--settings", type=Path, default=SETTINGS_FILE)
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    parser.add_argument("--verbose", action="store_true", help="list every SkyHanni switch changed")
    args = parser.parse_args()

    try:
        settings = tomllib.loads(args.settings.read_text(encoding="utf-8"))
        report = configure(args.instance.expanduser(), settings, args.dry_run)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    verb = "Would change" if args.dry_run else "Changed"
    for section, changes in report.items():
        if section.startswith("_"):
            continue
        print(f"{section}: {verb.lower()} {len(changes)}")
        shown = changes if (args.verbose or section != "SkyHanni") else []
        if section == "SkyHanni" and changes and not args.verbose:
            by_top = {}
            for c in changes:
                by_top[c.split(".")[0]] = by_top.get(c.split(".")[0], 0) + 1
            shown = [f"{top}: {n} switches turned on" for top, n in by_top.items()]
        for line in shown:
            print(f"  {line}")
    if backup_path := report.get("_backup"):
        print(f"\nBackup of the previous files: {backup_path[0]}")
    elif not args.dry_run:
        print("\nNothing needed changing.")


if __name__ == "__main__":
    main()
