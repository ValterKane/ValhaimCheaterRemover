# Valheim Character Editor v.1.0 (Remove Cheater flag)

A small Windows tool to edit your own Valheim character save (`.fch`): remove the
**Cheater** flag, and edit your **skills** and **base stats** (health, stamina,
eitr). It works directly on the save file, keeps a backup, and recomputes the
file's checksum so the game still loads it normally.

> **Use it on your own single-player characters only.** Editing saves is done at
> your own risk. The tool always creates a backup, but keep a manual copy too if
> the character is important to you.

---

## 1. What it can do

- **Remove the Cheater flag** (`m_usedCheats`) from a character.
- **Edit skills** — level (0–100) and experience toward the next level, add or
  remove skills.
- **Edit base stats** — max/current health, max/current stamina, eitr, time since
  death, guardian power cooldown.
- Automatically **recomputes the SHA-512 checksum** and keeps the file valid.

It does **not** touch your world files, and it does not require the game to be
running.

---

## 2. Download

1. Go to the **Releases** page of the repository.
2. Download **`ValheimCharacterEditor.exe`**.
3. It is a portable single file — no installer. Put it anywhere you like.

**SmartScreen warning:** the exe is not digitally signed, so Windows may show
"Windows protected your PC". Click **More info → Run anyway**. If you prefer,
you can also run it from source with Python (see the repository README).

---

## 3. Where your character files are

By default:

```
%USERPROFILE%\AppData\LocalLow\IronGate\Valheim\characters
```

Each character is a `.fch` file (plus a `.fch.old` / sidecar files). You can open
the folder quickly by pasting that path into File Explorer's address bar.

> If you use Steam Cloud, make sure the file you edit is the one the game
> actually loads. The editor shows the character name it parsed, so double-check
> it matches.

---

## 4. How to use it

1. **Open** the app, then either:
   - drag-and-drop a `.fch` file onto the window, or
   - click **"Open .fch…"** and pick the file.
2. Check the **"Characters"** tab to confirm you opened the right character
   (name, ID, seed).
3. **Remove the Cheater flag** — untick the `m_usedCheats` checkbox.
4. **Edit stats** on the **"Characteristics"** tab (health, stamina, eitr, etc.).
   Empty fields are left unchanged.
5. **Edit skills** on the **"Skills"** tab:
   - change level / experience,
   - **Add** to create a missing skill,
   - **Remove** to delete one.
6. Click **"Save"**. A backup is created next to the file (`.bak`), and the
   checksum is refreshed.

---

## 5. The Cheater flag and achievements

Valheim marks a character as "cheated" (`m_usedCheats`) when you use console
commands like `devcommands`. While that flag is set, **achievement progress for
that character is permanently disabled**.

This tool can clear that flag, but achievements can *still* stay disabled for
other reasons. In the game code the check is:

```
cheated = m_usedCheats OR world has cheated modifiers OR
          any cheated/spawned item in inventory OR game is modded
```

So clearing the flag is only one part. If achievements are still locked after
clearing it, also check:

- **World modifiers** — if the world was created with cheated modifiers, the
  world itself is marked (you'd need a clean world).
- **Spawned items** — items spawned with console may be flagged "cheated" in your
  inventory.
- **Mods** — running the game through BepInEx/modded clients marks it.

The tool handles the *character* part; it cannot clean a world or your inventory.

---

## 6. Restoring skills that "disappeared"

If your skills look reset, first open the file in the editor and look at the
**Skills** tab. In many cases the levels are still in the save file and only
*were not shown* for another reason (a mod, a death penalty that lowered them,
etc.). If they really are gone from the file, you can re-enter them manually or
copy them from an older backup (`.bak`) that still has them.

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| "Version of profile … only version 46 supported" | Your character was saved by an older game version. Launch the game once and let it save the character, then reopen it. |
| "No embedded player data" | The character has never entered a world. Join a world once and save, then reopen. |
| Achievements still disabled after clearing the flag | See section 5 — world modifiers / cheated items / mods. |
| Windows blocks the exe | SmartScreen → More info → Run anyway (the app is unsigned). |
| The game overwrites my changes | The game rewrites the save when you log out. Make sure the game is closed while editing, and reopen the file if you edited it during a session. |

---

## 8. FAQ

**Is this cheating?** It edits your own local save file. Use it on single-player
or private servers where everyone agrees. It does not give you anything you
could not already do with the in-game console — it mainly *removes* the flag
that console use left behind, and lets you fine-tune stats.

**Does it touch my world?** No. Only the character `.fch` file.

**Is my original file safe?** Yes — before writing, the tool copies the current
file to `<name>.fch.bak` (it never overwrites an existing backup; it appends a
number instead).

**Which game version?** The current 1.0 save format (profile version 46 /
player data version 33). If an update changes the format, wait for a new release
of the tool.
