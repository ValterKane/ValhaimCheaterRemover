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
- Inventory — the 8×4 backpack grid. Add or replace an item by name or ID
  (added items carry no cheater mark), unmark one cheater-flagged item or
  clear every mark at once.
- World — combat, death penalty, resources, raids and portals

Every save keeps a backup (.bak) and fixes the SHA-512 checksum so the game
still opens the file.

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

## Achievements

The game blocks achievements if any of these is true:

    m_usedCheats  OR  the world has cheated modifiers  OR
    a cheated item is in the inventory  OR  the game is modded

What this tool can and can't do about each:

- m_usedCheats — untick the flag.
- Cheated items — shown in red on the Inventory tab. Use **Unmark selected**
  for one item or **Clear all cheater marks** for the whole backpack. Only
  items in the inventory when you save are covered; items in chests or dropped
  in the world keep their mark, and picking one up later brings the cheat state
  back.
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

## Build from source

    python app_gui.py

The only dependency is tkinter — on Debian/Ubuntu install python3-tk first
(most other distros ship it or an equivalent package).

    pyinstaller --onefile --windowed --name ValheimCharacterEditor app_gui.py

## License

MIT.
