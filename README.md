# SkyBlock QoL

A Fabric modpack for **Hypixel SkyBlock** on modern Minecraft: the big SkyBlock mods for
dungeons, slayers, mining, farming, fishing and events, performance mods, a clean resource pack,
and only the vanilla tweaks SkyBlock actually needs.

## Install

1. Download the latest `.mrpack` from [Releases](../../releases/latest).
2. Import it:
   - **Modrinth App:** `+` (Create instance) → **Import** → pick the file.
   - **Prism Launcher:** **Add Instance** → **Import** → pick the file.
3. Give the instance **at least 4 GB of RAM** (6 GB if you add a SkyBlock texture pack).
   Minecraft 26.x runs on Java 25. Both launchers download it automatically.
4. Join `mc.hypixel.net`.

## First launch

1. Start the game once and close it again. Mods only create their config files on launch.
2. Run `python tools/configure.py` from this repo to apply the preset in
   [`settings.toml`](settings.toml) (see [Preset settings](#preset-settings)). Without it the
   SkyBlock mods show a lot of the same things twice, and the resource packs stay off.

- **Settings:** every mod has a config screen under **Mods** (Mod Menu) on the title/pause screen.
  Shortcuts: SkyHanni `/sh`, Skyblocker `/skyblocker config`, Odin **Right Shift**, profile
  viewer `/pv <player>` (Skyblocker's).
- **Mod Menu has no key by default.** The preset puts it on **Right Ctrl**.
- **Every mod with settings has a button in Mod Menu.** Most mods add their own. The pack's
  small companion mod ([`companion-mod/`](companion-mod/)) adds the missing ones: Sodium /
  Sodium Extra / Reese's (all open Sodium's video settings) and Catharsis (opens Resource
  Packs, where its per-pack options live). Mods without a button either have nothing to set
  (libraries) or keep their settings only in a file under `config/` (Lithium, FerriteCore,
  ImmediatelyFast, Enhanced Storage).
- **"The game crashed" when you quit was a false alarm.** It came from Secret Routes, whose
  shutdown step waits on a web request; the launcher's watchdog saw the hang and wrote a crash
  report. Secret Routes is out of the pack (Skyblocker already has secret waypoints).

## Preset settings

`tools/configure.py` applies [`settings.toml`](settings.toml) to an installed instance. Close the
game first. Every run backs up the files it changes to `<instance>/settings-backups/`, and
`--dry-run` shows what it would do without writing anything.

| Area | What the preset does |
| --- | --- |
| Keys | Mod Menu → **Right Ctrl**. Clashes fixed: **G** = fullbright, **H** = night vision, **M** = warp menu; Skyblocker tab-HUD reset → **Home**, vanilla Quick Actions → **Right Alt** |
| One source each | Each kind of information comes from one mod only (table below). The other mod's copy is switched off, so nothing pops up or prints twice |
| SkyHanni | Garden, Fishing, Mining, Slayer and Diana switches go back to SkyHanni's own defaults (read from the mod jar), then the parts Skyblocker covers are switched off. SkyBlock XP chat lines come from Skyblocker only |
| Skyblocker | Its Garden, fishing, Diana, Rift, Hoppity and Trevor helpers are off (SkyHanni's job), and so are its item list (Enhanced SkyRecipes' job), chat tips, and Auction House / Bazaar prices and helpers |
| Titles | Pop-up titles from Skyblocker and SkyHanni sit at the top centre of the screen instead of the middle |
| Dungeons | Skyblocker does map, score, secret waypoints and puzzle/terminal solvers. Odin adds end-game helpers only: M7 dragons + relics, terracotta, tick timers, spirit bear, blood camp, blessings, invincibility timer, and Kuudra HP + Fresh Tools. Odin's copies of Skyblocker's solvers, secret marks and Kuudra waypoints stay off, and so do Mimic and Pre-Spot Alert, which post to party chat for you |
| Resource packs | Turns on Clean PvP with Skyblock Dark UI on top. Clean PvP still labels itself with an older pack format, so it's also marked as accepted (the same as clicking "Yes" on the game's warning) |

Who shows what:

| Mod | Owns |
| --- | --- |
| Skyblocker | Dungeons, mining, slayers, Kuudra, Galatea, tab HUD and bars, XP chat lines, item tooltips, `/pv` |
| SkyHanni | Garden and farming, fishing, Diana, the Rift, Hoppity, Trevor, Crimson Isle reputation |
| Odin | Dungeon boss timers and the two Kuudra extras above |
| Enhanced SkyRecipes | Recipes and the item list |

## Hypixel rules

Nothing here is a macro. There are no auto-farmers, auto-fishers or auto-clickers, only the
community-standard client-side QoL mods. Hypixel's official line is still that any modification
is used at your own risk, so **don't add** macros, "cheat" builds of Odin, freecam, x-ray or ESP
mods. Mouse Tweaks is also left out on purpose: SkyBlock menus (Bazaar, AH, NPC shops) are chest
screens, so its scroll-to-move feature sends real clicks and can buy or sell things by accident.

## What's inside

<!-- mods:start -->
_Minecraft **26.2**, Fabric Loader **0.19.5**._

#### SkyBlock: core

| Mod | Version | What it does |
| --- | --- | --- |
| [Skyblocker • Hypixel Skyblock](https://modrinth.com/mod/skyblocker-liap) | `v6.10.4+26.2` | Dungeons (map, score, secret waypoints, puzzle + terminal solvers, Croesus), mining, slayers, Kuudra, Galatea, tab HUD, `/pv` profile viewer |
| [SkyHanni for Hypixel SkyBlock](https://modrinth.com/mod/skyhanni) | `9.0.0` | Garden and farming (visitors, pests, crop milestones), fishing, Diana, the Rift, Hoppity, Trevor. `/sh` |
| [Skyblock Enhanced Storage](https://modrinth.com/mod/skyblock-enhanced-storage) | `v1.2.2-mc26.2` | All Ender Chest + Backpack pages in one searchable screen |
| [Modern Warp Menu](https://modrinth.com/mod/modern-warp-menu) | `0.2.4+26.2` | Clickable island map warp menu (Fancy Warp Menu port) |
| [Catharsis](https://modrinth.com/mod/catharsis) | `1.0.0-beta.22` _(beta)_ | Lets SkyBlock texture packs retexture items (needed by modern Furfsky / Hypixel+ style packs) |
| [ScamScreener for Hypixel SkyBlock](https://modrinth.com/mod/scamscreener) | `2.6.1+26.2` | Flags likely scam messages in chat |

#### Dungeons & Kuudra

| Mod | Version | What it does |
| --- | --- | --- |
| [Odin - Hypixel Skyblock](https://modrinth.com/mod/odin) | `0.3.4` _(beta)_ | Dungeon boss timers (F6/F7), blood camp and blessing display, Kuudra HP and Fresh Tools timer. Only the parts Skyblocker doesn't do are switched on |

#### Recipes

| Mod | Version | What it does |
| --- | --- | --- |
| [Enhanced SkyRecipes](https://modrinth.com/mod/enhanced-skyrecipes) | `v0.5.12-mc26.2` _(beta)_ | SkyBlock-only recipe browser: 8,000+ items, crafting/forge recipes, mob drops, NPC shops, essence upgrades, reforges. No vanilla recipes cluttering it up like JEI had |

#### Vanilla QoL

| Mod | Version | What it does |
| --- | --- | --- |
| [Mod Menu](https://modrinth.com/mod/modmenu) | `20.0.3` | Mods button with a config screen for everything in the pack |
| [Gamma Utils (Fullbright)](https://modrinth.com/mod/gamma-utils) | `3.1.1+Fabric` | Fullbright for mining caves and dungeons: **G** toggles high gamma, **H** toggles client-side night vision |
| [Tooltip Scroll](https://modrinth.com/mod/tooltip-scroll) | `1.5.1+26.2` | Scroll long SkyBlock tooltips that run off the screen |

#### Performance

| Mod | Version | What it does |
| --- | --- | --- |
| [Sodium](https://modrinth.com/mod/sodium) | `mc26.2-0.9.2-fabric` | Modern renderer, huge FPS boost |
| [Sodium Extra](https://modrinth.com/mod/sodium-extra) | `mc26.2-0.9.4+fabric` | Extra Sodium toggles (particles, animations, fog, FPS counter) |
| [Reese's Sodium Options](https://modrinth.com/mod/reeses-sodium-options) | `mc26.2-2.2.4+fabric` | Cleaner tabbed video settings screen |
| [Lithium](https://modrinth.com/mod/lithium) | `mc26.2-0.25.3-fabric` | Game-logic optimizations |
| [FerriteCore](https://modrinth.com/mod/ferrite-core) | `9.0.0-fabric` | Lower memory usage |
| [ModernFix-mVUS](https://modrinth.com/mod/modernfix-mvus) | `5.27.19-build.2` | Faster launch, lower memory, bug fixes (ModernFix fork that tracks new versions) |
| [Entity Culling](https://modrinth.com/mod/entityculling) | `1.11.2` | Skips rendering entities/block entities you can't see (big win in crowded hubs) |
| [More Culling](https://modrinth.com/mod/moreculling) | `1.8.1` | Additional block culling |
| [ImmediatelyFast](https://modrinth.com/mod/immediatelyfast) | `1.16.5+26.2-fabric` | Faster HUD, text and GUI rendering (lots of SkyBlock overlays) |
| [Dynamic FPS](https://modrinth.com/mod/dynamic-fps) | `3.11.9` | Lowers FPS when the game is in the background or idle (AFK garden, alt-tab) |

Plus 8 libraries pulled in automatically: [Cloth Config API](https://modrinth.com/mod/cloth-config), [Fabric API](https://modrinth.com/mod/fabric-api), [Fabric Language Kotlin](https://modrinth.com/mod/fabric-language-kotlin), [Hypixel Mod API](https://modrinth.com/mod/hypixel-mod-api), [Text Placeholder API](https://modrinth.com/mod/placeholder-api), [Reliable Recipe Viewer](https://modrinth.com/mod/rrv), [UI Lib](https://modrinth.com/mod/ui-lib), [YetAnotherConfigLib (YACL)](https://modrinth.com/mod/yacl).

#### Resource packs

| Pack | Version | What it does |
| --- | --- | --- |
| [Clean PvP texturepack](https://modrinth.com/resourcepack/clean-pvp-texturepack) | `26.2+` | Clean, minimal default edit (short swords, tidy tools and GUI), in the spirit of the ThirtyVirus pack |
| [Skyblock Dark UI](https://modrinth.com/resourcepack/skyblock-dark-ui) | `1.18` | Dark, clean SkyBlock menus on top |
<!-- mods:end -->

## Working on the pack

Everything is driven by two files you edit by hand plus one generated lock file:

| File | What it is |
| --- | --- |
| [`pack.toml`](pack.toml) | Pack name, version, Minecraft version, loader |
| [`mods.toml`](mods.toml) | The mod list, by Modrinth slug, grouped by category |
| [`modpack.lock.json`](modpack.lock.json) | **Generated.** Exact pinned versions, download URLs and hashes |
| [`overrides/`](overrides/) | Files copied into the instance as-is (configs etc.). Empty for now |
| [`tools/modpack.py`](tools/modpack.py) | The build tool. Python 3.11+, standard library only |
| [`settings.toml`](settings.toml) + [`tools/configure.py`](tools/configure.py) | The settings preset and the script that applies it to an instance |
| [`companion-mod/`](companion-mod/) | Our own small Fabric mod (Java 25) that adds the missing Mod Menu buttons. Built with Gradle and shipped inside the `.mrpack` |
| [`tests/`](tests/) | Tests for the scripts and the companion mod (no internet or game needed) plus checks on the real lock and settings files |

**In VS Code** (Terminal → Run Task…, or `Ctrl+Shift+B` for Build):

| Task | Command |
| --- | --- |
| Update all mods | `python tools/modpack.py update` |
| Update one mod | `python tools/modpack.py update skyhanni` |
| Build companion mod | `companion-mod\gradlew.bat build` (needs JDK 25; the task points `JAVA_HOME` at `%USERPROFILE%\.jdks\jdk-25.0.4.1+1`) |
| Build .mrpack | `python tools/modpack.py build` → `dist/SkyBlock-QoL-<version>.mrpack` (the task builds the companion mod first) |
| Run tests | `python -m unittest discover -s tests -v` |
| Configure instance (dry run) | `python tools/configure.py --dry-run --verbose` |
| Configure instance | `python tools/configure.py` |

**Add or remove a mod:** edit `mods.toml` (the slug is the last part of its
`modrinth.com/mod/<slug>` URL; resource packs go under `[[resourcepack]]`), run **Update all
mods**, commit `mods.toml` +
`modpack.lock.json`. Dependencies are resolved automatically, and `update` refuses to lock mods
that declare each other incompatible. The table above is regenerated on every update.

**Update to a new Minecraft version:** change `minecraft.version` in `pack.toml` and run
**Update all mods**. It fails loudly and names any mod that doesn't have a build for that
version yet.

**Release:** bump `version` in `pack.toml`, commit, then

```bash
git tag v1.1.0 && git push origin main --tags
```

The [Build workflow](.github/workflows/build.yml) runs the tests and builds the `.mrpack` on
every push and pull request, and on a `v*` tag it publishes a GitHub Release with the file
attached.

## data/skyblock-election.json

Unrelated to the pack itself, and **switched off since 2026-10-02**. The
[mayor snapshot workflow](.github/workflows/skyblock-mayor.yml) fetched Hypixel's public
election API every 3 hours and committed the result here, for a Claude Code cloud routine that
kept the SkyBlock accessory page's mayor info current (that routine's sandbox can't reach
`api.hypixel.net` directly). Both the routine and the workflow are disabled; the workflow can
be turned back on under Actions → SkyBlock mayor snapshot → Enable workflow. Safe to ignore.
