#!/usr/bin/env python3
import os, re, sys, traceback, datetime, struct, tkinter as tk
from tkinter import ttk, filedialog, messagebox

from valheim_character_editor import (
    Character, ParseError, save_character, BASE_FIELDS, SKILLS,
    INV_ROWS_FALLBACK, decode_drop_key,
)
import valheim_world_editor as world_editor
import valheim_items as items_db

PAD = {"padx": 6, "pady": 3}
INV_COLS = 8


def pretty_name(prefab):
    """ArmorPaddedCuirass -> Armor Padded Cuirass, for the grid and titles."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[A-Z])(?=[A-Z][a-z])", " ", prefab)
    return s.replace("_", " ")


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
        root.geometry("1040x700")
        root.minsize(820, 520)

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
        self.inv_rows = INV_ROWS_FALLBACK

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
        self.tab_drops = ttk.Frame(nb)
        self.tab_world = ttk.Frame(nb)
        nb.add(self.tab_char, text="Character")
        nb.add(self.tab_base, text="Stats")
        nb.add(self.tab_skills, text="Skills")
        nb.add(self.tab_inv, text="Inventory")
        nb.add(self.tab_drops, text="Drop luck")
        nb.add(self.tab_world, text="World")

        self._build_tab_char()
        self._build_tab_base()
        self._build_tab_skills()
        self._build_tab_inv()
        self._build_tab_drops()
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

    def _build_tab_drops(self):
        f = self.tab_drops
        self.drops_note = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.drops_note, foreground="#555",
                  wraplength=680, justify="left").pack(anchor="w", **PAD)
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, **PAD)
        cols = ("drop", "chance", "misses")
        tv = ttk.Treeview(body, columns=cols, show="headings", selectmode="none")
        tv.heading("drop", text="Drop")
        tv.heading("chance", text="Chance")
        tv.heading("misses", text="Misses in a row")
        tv.column("drop", width=260, anchor="w")
        tv.column("chance", width=90, anchor="e")
        tv.column("misses", width=120, anchor="e")
        vsb = ttk.Scrollbar(body, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)
        self.drops_tree = tv
        ttk.Label(f, text=("Read-only. Since Valheim 1.0.20 the game remembers how "
                           "many times each rare drop has failed, per character, "
                           "and nudges the odds up until it lands. One row per "
                           "drop and chance; star levels raise the chance, so a "
                           "creature can appear more than once."),
                  foreground="#555", wraplength=680).pack(anchor="w", **PAD)

    def _populate_drops(self):
        tv = self.drops_tree
        tv.delete(*tv.get_children())
        ch = self.ch
        if ch is None or ch.player is None:
            self.drops_note.set("")
            return
        if ch.player["version"] < 34:
            self.drops_note.set("This character was last saved before Valheim 1.0.20; "
                                "drop luck is not stored yet.")
            return
        drops = ch.player["drops"]
        if not drops:
            self.drops_note.set("No drop luck recorded yet.")
            return
        rows = []
        for d in drops:
            name, permille = decode_drop_key(d["key"], items_db.ITEM_HASH_TO_NAME)
            if name is None:
                rows.append(("Unknown (key %d)" % d["key"], "", d["misses"]))
            else:
                rows.append((name, "%g%%" % (permille / 10.0), d["misses"]))
        rows.sort(key=lambda r: (-r[2], r[0]))
        for row in rows:
            tv.insert("", "end", values=row)
        self.drops_note.set("%d drop%s tracked." % (len(rows), "" if len(rows) == 1 else "s"))

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
        self._populate_drops()

    # ------------------------------------------------------------------ inventory

    def _build_tab_inv(self):
        f = self.tab_inv
        outer = ttk.Frame(f)
        outer.pack(fill="both", expand=True, **PAD)
        left = ttk.Frame(outer)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(outer)
        right.pack(side="left", fill="y", padx=(12, 0))

        self.inv_grid = ttk.Frame(left, takefocus=1)
        self.inv_grid.pack(anchor="nw")
        self.inv_grid.bind("<Delete>", lambda e: self._clear_cell())
        self.inv_grid.bind("<BackSpace>", lambda e: self._clear_cell())
        for key, dx, dy in (("<Left>", -1, 0), ("<Right>", 1, 0),
                            ("<Up>", 0, -1), ("<Down>", 0, 1)):
            self.inv_grid.bind(key, lambda e, dx=dx, dy=dy: self._move_selection(dx, dy))
        self._cell_pos = {}
        self._drag_from = None
        self._dragging = False
        self._build_inv_grid()

        ttk.Label(left, text=("Click a slot to inspect it. Drag a slot onto another to "
                              "move or swap. Right-click for a menu; Delete clears. "
                              "Cheater-marked items are red."),
                  foreground="#555", wraplength=620, justify="left").pack(anchor="w", pady=(8, 0))
        row2 = ttk.Frame(left)
        row2.pack(fill="x", pady=(8, 0))
        self.inv_cheat_note = tk.StringVar(value="")
        ttk.Label(row2, textvariable=self.inv_cheat_note, foreground="#a22").pack(
            side="left", padx=(0, 12))
        ttk.Button(row2, text="Clear all cheater marks",
                   command=self._clear_all_cheats).pack(side="left")

        self.cell_menu = tk.Menu(self.root, tearoff=0)
        self.cell_menu.add_command(label="Remove cheater mark", command=self._unmark_selected)
        self.cell_menu.add_command(label="Clear slot", command=self._clear_cell)

        # slot inspector
        ed = ttk.LabelFrame(right, text="Selected slot")
        ed.pack(fill="x")
        self.slot_title = tk.StringVar(value="Nothing selected")
        ttk.Label(ed, textvariable=self.slot_title,
                  font=("TkDefaultFont", 9, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 0))
        self.slot_item = tk.StringVar(value="")
        ttk.Label(ed, textvariable=self.slot_item, wraplength=240,
                  justify="left").grid(row=1, column=0, columnspan=2, sticky="w", padx=6)
        self.slot_vars = {}
        self.slot_entries = []
        for i, (key, label) in enumerate((("stack", "Stack"), ("quality", "Quality"),
                                          ("durability", "Durability"))):
            ttk.Label(ed, text=label + ":").grid(row=2 + i, column=0, sticky="e",
                                                 padx=(6, 4), pady=2)
            var = tk.StringVar()
            ent = ttk.Entry(ed, textvariable=var, width=10)
            ent.grid(row=2 + i, column=1, sticky="w", pady=2)
            ent.bind("<Return>", lambda e: self._apply_slot())
            self.slot_vars[key] = var
            self.slot_entries.append(ent)
        btns = ttk.Frame(ed)
        btns.grid(row=5, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 6))
        self.slot_apply = ttk.Button(btns, text="Apply", command=self._apply_slot)
        self.slot_apply.pack(side="left")
        self.slot_unmark = ttk.Button(btns, text="Unmark", command=self._unmark_selected)
        self.slot_unmark.pack(side="left", padx=(6, 0))
        self.slot_clear = ttk.Button(btns, text="Clear", command=self._clear_cell)
        self.slot_clear.pack(side="left", padx=(6, 0))

        # item picker
        pk = ttk.LabelFrame(right, text="Put an item in the slot")
        pk.pack(fill="both", expand=True, pady=(10, 0))
        srow = ttk.Frame(pk)
        srow.pack(fill="x", padx=6, pady=(4, 2))
        self.item_search = tk.StringVar()
        self.item_entry = ttk.Entry(srow, textvariable=self.item_search)
        self.item_entry.pack(side="left", fill="x", expand=True)
        self.item_entry.bind("<KeyRelease>", self._on_search_key)
        self.item_entry.bind("<Return>", lambda e: self._place_from_list())
        self.item_entry.bind("<Down>", self._focus_item_list)
        ttk.Label(srow, text="×").pack(side="left", padx=(6, 2))
        self.place_qty = ttk.Entry(srow, width=5)
        self.place_qty.insert(0, "1")
        self.place_qty.pack(side="left")
        self.place_qty.bind("<Return>", lambda e: self._place_from_list())

        lbf = ttk.Frame(pk)
        lbf.pack(fill="both", expand=True, padx=6)
        self.item_list = tk.Listbox(lbf, height=14, width=30, exportselection=False,
                                    activestyle="none")
        lsb = ttk.Scrollbar(lbf, orient="vertical", command=self.item_list.yview)
        self.item_list.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.item_list.pack(side="left", fill="both", expand=True)
        self.item_list.bind("<Double-Button-1>", lambda e: self._place_from_list())
        self.item_list.bind("<Return>", lambda e: self._place_from_list())
        self.item_list.bind("<Escape>", lambda e: self.item_entry.focus_set())

        prow = ttk.Frame(pk)
        prow.pack(fill="x", padx=6, pady=(4, 6))
        ttk.Button(prow, text="Place", command=self._place_from_list).pack(side="left")
        self.item_count_note = tk.StringVar(value="")
        ttk.Label(prow, textvariable=self.item_count_note,
                  foreground="#555").pack(side="left", padx=(8, 0))
        ttk.Label(pk, text=("Type to filter, Enter or double-click to place. A prefab "
                            "name or numeric ID also works. New items start at quality "
                            "1 and durability 100; edit the slot afterwards."),
                  foreground="#555", wraplength=240, justify="left").pack(
            anchor="w", padx=6, pady=(0, 6))
        self._filter_items()
        self._refresh_slot_editor()

    def _build_inv_grid(self):
        for lbl in self.inv_cells.values():
            lbl.destroy()
        self.inv_cells = {}
        self._cell_pos = {}
        for y in range(self.inv_rows):
            for x in range(INV_COLS):
                lbl = tk.Label(self.inv_grid, text="", width=11, height=3,
                               wraplength=80, justify="center",
                               relief="groove", borderwidth=1, bg="#ececec",
                               anchor="center", cursor="hand2")
                lbl.grid(row=y, column=x, padx=1, pady=1, sticky="nsew")
                lbl.bind("<ButtonPress-1>", lambda e, xx=x, yy=y: self._cell_press(xx, yy))
                lbl.bind("<B1-Motion>", self._cell_drag)
                lbl.bind("<ButtonRelease-1>", self._cell_release)
                for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
                    lbl.bind(seq, lambda e, xx=x, yy=y: self._cell_menu(e, xx, yy))
                self.inv_cells[(x, y)] = lbl
                self._cell_pos[lbl] = (x, y)

    def _populate_inventory(self):
        self.inv_items = {}
        self.inv_selected = None
        self.inv_dirty = False
        if self.ch is not None and self.ch.player is not None:
            self.inv_rows = self.ch.player["inv_rows"]
            for it in self.ch.player["inventory"]:
                self.inv_items[(it["x"], it["y"])] = it
        else:
            self.inv_rows = INV_ROWS_FALLBACK
        self._build_inv_grid()
        for (x, y) in self.inv_cells:
            self._render_cell(x, y)
        self._update_cheat_note()
        self._refresh_slot_editor()

    @staticmethod
    def _item_name(item):
        return items_db.ITEM_HASH_TO_NAME.get(item["hash"], str(item["hash"]))

    @staticmethod
    def _cell_text(item):
        if item is None:
            return ""
        name = pretty_name(items_db.ITEM_HASH_TO_NAME.get(item["hash"], str(item["hash"])))
        extra = []
        if item["stack"] > 1:
            extra.append("×%d" % item["stack"])
        if item["quality"] > 1:
            extra.append("★%d" % item["quality"])
        return name + ("\n" + "  ".join(extra) if extra else "")

    def _render_cell(self, x, y):
        lbl = self.inv_cells[(x, y)]
        item = self.inv_items.get((x, y))
        cheated = item is not None and item.get("cheated")
        selected = (x, y) == self.inv_selected
        lbl.config(text=self._cell_text(item))
        if cheated:
            bg, fg = ("#c0392b", "#ffffff") if selected else ("#f2a6a6", "#5b0a0a")
        elif selected:
            bg, fg = ("#bfd9ff", "#000000") if item else ("#d9e8ff", "#5a6b80")
        elif item is not None:
            bg, fg = "#ffffff", "#000000"
        else:
            bg, fg = "#ececec", "#808080"
        lbl.config(bg=bg, fg=fg, relief="solid" if selected else "groove")

    def _select_cell(self, x, y):
        prev = self.inv_selected
        self.inv_selected = (x, y)
        if prev in self.inv_cells:
            self._render_cell(*prev)
        self._render_cell(x, y)
        self._refresh_slot_editor()

    def _move_selection(self, dx, dy):
        if self.inv_selected is None:
            self._select_cell(0, 0)
            return
        x, y = self.inv_selected
        nx = max(0, min(INV_COLS - 1, x + dx))
        ny = max(0, min(self.inv_rows - 1, y + dy))
        self._select_cell(nx, ny)

    # --- mouse: click, drag to move/swap, right-click menu

    def _cell_press(self, x, y):
        self.inv_grid.focus_set()
        self._drag_from = (x, y)
        self._dragging = False
        self._select_cell(x, y)

    def _cell_drag(self, e):
        if self._drag_from is None or self.inv_items.get(self._drag_from) is None:
            return
        if not self._dragging:
            self._dragging = True
            e.widget.config(cursor="fleur")

    def _cell_release(self, e):
        e.widget.config(cursor="hand2")
        src, self._drag_from = self._drag_from, None
        if not self._dragging or src is None:
            return
        self._dragging = False
        target = self.root.winfo_containing(e.x_root, e.y_root)
        dst = self._cell_pos.get(target)
        if dst is not None and dst != src:
            self._move_item(src, dst)

    def _cell_menu(self, e, x, y):
        self._select_cell(x, y)
        item = self.inv_items.get((x, y))
        self.cell_menu.entryconfig(0, state="normal" if item and item.get("cheated") else "disabled")
        self.cell_menu.entryconfig(1, state="normal" if item else "disabled")
        try:
            self.cell_menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.cell_menu.grab_release()

    @staticmethod
    def _relocated(item, pos):
        # moving keeps the item bytes as they are; only the slot changes
        it = dict(item)
        it["x"], it["y"] = pos
        if "raw" in it:
            raw = bytearray(it["raw"])
            raw[4], raw[5] = pos
            it["raw"] = bytes(raw)
        return it

    def _move_item(self, src, dst):
        a = self.inv_items.get(src)
        if a is None:
            return
        b = self.inv_items.get(dst)
        self.inv_items[dst] = self._relocated(a, dst)
        self.inv_items[src] = self._relocated(b, src) if b is not None else None
        self.inv_dirty = True
        self.inv_selected = dst
        self._render_cell(*src)
        self._render_cell(*dst)
        self._refresh_slot_editor()
        verb = "Swapped" if b is not None else "Moved"
        self.status.set("%s %s to slot %d,%d" % (verb, self._item_name(a), dst[0], dst[1]))

    # --- slot inspector

    def _refresh_slot_editor(self):
        sel = self.inv_selected
        item = self.inv_items.get(sel) if sel is not None else None
        for ent in self.slot_entries:
            ent.state(["!disabled" if item else "disabled"])
        for btn in (self.slot_apply, self.slot_clear):
            btn.state(["!disabled" if item else "disabled"])
        self.slot_unmark.state(["!disabled" if item and item.get("cheated") else "disabled"])
        if sel is None:
            self.slot_title.set("Nothing selected")
            self.slot_item.set("Click a slot in the grid.")
            for var in self.slot_vars.values():
                var.set("")
            return
        if item is None:
            self.slot_title.set("Slot %d,%d — empty" % sel)
            self.slot_item.set("Pick an item below to fill it.")
            for var in self.slot_vars.values():
                var.set("")
            return
        name = self._item_name(item)
        self.slot_title.set("Slot %d,%d — %s" % (sel[0], sel[1], pretty_name(name)))
        bits = ["%s  (ID %d)" % (name, item["hash"])]
        if item.get("crafter_name"):
            bits.append("Crafted by %s" % item["crafter_name"])
        if item.get("world_level"):
            bits.append("World level %d" % item["world_level"])
        if item.get("cheated"):
            bits.append("Marked as cheated")
        self.slot_item.set("\n".join(bits))
        self.slot_vars["stack"].set(str(item["stack"]))
        self.slot_vars["quality"].set(str(item["quality"]))
        self.slot_vars["durability"].set(("%.2f" % (item["durability"] / 100.0)).rstrip("0").rstrip("."))

    def _apply_slot(self):
        sel = self.inv_selected
        item = self.inv_items.get(sel) if sel is not None else None
        if item is None:
            return
        try:
            stack = int(self.slot_vars["stack"].get().strip() or "1")
            quality = int(self.slot_vars["quality"].get().strip() or "1")
            dur = float((self.slot_vars["durability"].get().strip() or "0").replace(",", "."))
        except ValueError:
            _err("Stack and quality must be whole numbers; durability a number.")
            return
        stack = max(1, min(65535, stack))
        quality = max(1, min(65535, quality))
        durability = max(0, min(2147483647, int(round(dur * 100))))
        if (stack, quality, durability) == (item["stack"], item["quality"], item["durability"]):
            self.status.set("No change")
            return
        new = dict(item)
        new.pop("raw", None)            # re-encoded from fields; extras are kept
        new.update(stack=stack, quality=quality, durability=durability)
        self.inv_items[sel] = new
        self.inv_dirty = True
        self._render_cell(*sel)
        self._refresh_slot_editor()
        self.status.set("Updated %s in slot %d,%d" % (self._item_name(new), sel[0], sel[1]))

    # --- item picker

    def _on_search_key(self, e):
        if e.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        self._filter_items()

    def _focus_item_list(self, e=None):
        if self.item_list.size():
            self.item_list.focus_set()
            self.item_list.selection_clear(0, "end")
            self.item_list.selection_set(0)
            self.item_list.activate(0)
            self.item_list.see(0)
        return "break"

    def _filter_items(self):
        txt = self.item_search.get().strip().lower().replace(" ", "")
        if txt:
            matches = [n for n in self.all_item_names if txt in n.lower()]
            matches.sort(key=lambda n: (not n.lower().startswith(txt), n.lower()))
        else:
            matches = self.all_item_names
        self._item_matches = matches
        self.item_list.delete(0, "end")
        for n in matches:
            self.item_list.insert("end", n)
        if matches:
            self.item_list.selection_clear(0, "end")
            self.item_list.selection_set(0)
            self.item_list.activate(0)
        self.item_count_note.set("%d item%s" % (len(matches), "" if len(matches) == 1 else "s"))

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

    def _picked_item(self):
        # an exact name or numeric ID in the box wins; otherwise the list selection
        h = self._resolve_item(self.item_search.get())
        if h is not None:
            return h
        sel = self.item_list.curselection()
        if sel:
            return items_db.ITEM_NAME_TO_HASH[self._item_matches[sel[0]]]
        return None

    def _first_empty_slot(self):
        for y in range(self.inv_rows):
            for x in range(INV_COLS):
                if self.inv_items.get((x, y)) is None:
                    return (x, y)
        return None

    def _place_from_list(self):
        if self.ch is None or self.ch.player is None:
            _err("Open a character with player data first.")
            return
        h = self._picked_item()
        if h is None:
            _err("Pick an item from the list, or type a prefab name or numeric ID.")
            return
        try:
            qty = max(1, min(65535, int(self.place_qty.get().strip() or "1")))
        except ValueError:
            _err("Quantity must be a whole number.")
            return
        slot = self.inv_selected or self._first_empty_slot()
        if slot is None:
            _err("The inventory is full. Select a slot to replace.")
            return
        replaced = self.inv_items.get(slot)
        x, y = slot
        self.inv_items[slot] = {
            "hash": h, "x": x, "y": y, "stack": qty, "quality": 1,
            "durability": 10000, "cheated": False, "world_level": 0,
        }
        self.inv_dirty = True
        self.inv_selected = slot
        self._render_cell(x, y)
        self._refresh_slot_editor()
        self._update_cheat_note()
        name = items_db.ITEM_HASH_TO_NAME.get(h, str(h))
        what = "Replaced %s with" % self._item_name(replaced) if replaced else "Placed"
        self.status.set("%s %s ×%d in slot %d,%d" % (what, name, qty, x, y))

    def _clear_cell(self):
        sel = self.inv_selected
        if sel is None or self.inv_items.get(sel) is None:
            return
        name = self._item_name(self.inv_items[sel])
        self.inv_items[sel] = None
        self.inv_dirty = True
        self._render_cell(*sel)
        self._refresh_slot_editor()
        self._update_cheat_note()
        self.status.set("Cleared %s from slot %d,%d" % (name, sel[0], sel[1]))

    def _collect_inventory(self):
        return [self.inv_items[(x, y)] for y in range(self.inv_rows) for x in range(INV_COLS)
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
        sel = self.inv_selected
        item = self.inv_items.get(sel) if sel is not None else None
        if item is None or not item.get("cheated"):
            return
        item["cheated"] = False
        self.inv_dirty = True
        self._render_cell(*sel)
        self._refresh_slot_editor()
        self._update_cheat_note()
        self.status.set("Removed cheater mark from %s" % self._item_name(item))

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
            self._refresh_slot_editor()
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
