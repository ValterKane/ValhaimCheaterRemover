#!/usr/bin/env python3
import os, sys, traceback, datetime, struct, tkinter as tk
from tkinter import ttk, filedialog, messagebox

from valheim_character_editor import (
    Character, ParseError, save_character, BASE_FIELDS, SKILLS,
)

PAD = {"padx": 6, "pady": 3}


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
        root.geometry("720x520")
        root.minsize(560, 420)

        self.ch = None
        self.base_vars = {}
        self.skill_rows = {}
        self.skill_names = dict(SKILLS)
        self.cheat_var = tk.BooleanVar(value=False)
        self.cheat_items_var = tk.BooleanVar(value=False)

        self._build_toolbar()
        self._build_notebook()
        self.status = tk.StringVar(value="Open a character file (.fch)")
        ttk.Label(root, textvariable=self.status, relief="sunken",
                  anchor="w").pack(fill="x", side="bottom")

        for a in sys.argv[1:]:
            if a.lower().endswith(".fch") and os.path.exists(a):
                self.open_file(a)
                break

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", **PAD)
        ttk.Button(bar, text="Open .fch…", command=self.ask_open).pack(side="left")
        ttk.Button(bar, text="Save", command=self.save).pack(side="left", padx=(8, 0))
        self.file_label = ttk.Label(bar, text="")
        self.file_label.pack(side="left", padx=12)

    def _build_notebook(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.tab_char = ttk.Frame(nb)
        self.tab_base = ttk.Frame(nb)
        self.tab_skills = ttk.Frame(nb)
        nb.add(self.tab_char, text="Character")
        nb.add(self.tab_base, text="Stats")
        nb.add(self.tab_skills, text="Skills")

        self._build_tab_char()
        self._build_tab_base()
        self._build_tab_skills()

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

        self.items_note = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.items_note, foreground="#a55").pack(anchor="w", **PAD)
        self.cheat_items_check = ttk.Checkbutton(
            f, text="Clear cheater marks on inventory items",
            variable=self.cheat_items_var)
        self.cheat_items_check.pack(anchor="w", **PAD)

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

    def _on_canvas_resize(self, e):
        self.skills_canvas.itemconfigure(self._skills_win, width=e.width)

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
        self.file_label.config(text=os.path.basename(path))
        self.status.set("Loaded: %s" % path)
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
        self.cheat_items_var.set(False)

        for key in self.base_vars:
            self.base_vars[key].set("")
        if ch.player is None:
            self.base_disabled_note.set(
                "No embedded player data (the character has not entered a world yet) — "
                "stats and skills are unavailable.")
            self.items_note.set("")
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
            cheated = sum(1 for _, c in ch.player["item_cheats"] if c)
            total = len(ch.player["item_cheats"])
            if cheated:
                self.items_note.set("Inventory: %d of %d items marked as cheated"
                                    % (cheated, total))
            else:
                self.items_note.set("Inventory: no cheater-marked items (%d items)" % total)

        self._rebuild_skill_rows()

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
            clear_item_cheats = bool(self.cheat_items_var.get())
        except ValueError as e:
            _err(str(e))
            return

        target = self.ch.path
        try:
            backup = save_character(self.ch, target, skills_levels,
                                    base_values, used_cheats, clear_item_cheats)
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
