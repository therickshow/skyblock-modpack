#!/usr/bin/env python3
"""Resolve and build the modpack. Standard library only (Python 3.11+).

  python tools/modpack.py update [slug ...]   Resolve mods.toml against Modrinth and pin the
                                              result in modpack.lock.json. With slugs, only
                                              those mods move; everything else stays pinned.
  python tools/modpack.py build [--version X] Write dist/<name>-<version>.mrpack from the lock.

Mod jars are never downloaded here. The .mrpack lists Modrinth CDN URLs + hashes and the
launcher (Modrinth App, Prism, ...) fetches and verifies them on install.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK_FILE = ROOT / "pack.toml"
MODS_FILE = ROOT / "mods.toml"
LOCK_FILE = ROOT / "modpack.lock.json"
README_FILE = ROOT / "README.md"
OVERRIDES_DIR = ROOT / "overrides"
DIST_DIR = ROOT / "dist"

MODRINTH_API = "https://api.modrinth.com/v2"
FABRIC_META = "https://meta.fabricmc.net/v2"
USER_AGENT = "therickshow/skyblock-modpack (https://github.com/therickshow/skyblock-modpack)"

CHANNELS = ["release", "beta", "alpha"]  # most -> least stable
README_START = "<!-- mods:start -->"
README_END = "<!-- mods:end -->"


# ─── helpers ──────────────────────────────────────────────────────────────────


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def modrinth(path: str, **params):
    query = {k: json.dumps(v) if isinstance(v, list) else v for k, v in params.items()}
    url = f"{MODRINTH_API}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return fetch_json(url)


def fail(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_pack() -> dict:
    return tomllib.loads(PACK_FILE.read_text(encoding="utf-8"))


def load_mod_list() -> list[dict]:
    mods = tomllib.loads(MODS_FILE.read_text(encoding="utf-8")).get("mod", [])
    seen = set()
    for m in mods:
        if "slug" not in m:
            fail(f"mods.toml entry without a slug: {m}")
        if m["slug"] in seen:
            fail(f"{m['slug']} is listed twice in mods.toml")
        if m.get("channel", "release") not in CHANNELS:
            fail(f"{m['slug']}: channel must be one of {CHANNELS}")
        seen.add(m["slug"])
    return mods


def load_lock() -> dict | None:
    if not LOCK_FILE.exists():
        return None
    return json.loads(LOCK_FILE.read_text(encoding="utf-8"))


# ─── update ───────────────────────────────────────────────────────────────────


def latest_fabric_loader(mc: str) -> str:
    loaders = fetch_json(f"{FABRIC_META}/versions/loader/{urllib.parse.quote(mc)}")
    if not loaders:
        fail(f"Fabric has no loader for Minecraft {mc}")
    for entry in loaders:
        if entry["loader"]["stable"]:
            return entry["loader"]["version"]
    return loaders[0]["loader"]["version"]


def pick_version(project: dict, versions: list[dict], entry: dict) -> tuple[dict, str | None]:
    """Choose a version for a project. Returns (version, warning)."""
    slug = project["slug"]
    versions = sorted(versions, key=lambda v: v["date_published"], reverse=True)

    if pin := entry.get("pin"):
        for v in versions:
            if v["version_number"] == pin:
                return v, None
        fail(f"{slug}: pinned version {pin!r} doesn't exist for this Minecraft version/loader")

    channel = entry.get("channel", "release")
    allowed = CHANNELS[: CHANNELS.index(channel) + 1]
    for v in versions:
        if v["version_type"] in allowed:
            return v, None
    # Nothing on the requested channel: take the most stable build that exists.
    for ch in CHANNELS:
        for v in versions:
            if v["version_type"] == ch:
                return v, f"{slug}: no {channel} build for this version, using {ch} {v['version_number']}"
    raise AssertionError("unreachable")


def environment(side: str) -> str:
    return {"required": "required", "optional": "optional"}.get(side, "unsupported")


def make_record(project: dict, version: dict) -> dict:
    files = version["files"]
    file = next((f for f in files if f.get("primary")), files[0])
    return {
        "slug": project["slug"],
        "title": project["title"],
        "project_id": project["id"],
        "version_id": version["id"],
        "version": version["version_number"],
        "channel": version["version_type"],
        "published": version["date_published"][:10],
        "file": file["filename"],
        "url": file["url"],
        "size": file["size"],
        "sha1": file["hashes"]["sha1"],
        "sha512": file["hashes"]["sha512"],
        # A client pack: every mod is needed on the client, the server side is informational.
        "env": {"client": "required", "server": environment(project["server_side"])},
        "requires": sorted(
            d["project_id"]
            for d in version["dependencies"]
            if d["dependency_type"] == "required" and d.get("project_id")
        ),
        "incompatible": sorted(
            d["project_id"]
            for d in version["dependencies"]
            if d["dependency_type"] == "incompatible" and d.get("project_id")
        ),
    }


def cmd_update(only: list[str]):
    pack = load_pack()
    mc = pack["minecraft"]["version"]
    loader_name = pack["loader"]["name"]
    listed = load_mod_list()
    listed_by_slug = {m["slug"]: m for m in listed}
    old = load_lock() or {}
    old_by_id = {m["project_id"]: m for m in old.get("mods", [])}

    same_target = old.get("minecraft") == mc and old.get("loader", {}).get("name") == loader_name
    if only and not same_target:
        fail("Minecraft version or loader changed since the last lock; run a full `update` first")
    unknown = [s for s in only if s not in listed_by_slug and s not in {m["slug"] for m in old.get("mods", [])}]
    if unknown:
        fail(f"not in mods.toml or the lock file: {', '.join(unknown)}")

    loader_version = pack["loader"]["version"]
    if loader_version == "latest":
        if only and old.get("loader"):
            loader_version = old["loader"]["version"]
        else:
            loader_version = latest_fabric_loader(mc)

    # Look up every listed project in one request (the endpoint accepts slugs or ids).
    projects = {}
    for p in modrinth("/projects", ids=[m["slug"] for m in listed]) or []:
        projects[p["slug"]] = p
        projects[p["id"]] = p
    missing = [m["slug"] for m in listed if m["slug"] not in projects]
    if missing:
        fail(f"not found on Modrinth: {', '.join(missing)}")

    resolved: dict[str, dict] = {}  # project_id -> record
    warnings: list[str] = []
    queue: list[tuple[str, dict]] = [(projects[m["slug"]]["id"], m) for m in listed]

    while queue:
        project_id, entry = queue.pop(0)
        if project_id in resolved:
            continue
        project = projects.get(project_id) or modrinth(f"/project/{project_id}")
        if project is None:
            fail(f"dependency {project_id} no longer exists on Modrinth")
        projects[project_id] = project

        keep = only and project["slug"] not in only and project_id in old_by_id
        if keep and not entry.get("pin"):
            record = old_by_id[project_id]
        else:
            versions = modrinth(
                f"/project/{project_id}/version", loaders=[loader_name], game_versions=[mc]
            )
            if not versions:
                fail(f"{project['slug']} has no {loader_name} build for Minecraft {mc}")
            version, warning = pick_version(project, versions, entry)
            if warning:
                warnings.append(warning)
            record = make_record(project, version)

        resolved[project_id] = record
        for dep in record["requires"]:
            if dep not in resolved:
                queue.append((dep, {}))

    # Declared incompatibilities between anything in the pack are fatal.
    for rec in resolved.values():
        for bad in rec["incompatible"]:
            if bad in resolved:
                fail(f"{rec['slug']} declares itself incompatible with {resolved[bad]['slug']}")

    # Annotate: listed mods keep their category; libraries record who pulled them in.
    for rec in resolved.values():
        if entry := listed_by_slug.get(rec["slug"]):
            rec["category"] = entry.get("category", "Other")
            rec["why"] = entry.get("why", "")
            rec.pop("required_by", None)
        else:
            rec.pop("category", None)
            rec.pop("why", None)
            rec["required_by"] = sorted(
                other["slug"] for other in resolved.values() if rec["project_id"] in other["requires"]
            )

    order = {m["slug"]: i for i, m in enumerate(listed)}
    mods = sorted(
        resolved.values(),
        key=lambda r: (r["slug"] not in order, order.get(r["slug"], 0), r["slug"]),
    )
    lock = {
        "minecraft": mc,
        "loader": {"name": loader_name, "version": loader_version},
        "mods": mods,
    }
    LOCK_FILE.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print_diff(old, lock)
    for w in warnings:
        print(f"note: {w}")
    write_readme_table(lock)
    libs = sum(1 for m in mods if "required_by" in m)
    print(f"\nLocked {len(mods)} mods ({len(mods) - libs} listed + {libs} libraries) "
          f"for Minecraft {mc}, Fabric Loader {loader_version}.")


def print_diff(old: dict, new: dict):
    before = {m["slug"]: m["version"] for m in old.get("mods", [])}
    after = {m["slug"]: m["version"] for m in new["mods"]}
    lines = []
    if old.get("loader") and old["loader"] != new["loader"]:
        lines.append(f"  ~ fabric-loader  {old['loader']['version']} -> {new['loader']['version']}")
    for slug in sorted(before.keys() | after.keys()):
        if slug not in before:
            lines.append(f"  + {slug}  {after[slug]}")
        elif slug not in after:
            lines.append(f"  - {slug}  {before[slug]}")
        elif before[slug] != after[slug]:
            lines.append(f"  ~ {slug}  {before[slug]} -> {after[slug]}")
    print("Changes:\n" + "\n".join(lines) if lines else "Everything is already up to date.")


def write_readme_table(lock: dict):
    if not README_FILE.exists():
        return
    text = README_FILE.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return

    out = [f"_Minecraft **{lock['minecraft']}**, Fabric Loader **{lock['loader']['version']}**._"]
    category = None
    for m in lock["mods"]:
        if "category" not in m:
            continue
        if m["category"] != category:
            category = m["category"]
            out += ["", f"#### {category}", "", "| Mod | Version | What it does |", "| --- | --- | --- |"]
        tag = "" if m["channel"] == "release" else f" _({m['channel']})_"
        version = m["version"].replace("|", "\\|")
        out.append(f"| [{m['title']}](https://modrinth.com/mod/{m['slug']}) | `{version}`{tag} | {m['why']} |")
    libs = [m for m in lock["mods"] if "required_by" in m]
    if libs:
        names = ", ".join(f"[{m['title']}](https://modrinth.com/mod/{m['slug']})" for m in libs)
        out += ["", f"Plus {len(libs)} libraries pulled in automatically: {names}."]

    new_block = README_START + "\n" + "\n".join(out).strip() + "\n" + README_END
    text = re.sub(re.escape(README_START) + r".*?" + re.escape(README_END), lambda _: new_block, text, flags=re.S)
    README_FILE.write_text(text, encoding="utf-8")


# ─── build ────────────────────────────────────────────────────────────────────


def cmd_build(version_override: str | None):
    pack = load_pack()
    lock = load_lock()
    if lock is None:
        fail("no modpack.lock.json yet; run `python tools/modpack.py update` first")

    mc = pack["minecraft"]["version"]
    if lock["minecraft"] != mc or lock["loader"]["name"] != pack["loader"]["name"]:
        fail("pack.toml changed Minecraft version/loader since the last lock; run `update`")
    locked = {m["slug"] for m in lock["mods"]}
    stale = [m["slug"] for m in load_mod_list() if m["slug"] not in locked]
    if stale:
        fail(f"mods.toml has mods that aren't locked yet ({', '.join(stale)}); run `update`")

    info = pack["pack"]
    version = version_override or info["version"]
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": version,
        "name": info["name"],
        "summary": info.get("summary", ""),
        "files": [
            {
                "path": f"mods/{m['file']}",
                "hashes": {"sha1": m["sha1"], "sha512": m["sha512"]},
                "env": m["env"],
                "downloads": [m["url"]],
                "fileSize": m["size"],
            }
            for m in lock["mods"]
        ],
        "dependencies": {"minecraft": mc, "fabric-loader": lock["loader"]["version"]},
    }

    DIST_DIR.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", info["name"]).strip("-")
    out = DIST_DIR / f"{safe_name}-{version}.mrpack"
    overrides = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("modrinth.index.json", json.dumps(index, indent=2, ensure_ascii=False))
        if OVERRIDES_DIR.is_dir():
            for path in sorted(OVERRIDES_DIR.rglob("*")):
                if path.is_file() and path.name != ".gitkeep":
                    z.write(path, "overrides/" + path.relative_to(OVERRIDES_DIR).as_posix())
                    overrides += 1

    size_kb = out.stat().st_size / 1024
    print(f"Built {out.relative_to(ROOT)} ({len(index['files'])} mods, {overrides} override files, {size_kb:.1f} KB)")
    print("Import it in Modrinth App (+ > Import) or Prism Launcher (Add Instance > Import).")


# ─── cli ──────────────────────────────────────────────────────────────────────


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_update = sub.add_parser("update", help="resolve mods.toml and write modpack.lock.json")
    p_update.add_argument("slugs", nargs="*", help="only update these mods (default: everything)")
    p_build = sub.add_parser("build", help="write dist/<name>-<version>.mrpack")
    p_build.add_argument("--version", help="override the pack version from pack.toml (used by CI)")
    args = parser.parse_args()

    if args.command == "update":
        cmd_update(args.slugs)
    else:
        cmd_build(args.version)


if __name__ == "__main__":
    main()
