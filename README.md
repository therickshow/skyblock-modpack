# SkyBlock QoL

A Fabric modpack for **Hypixel SkyBlock** on modern Minecraft: vanilla quality-of-life and
performance mods, plus the big SkyBlock mods for dungeons, fishing, farming, the Bazaar and more.

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
2. Optional: run `python tools/configure.py` from this repo to apply the preset in
   [`settings.toml`](settings.toml) (see [Preset settings](#preset-settings)).

- **Settings:** every mod has a config screen under **Mods** (Mod Menu) on the title/pause screen.
  Shortcuts: SkyHanni `/sh`, Skyblocker `/skyblocker config`, Odin **Right Shift**, Feesh `/feesh`,
  BtrBz `/btrbz`, MarketGuard `/mg`, profile viewer `/pv <player>`.
- **Mod Menu has no key by default.** The preset puts it on **Right Ctrl**.
- **Every mod with settings has a button in Mod Menu.** Most mods add their own. The pack's
  small companion mod ([`companion-mod/`](companion-mod/)) adds the missing ones: Feesh,
  SkyBlock Profile Viewer, Auth Me, Sodium / Sodium Extra / Reese's (all open Sodium's video
  settings), and Catharsis (opens Resource Packs, where its per-pack options live). Mods
  without a button either have nothing to set (libraries, Controlling) or keep their
  settings only in a file under `config/` (Lithium, FerriteCore, ImmediatelyFast, Crash
  Assistant, JEI, MarketGuard, Enhanced Storage).
- **Secret Routes only *checks* for updates.** Its auto-download is off by default. Leave it
  off: the pack pins every version, and an extra jar in the mods folder causes a
  duplicate-mod crash.

## Preset settings

`tools/configure.py` applies [`settings.toml`](settings.toml) to an installed instance. Close the
game first. Every run backs up the files it changes to `<instance>/settings-backups/`, and
`--dry-run` shows what it would do without writing anything.

| Area | What the preset does |
| --- | --- |
| Keys | Mod Menu → **Right Ctrl**. **C** = zoom. Clashes fixed: **G** = fullbright, **H** = night vision, **M** = warp menu; BtrBz Bazaar HUD → **End**, Skyblocker tab-HUD reset → **Home**, vanilla Quick Actions → **Right Alt** |
| SkyHanni | Turns on every feature switch in Garden, Fishing, Mining, Slayer and Diana, the same as its own `/shdefaultoptions` "turn all on". Features only run on their own island or activity |
| Dungeons | Skyblocker does map, score, secret waypoints and puzzle/terminal solvers (already on by default). Odin adds end-game helpers only: M7 dragons + relics, terracotta, tick timers, spirit bear, blood camp, blessings, secret feedback, invincibility timer, and Kuudra (info, supplies, build, pearls, fresh tools). Odin's duplicate solvers stay off, and so do Mimic and Pre-Spot Alert, which post to party chat for you |

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
| [Skyblocker • Hypixel Skyblock](https://modrinth.com/mod/skyblocker-liap) | `v6.10.4+26.2` | All-rounder: dungeon map & score, secret waypoints, puzzle + terminal solvers, Croesus profit, item prices |
| [SkyHanni for Hypixel SkyBlock](https://modrinth.com/mod/skyhanni) | `9.0.0` | Garden/farming overlays (crop milestones, visitor helper, money/hr, pests), plus slayer, mining, fishing, Diana and Rift features. `/sh` |
| [SkyBlock Profile Viewer](https://modrinth.com/mod/skyblock-profile-viewer) | `1.9.2` | `/pv <player>`: full profile viewer, handy for party-finder checks |
| [Skyblock Enhanced Storage](https://modrinth.com/mod/skyblock-enhanced-storage) | `v1.2.2-mc26.2` | All Ender Chest + Backpack pages in one searchable screen |
| [Modern Warp Menu](https://modrinth.com/mod/modern-warp-menu) | `0.2.4+26.2` | Clickable island map warp menu (Fancy Warp Menu port) |
| [Catharsis](https://modrinth.com/mod/catharsis) | `1.0.0-beta.22` _(beta)_ | Lets SkyBlock texture packs retexture items (needed by modern Furfsky / Hypixel+ style packs) |
| [ScamScreener for Hypixel SkyBlock](https://modrinth.com/mod/scamscreener) | `2.6.1+26.2` | Flags likely scam messages in chat |

#### Dungeons & Kuudra

| Mod | Version | What it does |
| --- | --- | --- |
| [Odin - Hypixel Skyblock](https://modrinth.com/mod/odin) | `0.3.4` _(beta)_ | End-game dungeons & Kuudra: solvers, teammate/starred-mob highlight, blood camp helpers, custom room waypoints |
| [Secret Routes Mod](https://modrinth.com/mod/secret-routes-mod) | `1.0.0+26.2` | Recorded secret routes for every room with etherwarp, pearl, stonk and superboom waypoints |

#### Fishing

| Mod | Version | What it does |
| --- | --- | --- |
| [Feesh](https://modrinth.com/mod/feesh) | `1.14.0` | Fishing QoL mod (set it up with `/feesh`). SkyHanni adds sea-creature & trophy-fish trackers on top |

#### Bazaar & Auction House

| Mod | Version | What it does |
| --- | --- | --- |
| [BtrBz](https://modrinth.com/mod/btrbz) | `0.12.0-alpha+26.2` _(alpha)_ | Bazaar order tracking, outbid/undercut alerts, price alerts, order safety checks. `/btrbz` |
| [MarketGuard for Hypixel SkyBlock](https://modrinth.com/mod/marketguard) | `1.5.0+26.2` | Blocks AH clicks priced far over/under Lowest BIN (typo protection). `/mg` |

#### Recipes

| Mod | Version | What it does |
| --- | --- | --- |
| [Enhanced SkyRecipes](https://modrinth.com/mod/enhanced-skyrecipes) | `v0.5.12-mc26.2` _(beta)_ | SkyBlock-only recipe browser: 8,000+ items, crafting/forge recipes, mob drops, NPC shops, essence upgrades, reforges. No vanilla recipes cluttering it up like JEI had |

#### Vanilla QoL

| Mod | Version | What it does |
| --- | --- | --- |
| [Mod Menu](https://modrinth.com/mod/modmenu) | `20.0.3` | Mods button with a config screen for everything in the pack |
| [Gamma Utils (Fullbright)](https://modrinth.com/mod/gamma-utils) | `3.1.1+Fabric` | Fullbright: **G** toggles high gamma, **H** toggles client-side night vision |
| [Zoomify (Zoom)](https://modrinth.com/mod/zoomify) | `2.16.3+26.2` | Zoom (hold **C**, scroll to adjust) |
| [Controlling](https://modrinth.com/mod/controlling) | `26.2.4` | Search bar in Controls, which you'll want with this many keybinds |
| [Chat Patches](https://modrinth.com/mod/chatpatches) | `8.0-alpha.11+26.2-fabric` _(alpha)_ | Longer chat history kept between sessions, timestamps, duplicate-message counter |
| [Tooltip Scroll](https://modrinth.com/mod/tooltip-scroll) | `1.5.1+26.2` | Scroll long SkyBlock tooltips that run off the screen |
| [Auth Me](https://modrinth.com/mod/auth-me) | `v9.3.0+26.2` | Re-login from the disconnect screen without restarting the game |
| [No Chat Reports](https://modrinth.com/mod/no-chat-reports) | `Fabric-26.2-v2.20.2` | Strips chat signing so messages can't be reported to Mojang |
| [ResourcePackCached](https://modrinth.com/mod/resourcepackcached) | `1.2.7` | Keeps server resource packs loaded so rejoining Hypixel is faster |
| [Crash Assistant](https://modrinth.com/mod/crash-assistant) | `1.11.14` | If the game crashes, shows which mod caused it instead of a wall of log |

#### Performance

| Mod | Version | What it does |
| --- | --- | --- |
| [Sodium](https://modrinth.com/mod/sodium) | `mc26.2-0.9.2-fabric` | Modern renderer, huge FPS boost |
| [Sodium Extra](https://modrinth.com/mod/sodium-extra) | `mc26.2-0.9.4+fabric` | Extra Sodium toggles (particles, animations, fog, FPS counter) |
| [Reese's Sodium Options](https://modrinth.com/mod/reeses-sodium-options) | `mc26.2-2.2.4+fabric` | Cleaner tabbed video settings screen |
| [Iris Shaders](https://modrinth.com/mod/iris) | `1.11.4+26.2-fabric` | Shader support (off by default, costs nothing unless you pick a shaderpack) |
| [Lithium](https://modrinth.com/mod/lithium) | `mc26.2-0.25.3-fabric` | Game-logic optimizations |
| [FerriteCore](https://modrinth.com/mod/ferrite-core) | `9.0.0-fabric` | Lower memory usage |
| [ModernFix-mVUS](https://modrinth.com/mod/modernfix-mvus) | `5.27.19-build.2` | Faster launch, lower memory, bug fixes (ModernFix fork that tracks new versions) |
| [Entity Culling](https://modrinth.com/mod/entityculling) | `1.11.2` | Skips rendering entities/block entities you can't see (big win in crowded hubs) |
| [More Culling](https://modrinth.com/mod/moreculling) | `1.8.1` | Additional block culling |
| [ImmediatelyFast](https://modrinth.com/mod/immediatelyfast) | `1.16.5+26.2-fabric` | Faster HUD, text and GUI rendering (lots of SkyBlock overlays) |
| [Dynamic FPS](https://modrinth.com/mod/dynamic-fps) | `3.11.9` | Lowers FPS when the game is in the background or idle (AFK garden, alt-tab) |

Plus 10 libraries pulled in automatically: [Cloth Config API](https://modrinth.com/mod/cloth-config), [Fabric API](https://modrinth.com/mod/fabric-api), [Fabric Language Kotlin](https://modrinth.com/mod/fabric-language-kotlin), [Hypixel Mod API](https://modrinth.com/mod/hypixel-mod-api), [oωo (owo-lib)](https://modrinth.com/mod/owo-lib), [Text Placeholder API](https://modrinth.com/mod/placeholder-api), [Reliable Recipe Viewer](https://modrinth.com/mod/rrv), [Searchables](https://modrinth.com/mod/searchables), [UI Lib](https://modrinth.com/mod/ui-lib), [YetAnotherConfigLib (YACL)](https://modrinth.com/mod/yacl).
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
| [`tests/`](tests/) | Tests for both scripts (no internet or game needed) plus checks on the real lock and settings files |

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
`modrinth.com/mod/<slug>` URL), run **Update all mods**, commit `mods.toml` +
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

Unrelated to the pack itself. The [mayor snapshot workflow](.github/workflows/skyblock-mayor.yml)
fetches Hypixel's public election API every 3 hours and commits the result here. A scheduled
Claude Code cloud routine (see [claude.ai/code/routines](https://claude.ai/code/routines)) reads
it to keep the "Road to 500 MP" SkyBlock artifact's mayor info current, since that routine's
sandbox can't reach `api.hypixel.net` directly. Safe to ignore.
