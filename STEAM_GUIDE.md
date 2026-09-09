# Valheim Character Editor

Removes the cheater flag from your own Valheim character and lets you edit
skills, stats, and the "cheated" marks on inventory items. Works directly on
the .fch save, keeps a backup, fixes the checksum.

Use it on your own single-player characters. Make a manual copy of anything
important first.

## Download

Grab ValheimCharacterEditor.exe from the Releases page. It's a single portable
file, no installer. Windows will warn the exe is unsigned — click More info →
Run anyway.

## Where the character files are

    %USERPROFILE%\AppData\LocalLow\IronGate\Valheim\characters

Each character is one .fch. Paste that path into File Explorer to jump there.

## How to use it

1. Open a character file: drag it onto the window, or use "Open .fch…".
2. The Character tab shows name, ID, seed, and the cheater flag.
3. Untick the flag to remove it. Tick "Clear cheater marks on inventory items"
   if spawned items are flagged.
4. Stats and Skills tabs edit the rest.
5. Save. A backup (.bak) is written next to the file.

Close the game before you edit, or it overwrites your changes on exit.

## Why achievements stay locked

The game disables achievements when any of these is true:

    m_usedCheats  OR  the world has cheated modifiers  OR
    a cheated item is in the inventory  OR  the game is modded

This tool handles the character: the flag, and cheated marks on inventory
items. A cheated world or mods still lock achievements and this tool can't fix
that.

Heads up: the game re-marks an item whose total damage is over 10000 when it
loads the character, so clearing those won't stick.

## Notes

- If skills look reset, check the Skills tab first — the levels are often still
  in the file.
- "No embedded player data" means the character never entered a world.
- "Version of profile … only 46 supported" means the save is from an older game
  version. Launch the game once and let it re-save.

MIT license.
