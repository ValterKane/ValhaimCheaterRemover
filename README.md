# Valheim Character Editor

Edits your own Valheim character saves (.fch). Remove the cheater flag, tweak
skills and stats, clear the "cheated" mark from inventory items.

Windows only. Portable single exe — download it from the Releases page.

## What it edits

- Cheater flag (m_usedCheats)
- Skills — level and experience, add or remove
- Stats — health, stamina, eitr, time since death, guardian power cooldown
- Inventory — clears the cheated marks the game puts on spawned items

Every save keeps a backup (.bak) and fixes the SHA-512 checksum so the game
still opens the file.

## Character files

    %USERPROFILE%\AppData\LocalLow\IronGate\Valheim\characters

One .fch per character. Close the game before editing — it rewrites the save on
exit and will throw away your changes.

## Achievements

The game blocks achievements if any of these is true:

    m_usedCheats  OR  the world has cheated modifiers  OR
    a cheated item is in the inventory  OR  the game is modded

This tool fixes the character side: the flag, and cheated marks on items in the
inventory. It can't clean a cheated world or un-mod the game.

One catch: the game re-marks an item whose total damage is over 10000 when it
loads the character. Clearing those won't stick.

## Build from source

    python app_gui.py

    pyinstaller --onefile --windowed --name ValheimCharacterEditor app_gui.py

## License

MIT.
