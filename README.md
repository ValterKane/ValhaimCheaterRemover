# Valheim Character Editor

A small Windows tool to edit your own Valheim character save (`.fch`):

- **Remove the Cheater flag** (`m_usedCheats`) — re-enables achievements for a
  character that was marked by using console commands (`devcommands`).
- **Edit skills** — level (0–100) and experience, add or remove skills.
- **Edit base stats** — health, stamina, eitr, time since death, guardian power
  cooldown.
- Works directly on the save file, **keeps a backup** (`.bak`) and **recomputes
  the SHA-512 checksum**, so the game loads the file normally.

![Status](https://img.shields.io/badge/platform-Windows-informational)

## Download

Get the latest **`ValheimCharacterEditor.exe`** from the
[Releases](../../releases) page — a single portable file, no installation needed.

Windows SmartScreen will warn that the exe is unsigned: click
**More info → Run anyway**.

## Where are the character files?

```
%USERPROFILE%\AppData\LocalLow\IronGate\Valheim\characters
```

Each character is a `.fch` file. Drag & drop it onto the app window, or use
**Open .fch…**.

## How to use

1. Open the app and load your character file.
2. **Characters** tab — untick the **Cheater** flag if you want to remove it.
3. **Characteristics** tab — edit stats (empty fields stay unchanged).
4. **Skills** tab — adjust level/experience, add or remove skills.
5. Click **Save** — a backup (`<name>.fch.bak`) is created automatically.

> Make sure the game is **closed** while editing, or it may overwrite your
> changes when you quit.

## Achievements still disabled?

The game blocks achievements when **any** of these is true:

```
m_usedCheats  OR  the world has cheated modifiers  OR
a cheated/spawned item is in the inventory  OR  the game is modded (BepInEx)
```

This tool clears the *character* flag. A cheated world, cheated inventory items
or mods will keep achievements disabled regardless — this tool cannot fix those.

## Building from source

Requires Python 3.

```sh
# run from source
python app_gui.py

# build the exe
pip install pyinstaller
pyinstaller --onefile --windowed --name ValheimCharacterEditor app_gui.py
```

## Disclaimer

Use it on your **own single-player characters** (or private servers where
everyone agrees). Editing saves is at your own risk. The tool only edits the
character `.fch` file and never touches world files.

## License

MIT — see [LICENSE](LICENSE).
