# Valheim Character Editor

Edits your own Valheim character saves (.fch). Remove the cheater flag, tweak
skills and stats, clear the "cheated" mark from inventory items.

Windows: portable single exe — grab it from the Releases page. It's plain
Python + tkinter under the hood, so Linux and Steam Deck can run it from source
(see Build from source below).

## What it edits

- Cheater flag (m_usedCheats)
- Skills — level and experience, add or remove
- Stats — health, stamina, eitr, time since death, guardian power cooldown
- Inventory — clears the cheated marks the game puts on spawned items

Every save keeps a backup (.bak) and fixes the SHA-512 checksum so the game
still opens the file.

## Character files

Windows:

    %USERPROFILE%\AppData\LocalLow\IronGate\Valheim\characters

Linux:

    ~/.config/unity3d/IronGate/Valheim/characters

One .fch per character. Close the game before editing — it rewrites the save on
exit and will throw away your changes.

## Achievements

The game blocks achievements if any of these is true:

    m_usedCheats  OR  the world has cheated modifiers  OR
    a cheated item is in the inventory  OR  the game is modded

What this tool can and can't do about each:

- m_usedCheats — untick the flag.
- Cheated items — clears the mark, but only on items in the character's
  inventory at the time you save. Items in chests or dropped in the world keep
  their mark; picking one up later brings the cheat state back.
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
