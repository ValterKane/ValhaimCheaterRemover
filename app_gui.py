#!/usr/bin/env python3
import os, sys, traceback, datetime, struct, tkinter as tk
from tkinter import ttk, filedialog, messagebox

from valheim_character_editor import (
    Character, ParseError, save_character, BASE_FIELDS, SKILLS,
)
import valheim_world_editor as world_editor
import valheim_items as items_db

PAD = {"padx": 6, "pady": 3}


def save_root():
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        return os.path.join(base, "AppData", "LocalLow", "IronGate", "Valheim")
    return os.path.join(os.path.expanduser("~"), ".config", "unity3d",
                        "IronGate", "Valheim")


def scan_local():
    root = save_root()
    chars, worlds = [], []
    if not os.path.isdir(root):
        return chars, worlds
    for sub in ("characters", "characters_local"):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            chars += [os.path.join(d, n) for n in sorted(os.listdir(d))
                      if n.lower().endswith(".fch")]
    for sub in ("worlds", "worlds_local"):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                p = os.path.join(d, n)
                if os.path.isdir(p) and world_editor.find_world_file(p):
                    worlds.append(p)
    return sorted(chars), sorted(worlds)


def _err(msg):
    messagebox.showerror("Error", msg)


def _log_exc(where):
    try:
        log = os.path.join(os.environ.get("TEMP", "."), "valheim_editor_error.log")
        with open(log, "a", encoding="utf-8") as f:
            f.write("\n==== %s [%s]\n%s" % (
                datetime.datetime.now().isoformat(), where, traceback.format_exc()))
    except Exception:
        pass


class EditorApp:
    def __init__(self, root):
        self.root = root
        root.title("Valheim Character Editor")
        root.geometry("940x650")
        root.minsize(660, 440)

        self.ch = None
        self.world = None
        self.doc = "char"
        self.base_vars = {}
        self.skill_rows = {}
        self.skill_names = dict(SKILLS)
        self.cheat_var = tk.BooleanVar(value=False)

        self.all_item_names = sorted(items_db.ITEM_NAME_TO_HASH)
        self._name_lower = {n.lower(): h for n, h in items_db.ITEM_NAME_TO_HASH.items()}
        self.inv_cells = {}
        self.inv_items = {}
        self.inv_selected = None
        self.inv_dirty = False

        self._build_toolbar()
        self._build_notebook()
        self.status = tk.StringVar(value="Open a character file (.fch) or a world folder")
        ttk.Label(root, textvariable=self.status, relief="sunken",
                  anchor="w").pack(fill="x", side="bottom")

        for a in sys.argv[1:]:
            if a.lower().endswith(".fch") and os.path.exists(a):
                self.open_file(a)
                break
            if os.path.isdir(a) and world_editor.find_world_file(a):
                self.open_world(a)
                break

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", **PAD)
        ttk.Button(bar, text="Open character…", command=self.ask_open).pack(side="left")
        ttk.Button(bar, text="Open world…",
                   command=self.ask_open_world).pack(side="left", padx=(6, 0))
        self.local_btn = ttk.Menubutton(bar, text="Local files")
        self.local_menu = tk.Menu(self.local_btn, tearoff=0)
        self.local_btn["menu"] = self.local_menu
        self.local_btn.pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Save", command=self.save).pack(side="left", padx=(8, 0))
        self.file_label = ttk.Label(bar, text="")
        self.file_label.pack(side="left", padx=12)
        self._fill_local_menu()

    def _fill_local_menu(self):
        self.local_menu.delete(0, "end")
        chars, worlds = scan_local()
        if not chars and not worlds:
            self.local_menu.add_command(label="No saves found", state="disabled")
            return
        for p in chars:
            self.local_menu.add_command(
                label=os.path.basename(p), command=lambda p=p: self.open_file(p))
        if chars and worlds:
            self.local_menu.add_separator()
        for p in worlds:
            self.local_menu.add_command(
                label="%s   (world)" % os.path.basename(p),
                command=lambda p=p: self.open_world(p))

    def _build_notebook(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.nb = nb

        self.tab_char = ttk.Frame(nb)
        self.tab_base = ttk.Frame(nb)
        self.tab_skills = ttk.Frame(nb)
        self.tab_inv = ttk.Frame(nb)
        self.tab_world = ttk.Frame(nb)
        nb.add(self.tab_char, text="Character")
        nb.add(self.tab_base, text="Stats")
        nb.add(self.tab_skills, text="Skills")
        nb.add(self.tab_inv, text="Inventory")
        nb.add(self.tab_world, text="World")

        self._build_tab_char()
        self._build_tab_base()
        self._build_tab_skills()
        self._build_tab_inv()
        self._build_tab_world()

    def _build_tab_char(self):
        f = self.tab_char
        self.info_text = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.info_text, justify="left").pack(anchor="w", **PAD)
        self.cheat_check = ttk.Checkbutton(
            f, text="Marked as cheater (m_usedCheats) — untick to re-enable achievements",
            variable=self.cheat_var)
        self.cheat_check.pack(anchor="w", **PAD)
        note = ("Achievements can also be blocked by cheated world modifiers "
                "(setkey), cheated inventory items and mods (BepInEx).")
        ttk.Label(f, text=note, wraplength=640, foreground="#555").pack(anchor="w", **PAD)

    def _build_tab_base(self):
        f = self.tab_base
        self.base_disabled_note = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.base_disabled_note, foreground="#a55").pack(anchor="w", **PAD)
        grid = ttk.Frame(f)
        grid.pack(anchor="w", **PAD)
        for i, (key, label) in enumerate(BASE_FIELDS):
            r, c = divmod(i, 2)
            ttk.Label(grid, text=label + ":").grid(row=r, column=c * 2, sticky="e",
                                                   padx=4, pady=2)
            var = tk.StringVar()
            ent = ttk.Entry(grid, textvariable=var, width=10)
            ent.grid(row=r, column=c * 2 + 1, sticky="w", padx=4, pady=2)
            self.base_vars[key] = var
        ttk.Label(f, text=("Maximum carry weight, speed and some other values are "
                           "not stored in the file — the game computes them from "
                           "equipment and effects."),
                  foreground="#555", wraplength=640).pack(anchor="w", **PAD)

    def _build_tab_skills(self):
        f = self.tab_skills

        top = ttk.Frame(f)
        top.pack(fill="x", **PAD)
        ttk.Label(top, text="Add skill:").pack(side="left")
        self.add_combo = ttk.Combobox(top, state="readonly", width=28)
        self.add_combo.pack(side="left", padx=4)
        ttk.Button(top, text="Add", command=self.add_skill).pack(side="left")

        ttk.Label(f, text="Level: 0–100. Experience is progress toward the next level.",
                  foreground="#555").pack(side="bottom", anchor="w", **PAD)

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, **PAD)
        canvas = tk.Canvas(body, highlightthickness=0, background="#ffffff")
        vsb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=vsb.set)
        self.skills_canvas = canvas

        self.skills_box = ttk.Frame(canvas)
        self._skills_win = canvas.create_window((0, 0), window=self.skills_box, anchor="nw")
        self.skills_box.bind("<Configure>",
                             lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", self._on_canvas_resize)

        hdr = ttk.Frame(self.skills_box)
        hdr.pack(fill="x", padx=4, pady=(2, 0))
        for col, txt, w in (("Skill", "Skill", 26), ("level", "Level", 10),
                            ("acc", "Experience (to next level)", 20)):
            ttk.Label(hdr, text=txt, width=w, font=("TkDefaultFont", 9, "bold")).pack(side="left")

    def _build_tab_world(self):
        f = self.tab_world
        self.world_info = tk.StringVar(
            value="Open a world folder (the one holding _main.N.fwl2).")
        ttk.Label(f, textvariable=self.world_info, justify="left").pack(anchor="w", **PAD)

        grid = ttk.Frame(f)
        grid.pack(anchor="w", **PAD)
        self.world_combos = {}
        for i, slider in enumerate(world_editor.SLIDERS):
            ttk.Label(grid, text=slider["label"] + ":").grid(
                row=i, column=0, sticky="e", padx=4, pady=2)
            cb = ttk.Combobox(grid, state="readonly", width=24)
            cb.grid(row=i, column=1, sticky="w", padx=4, pady=2)
            self.world_combos[slider["id"]] = cb

        note = ("Combat scales every enemy, bosses included - the game has no "
                "separate boss difficulty. The preset line and any keys this "
                "tool doesn't know are left untouched.")
        ttk.Label(f, text=note, foreground="#555", wraplength=640).pack(anchor="w", **PAD)
        self.world_keys = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.world_keys, foreground="#555",
                  wraplength=640).pack(anchor="w", **PAD)

    def _on_canvas_resize(self, e):
        self.skills_canvas.itemconfigure(self._skills_win, width=e.width)

    def ask_open_world(self):
        path = filedialog.askdirectory(
            title="Select a Valheim world folder (contains _main.N.fwl2)")
        if path:
            self.open_world(path)

    def open_world(self, path):
        wf = world_editor.find_world_file(path)
        if not wf:
            _err("No _main.N.fwl2 found in:\n%s" % path)
            return
        try:
            world = world_editor.World(wf)
        except Exception as e:
            _log_exc("open_world: " + wf)
            _err(str(e))
            return
        self.world = world
        self.doc = "world"
        self.file_label.config(
            text="%s  (%s)" % (os.path.basename(os.path.dirname(wf)),
                               os.path.basename(wf)))
        self.status.set("Loaded world: %s" % wf)
        self.nb.select(self.tab_world)
        self._populate_world()

    def _populate_world(self):
        w = self.world
        self.world_info.set(
            "Name: %s\nSeed: %s\nFile: %s" % (w.name, w.seed_name or "(none)", w.path))
        current = w.current()
        for sid, cb in self.world_combos.items():
            slider = next(s for s in world_editor.SLIDERS if s["id"] == sid)
            labels = [o[1] for o in slider["options"]]
            oid = current[sid]
            if oid == world_editor.CUSTOM:
                cb["values"] = [world_editor.CUSTOM_LABEL] + labels
                cb.set(world_editor.CUSTOM_LABEL)
            else:
                cb["values"] = labels
                cb.set(next(o[1] for o in slider["options"] if o[0] == oid))
        self.world_keys.set("Keys: " + (", ".join(w.keys) if w.keys else "(none)"))

    def ask_open(self):
        path = filedialog.askopenfilename(
            title="Select a Valheim character file (.fch)",
            filetypes=[("Valheim character", "*.fch"), ("All files", "*.*")])
        if path:
            self.open_file(path)

    def open_file(self, path):
        try:
            ch = Character(path)
        except Exception as e:
            _log_exc("open_file: " + path)
            _err(str(e))
            return
        self.ch = ch
        self.doc = "char"
        self.file_label.config(text=os.path.basename(path))
        self.status.set("Loaded: %s" % path)
        self.nb.select(self.tab_char)
        self._populate()

    def _populate(self):
        ch = self.ch
        p = ch.profile
        cheater = "yes" if p["used_cheats"] else "no"
        self.info_text.set(
            "Name: %s\nID: %d    Seed: %s\nCreated: %s\nCheater flag: %s"
            % (p["name"], p["player_id"], p["seed"] or "(none)",
               p["date_created"], cheater))
        self.cheat_var.set(bool(p["used_cheats"]))

        for key in self.base_vars:
            self.base_vars[key].set("")
        if ch.player is None:
            self.base_disabled_note.set(
                "No embedded player data (the character has not entered a world yet) — "
                "stats and skills are unavailable.")
            for key in self.base_vars:
                self.base_vars[key].set("")
            for e in self._walk_entries():
                e.state(["disabled"])
        else:
            self.base_disabled_note.set("")
            blob = ch.body[p["blob_off"]:p["blob_off"] + p["blob_len"]]
            for key, var in self.base_vars.items():
                off = ch.player["base"].get(key)
                if off is not None:
                    val = struct.unpack_from("<f", blob, off)[0]
                    var.set(("%.3f" % val).rstrip("0").rstrip("."))
            for e in self._walk_entries():
                e.state(["!disabled"])

        self._rebuild_skill_rows()
        self._populate_inventory()

    def _build_tab_inv(self):
        f = self.tab_inv
        ctl = ttk.Frame(f)
        ctl.pack(fill="x", **PAD)
        ttk.Label(ctl, text="Item:").pack(side="left")
        self.item_combo = ttk.Combobox(ctl, width=24, values=self.all_item_names[:300],
                                       postcommand=self._filter_items)
        self.item_combo.pack(side="left", padx=(2, 8))
        ttk.Label(ctl, text="Stack:").pack(side="left")
        self.inv_stack = ttk.Entry(ctl, width=5)
        self.inv_stack.insert(0, "1")
        self.inv_stack.pack(side="left", padx=(2, 8))
        ttk.Label(ctl, text="Quality:").pack(side="left")
        self.inv_quality = ttk.Entry(ctl, width=5)
        self.inv_quality.insert(0, "1")
        self.inv_quality.pack(side="left", padx=(2, 8))
        ttk.Label(ctl, text="Durability%:").pack(side="left")
        self.inv_durability = ttk.Entry(ctl, width=5)
        self.inv_durability.insert(0, "100")
        self.inv_durability.pack(side="left", padx=(2, 8))
        ttk.Button(ctl, text="Place", command=self._place_item).pack(side="left")
        ttk.Button(ctl, text="Clear", command=self._clear_cell).pack(side="left", padx=(6, 0))
        ttk.Label(f, text=("Click a slot, then type an item name or numeric ID and "
                           "press Place. Type a few letters and open the list (arrow "
                           "button or Down) to narrow it. Empty slots add; occupied "
                           "slots are replaced. Cheater-marked items are shown in red."),
                  foreground="#555", wraplength=680).pack(anchor="w", **PAD)

        grid = ttk.Frame(f)
        grid.pack(anchor="w", **PAD)
        for y in range(4):
            for x in range(8):
                lbl = tk.Label(grid, text="", width=14, height=2, relief="groove",
                               borderwidth=1, bg="#ececec", anchor="center")
                lbl.grid(row=y, column=x, padx=1, pady=1, sticky="nsew")
                lbl.bind("<Button-1>", lambda e, xx=x, yy=y: self._select_cell(xx, yy))
                self.inv_cells[(x, y)] = lbl

        row2 = ttk.Frame(f)
        row2.pack(fill="x", **PAD)
        self.inv_cheat_note = tk.StringVar(value="")
        ttk.Label(row2, textvariable=self.inv_cheat_note, foreground="#a22").pack(
            side="left", padx=(0, 12))
        ttk.Button(row2, text="Unmark selected",
                   command=self._unmark_selected).pack(side="left")
        ttk.Button(row2, text="Clear all cheater marks",
                   command=self._clear_all_cheats).pack(side="left", padx=(6, 0))

    def _populate_inventory(self):
        self.inv_items = {}
        self.inv_selected = None
        self.inv_dirty = False
        if self.ch is not None and self.ch.player is not None:
            for it in self.ch.player["inventory"]:
                self.inv_items[(it["x"], it["y"])] = it
        for (x, y) in self.inv_cells:
            self._render_cell(x, y)
        self._update_cheat_note()

    @staticmethod
    def _cell_text(item):
        if item is None:
            return ""
        name = items_db.ITEM_HASH_TO_NAME.get(item["hash"], str(item["hash"]))
        txt = "%s x%d" % (name, item["stack"]) if item["stack"] > 1 else name
        return txt[:20]

    def _render_cell(self, x, y):
        lbl = self.inv_cells[(x, y)]
        item = self.inv_items.get((x, y))
        cheated = item is not None and item.get("cheated")
        lbl.config(text=self._cell_text(item))
        if cheated:
            bg, fg = ("#c0392b", "#ffffff") if (x, y) == self.inv_selected \
                else ("#f2a6a6", "#5b0a0a")
        elif (x, y) == self.inv_selected:
            bg, fg = "#bfd9ff", "#000000"
        elif item is not None:
            bg, fg = "#ffffff", "#000000"
        else:
            bg, fg = "#ececec", "#808080"
        lbl.config(bg=bg, fg=fg)

    def _select_cell(self, x, y):
        self.inv_selected = (x, y)
        for (xx, yy) in self.inv_cells:
            self._render_cell(xx, yy)

    def _filter_items(self):
        txt = self.item_combo.get().strip()
        if not txt:
            self.item_combo["values"] = self.all_item_names[:300]
            return
        low = txt.lower()
        matches = [n for n in self.all_item_names if low in n.lower()]
        matches.sort(key=lambda n: (not n.lower().startswith(low), n.lower()))
        self.item_combo["values"] = matches[:300]

    def _resolve_item(self, txt):
        t = txt.strip()
        if not t:
            return None
        try:
            h = int(t)
            if h in items_db.ITEM_HASH_TO_NAME:
                return h
        except ValueError:
            pass
        return self._name_lower.get(t.lower())

    def _place_item(self):
        if self.inv_selected is None:
            _err("Select a slot first (click one in the grid).")
            return
        h = self._resolve_item(self.item_combo.get())
        if h is None:
            _err("Unknown item name or ID: %r" % self.item_combo.get())
            return
        try:
            stack = max(1, int(self.inv_stack.get() or "1"))
            quality = max(1, int(self.inv_quality.get() or "1"))
            dur_pct = float((self.inv_durability.get() or "100").replace(",", "."))
        except ValueError:
            _err("Stack, Quality and Durability must be numbers.")
            return
        x, y = self.inv_selected
        self.inv_items[(x, y)] = {
            "hash": h, "x": x, "y": y, "stack": stack, "quality": quality,
            "durability": max(0, int(round(dur_pct * 100))),
            "cheated": False, "world_level": 0,
        }
        self.inv_dirty = True
        self._render_cell(x, y)
        name = items_db.ITEM_HASH_TO_NAME.get(h, str(h))
        self.status.set("Placed %s x%d at (%d,%d)" % (name, stack, x, y))

    def _clear_cell(self):
        if self.inv_selected is None:
            _err("Select a slot first (click one in the grid).")
            return
        x, y = self.inv_selected
        self.inv_items[(x, y)] = None
        self.inv_dirty = True
        self._render_cell(x, y)

    def _collect_inventory(self):
        return [self.inv_items[(x, y)] for y in range(4) for x in range(8)
                if self.inv_items.get((x, y)) is not None]

    def _update_cheat_note(self):
        items = [it for it in self.inv_items.values() if it is not None]
        cheated = sum(1 for it in items if it.get("cheated"))
        if cheated:
            self.inv_cheat_note.set("%d of %d items marked as cheated"
                                    % (cheated, len(items)))
        else:
            self.inv_cheat_note.set("No cheater-marked items (%d items)" % len(items))

    def _unmark_selected(self):
        if self.inv_selected is None:
            _err("Select a slot first (click one in the grid).")
            return
        item = self.inv_items.get(self.inv_selected)
        if item is None or not item.get("cheated"):
            _err("That slot has no cheater-marked item.")
            return
        item["cheated"] = False
        self.inv_dirty = True
        self._render_cell(*self.inv_selected)
        self._update_cheat_note()
        self.status.set("Removed cheater mark from (%d,%d)" % self.inv_selected)

    def _clear_all_cheats(self):
        n = 0
        for it in self.inv_items.values():
            if it is not None and it.get("cheated"):
                it["cheated"] = False
                n += 1
        if n:
            self.inv_dirty = True
            for (x, y) in self.inv_cells:
                self._render_cell(x, y)
            self._update_cheat_note()
            self.status.set("Removed cheater mark from %d item(s)" % n)
        else:
            self.status.set("No cheater-marked items to clear")

    def _walk_entries(self):
        seen = set()
        for f in (self.tab_base,):
            for child in f.winfo_children():
                for sub in child.winfo_children():
                    if isinstance(sub, ttk.Entry) and id(sub) not in seen:
                        seen.add(id(sub))
                        yield sub

    def _rebuild_skill_rows(self):
        for row in self.skill_rows.values():
            row["frame"].destroy()
        self.skill_rows = {}
        for s in self.ch.skills:
            self._add_row(s["type"], s["level"], s["acc"])
        self._refresh_add_combo()

    def _add_row(self, stype, level, acc):
        name = SKILLS.get(stype, "Skill %d" % stype)
        frame = ttk.Frame(self.skills_box)
        frame.pack(fill="x", padx=4, pady=1)
        ttk.Label(frame, text=name, width=26, anchor="w").pack(side="left")
        lvl = tk.StringVar(value=self._fmt(level))
        accv = tk.StringVar(value=self._fmt(acc))
        ttk.Entry(frame, textvariable=lvl, width=10).pack(side="left", padx=4)
        ttk.Entry(frame, textvariable=accv, width=18).pack(side="left", padx=4)
        ttk.Button(frame, text="Remove",
                   command=lambda t=stype: self.del_skill(t)).pack(side="left", padx=6)
        self.skill_rows[stype] = {"frame": frame, "level": lvl, "acc": accv,
                                  "name": name}
        self.skills_canvas.configure(scrollregion=self.skills_canvas.bbox("all"))

    @staticmethod
    def _fmt(v):
        return ("%.3f" % v).rstrip("0").rstrip(".")

    def _refresh_add_combo(self):
        present = set(self.skill_rows)
        missing = [self.skill_names[t] for t in sorted(self.skill_names) if t not in present]
        self.add_combo["values"] = missing
        if missing:
            self.add_combo.current(0)
        else:
            self.add_combo.set("")

    def add_skill(self):
        sel = self.add_combo.get()
        if not sel:
            return
        stype = next(t for t, nm in self.skill_names.items() if nm == sel)
        if stype in self.skill_rows:
            return
        self._add_row(stype, 1.0, 0.0)
        self._refresh_add_combo()

    def del_skill(self, stype):
        row = self.skill_rows.pop(stype)
        row["frame"].destroy()
        self.skills_canvas.configure(scrollregion=self.skills_canvas.bbox("all"))
        self._refresh_add_combo()

    def _parse_float(self, text, what):
        try:
            v = float(text.replace(",", "."))
        except ValueError:
            raise ValueError("\"%s\" is not a number (\"%s\")" % (what, text))
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("\"%s\" is not a number" % what)
        return v

    def save(self):
        if self.doc == "world":
            self._save_world()
            return
        if self.ch is None:
            _err("Open a character file first.")
            return
        try:
            skills_levels = {}
            for stype, row in self.skill_rows.items():
                lvl = self._parse_float(row["level"].get(), "level of %s" % row["name"])
                acc = self._parse_float(row["acc"].get(), "experience of %s" % row["name"])
                lvl = max(0.0, min(100.0, lvl))
                acc = max(0.0, acc)
                skills_levels[stype] = (lvl, acc)
            base_values = {}
            for key, var in self.base_vars.items():
                txt = var.get().strip()
                if txt:
                    base_values[key] = self._parse_float(txt, dict(BASE_FIELDS)[key])
            used_cheats = bool(self.cheat_var.get())
            items = self._collect_inventory() if self.inv_dirty else None
        except ValueError as e:
            _err(str(e))
            return

        target = self.ch.path
        try:
            backup = save_character(self.ch, target, skills_levels,
                                    base_values, used_cheats, False, items)
        except (ParseError, OSError, ValueError) as e:
            _err("Failed to save: %s" % e)
            return

        msg = "Saved: %s" % os.path.basename(target)
        if backup:
            msg += "\nBackup: %s" % backup
        msg += "\nChecksum updated."
        if used_cheats:
            msg += ("\n\nNote: the Cheater flag is still set — "
                    "achievements are disabled for this character.")
        messagebox.showinfo("Done", msg)
        self.open_file(target)

    def _save_world(self):
        if self.world is None:
            _err("Open a world folder first.")
            return
        for sid, cb in self.world_combos.items():
            slider = next(s for s in world_editor.SLIDERS if s["id"] == sid)
            label = cb.get()
            oid = next((o[0] for o in slider["options"] if o[1] == label),
                       world_editor.CUSTOM)
            self.world.set_modifier(sid, oid)
        target = self.world.path
        try:
            backup = self.world.save(target)
        except (world_editor.WorldParseError, OSError) as e:
            _err("Failed to save: %s" % e)
            return
        msg = "Saved: %s" % os.path.basename(target)
        if backup:
            msg += "\nBackup: %s" % backup
        messagebox.showinfo("Done", msg)
        self.open_world(os.path.dirname(target))


def run_gui():
    try:
        root = tk.Tk()
    except Exception as e:
        _log_exc("tk init")
        sys.stderr.write("GUI unavailable: %s\n" % e)
        sys.exit(2)
    try:
        EditorApp(root)
        root.mainloop()
    except Exception as e:
        _log_exc("mainloop")
        try:
            messagebox.showerror("Error", "Something went wrong:\n%s" % e)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    run_gui()
