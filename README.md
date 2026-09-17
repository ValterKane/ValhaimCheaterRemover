# Valheim Character Editor

Edits your own Valheim character saves (.fch) and world settings. Remove the
cheater flag, tweak skills and stats, edit the backpack, adjust world modifiers.

Windows: portable single exe — grab it from the Releases page. It's plain
Python + tkinter under the hood, so Linux and Steam Deck can run it from source
(see Build from source below).

## What it edits

- Cheater flag (m_usedCheats)
- Skills — level and experience, add or remove
- Stats — health, stamina, eitr, time since death, guardian power cooldown
- Inventory — the 8-column backpack grid, 4–6 rows (32–48 slots). Row count
  matches in-game upgrades (Wider / Deep Pockets). Add or replace an item by
  name or ID (added items carry no cheater mark), unmark one cheater-flagged
  item or clear every mark at once.
- World — combat, death penalty, resources, raids and portals; clear cheater
  marks from all items in the world (_main.N.db2/.db and .chunk files)

Character saves (`.fch`) get a `.bak` backup and an updated SHA-512 checksum so
the game still accepts the file. World files (`.fwl2`, `.db2`, `.chunk`) get a
`.bak` before each write; they have no character-style checksum.

## Character files

Windows:

    %USERPROFILE%\AppData\LocalLow\IronGate\Valheim\characters

Linux:

    ~/.config/unity3d/IronGate/Valheim/characters

One .fch per character. Close the game before editing — it rewrites the save on
exit and will throw away your changes.

Some setups keep a second copy under `characters_local` (worlds under
`worlds_local`). The **Local files** button scans both the normal and the
`_local` folders and lists what it finds.

## World files

Windows:

    %USERPROFILE%\AppData\LocalLow\IronGate\Valheim\worlds
    %USERPROFILE%\AppData\LocalLow\IronGate\Valheim\worlds_local

Linux:

    ~/.config/unity3d/IronGate/Valheim/worlds
    ~/.config/unity3d/IronGate/Valheim/worlds_local

Each world is a **folder** (not a single file). Valheim 1.0 stores several
files inside it:

| File | Role |
|------|------|
| `_main.N.fwl2` | World metadata and modifier keys (combat, resources, …) |
| `_main.N.db2` | Global world state (legacy saves used `_main.N.db`) |
| `_main.N.chunks` | Small index; actual terrain lives in `*.chunk` |
| `*.chunk` | Per-area data — chests, dropped items, carts, tombstones, etc. |

`N` is the save slot number (0, 1, 2, …). The editor picks the highest
`_main.N.fwl2` in the folder when you open it.

**Open world…** asks for the world **folder** (e.g. `infiniteworld`), not an
individual file. After loading, the World tab shows the paired `_main.N.db2`
(or `.db`) and how many `.chunk` files were found.

Close the game before editing world files — same rule as for `.fch`.

### World tab

- **Sliders** — change combat, death penalty, resources, raids and portals.
  Only keys the in-game Server Options screen can write are touched; anything
  else in the file is left as-is.
- **Clear all cheater marks in world** — scans `_main.N.db2` / legacy `.db` and
  every `*.chunk` in that folder, finds items with the cheater flag set, and
  clears the flag without deleting the item. Character backpack slots are **not**
  included — use the Inventory tab on the `.fch` file for those.

The scan reports how many flagged items and places it found before you confirm.
Each modified file gets its own `.bak` backup.

## Inventory size (Valheim 1.0)

The backpack is 8 columns wide. Row count comes from merchant upgrades:

| Upgrade | Rows | Slots |
|---------|------|-------|
| Default | 4 | 32 |
| Wider inventory | 5 | 40 |
| Deep Pockets | 6 | 48 |

The editor reads `invrows` from the save and draws the matching grid. If you
change row count manually, make sure it matches what the character actually has
in-game.

## Achievements

The game blocks achievements if any of these is true:

    m_usedCheats  OR  the world has cheated modifiers  OR
    a cheated item is in the inventory  OR  the game is modded

What this tool can and can't do about each:

- m_usedCheats — untick the flag.
- Cheated items — shown in red on the Inventory tab. Use **Unmark selected**
  or **Clear all cheater marks** for the character backpack (.fch). On the
  **World** tab, **Clear all cheater marks in world** scans the world folder
  (`_main.N.db2` or legacy `.db`, plus `.chunk` files) and unmarks items in
  chests, on the ground, in carts, tombstones, etc. Close the game before
  editing.
- World modifiers (Hammer Mode, No Build Cost) — not a stored flag. The game
  checks them live, so there's nothing to fix: toggle them off before going for
  achievements.
- Modded game — this tool can't touch that. AchievementEnabler and Unshamed
  (Thunderstore / Nexus) patch just that one check and leave the other three
  alone.

One catch: the game re-marks an item whose total damage is over 10000 when it
loads the character. Clearing those won't stick.

Old pre-1.0 worlds: console-spawned items from before 1.0 don't seem to get
retroactively tagged. A clean character walking into an old cheated world and
picking up old spawned items hasn't tripped the flag in testing.

### Suggested cleanup order

1. Close Valheim.
2. Open the `.fch` — clear **m_usedCheats** and cheater marks on the Inventory
   tab.
3. Open the world **folder** — run **Clear all cheater marks in world** if
   anything remains in chests or on the ground.
4. Turn off live console modifiers (Hammer Mode, etc.) before your next session.

## Build from source

    python app_gui.py

The only dependency is tkinter — on Debian/Ubuntu install python3-tk first
(most other distros ship it or an equivalent package).

    pyinstaller --onefile --windowed --name ValheimCharacterEditor app_gui.py

### Tests

No extra packages — plain Python:

    python test_inventory.py
    python test_world_db.py
    python test_world_editor.py
    python test_items.py

`test_world_db.py` covers cheater-flag scanning and patching inside fake
`.db` / inventory blobs, plus pairing `_main.N.fwl2` with `_main.N.db2`.

## License

MIT.
