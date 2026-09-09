#!/usr/bin/env python3
import struct, hashlib, sys, os, shutil, datetime

PROFILE_VERSION = 46
PLAYERDATA_VERSION = 33

SKILLS = {
    1: "Swords", 2: "Knives", 3: "Clubs", 4: "Polearms", 5: "Spears",
    6: "Blocking", 7: "Axes", 8: "Bows", 9: "ElementalMagic",
    10: "BloodMagic", 11: "Unarmed", 12: "Pickaxes", 13: "WoodCutting",
    14: "Crossbows", 100: "Jump", 101: "Sneak", 102: "Run", 103: "Swim",
    104: "Fishing", 105: "Cooking", 106: "Farming", 107: "Crafting",
    108: "Dodge", 110: "Ride",
}

BASE_FIELDS = [
    ("maxHealth", "Max health"),
    ("health", "Current health"),
    ("maxStamina", "Max stamina"),
    ("stamina", "Current stamina"),
    ("maxEitr", "Max eitr"),
    ("eitr", "Current eitr"),
    ("timeSinceDeath", "Time since death (sec)"),
    ("guardianPowerCooldown", "Guardian power cooldown (sec)"),
]


class ParseError(Exception):
    pass


def _varint(b, o):
    shift = 0
    val = 0
    while True:
        if o >= len(b):
            raise ParseError("truncated file: string length prefix")
        byte = b[o]; o += 1
        val |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return val, o
        shift += 7
        if shift > 28:
            raise ParseError("invalid string length prefix")


def read_str(b, o):
    n, o = _varint(b, o)
    if o + n > len(b):
        raise ParseError("truncated file: string body")
    return b[o:o + n].decode("utf-8", "replace"), o + n


class Reader:
    def __init__(self, b):
        self.b = b; self.o = 0
    def i32(self): return self._unpack("<i", 4)
    def i64(self): return self._unpack("<q", 8)
    def f32(self): return self._unpack("<f", 4)
    def u16(self): return self._unpack("<H", 2)
    def byte(self): return self._unpack("<B", 1)
    def s(self): return self._skip_str()[0]
    def _unpack(self, fmt, size):
        if self.o + size > len(self.b):
            raise ParseError("truncated file (position %d)" % self.o)
        v = struct.unpack_from(fmt, self.b, self.o)[0]
        self.o += size
        return v
    def _skip_str(self):
        s, self.o = read_str(self.b, self.o)
        return s, self.o
    def skip_vec3(self): self.o += 12
    def skip_item(self):
        self.i32()
        self.byte(); self.byte(); self.byte()
        flags = self.byte()
        if flags & 4: self.u16()
        if flags & 8: self.u16()
        if flags & 0x10: self.i32()
        if flags & 0x20: self.i64(); self.s()
        if flags & 0x40: self.i32()
        if flags & 0x80:
            cnt = self.byte()
            if cnt & 0x80:
                cnt = ((cnt & 0x7F) << 8) | self.byte()
            for _ in range(cnt):
                self.s(); self.s()
        off = self.o
        cheated = self.byte()
        return off, cheated


def skip_float_dict(r):
    cnt = r.i32()
    for _ in range(cnt):
        r.s(); r.f32()


def parse_profile(body):
    r = Reader(body)
    ver = r.i32(); nstats = r.i32(); nbuckets = r.i32()
    if ver != PROFILE_VERSION:
        raise ParseError("profile version %d (only %d is supported - the current game)"
                         % (ver, PROFILE_VERSION))
    if nstats != 205 or not (1 <= nbuckets <= 20):
        raise ParseError("unexpected parameters (stats=%d, buckets=%d)" % (nstats, nbuckets))
    for _ in range(nbuckets):
        r.o += 4 * nstats
        skip_float_dict(r)
        skip_float_dict(r)
        skip_float_dict(r)
        sub = r.i32()
        for _ in range(sub):
            skip_float_dict(r)
        skip_float_dict(r)
        skip_float_dict(r)
        skip_float_dict(r)
        skip_float_dict(r)
        skip_float_dict(r)
    first_spawn = r.byte()
    nworlds = r.i32()
    for _ in range(nworlds):
        r.i64()
        r.byte(); r.skip_vec3()
        r.byte(); r.skip_vec3()
        r.byte(); r.skip_vec3()
        r.skip_vec3()
        if r.byte():
            ln = r.i32(); r.o += ln
    name, _ = r._skip_str()
    player_id = r.i64()
    seed, _ = r._skip_str()

    flag_off = r.o
    used_cheats = r.byte()
    date_created = datetime.datetime.fromtimestamp(
        r.i64(), datetime.timezone.utc).date()

    has_data = r.byte()
    blob_len_off = blob_off = blob_len = None
    if has_data:
        blob_len_off = r.o
        blob_len = r.i32()
        blob_off = r.o
        r.o += blob_len
    if r.o != len(body):
        raise ParseError("profile end mismatch (%d of %d)" % (r.o, len(body)))
    return {
        "name": name, "player_id": player_id, "seed": seed,
        "first_spawn": first_spawn, "date_created": date_created,
        "flag_off": flag_off, "used_cheats": used_cheats,
        "has_data": has_data, "blob_len_off": blob_len_off,
        "blob_off": blob_off, "blob_len": blob_len,
    }


def parse_blob(blob):
    r = Reader(blob)
    pd = r.i32()
    if pd != PLAYERDATA_VERSION:
        raise ParseError("player data version %d (only %d is supported)"
                         % (pd, PLAYERDATA_VERSION))

    base = {}
    off = r.o
    base["maxHealth"] = off; r.f32()
    off = r.o; base["health"] = off; r.f32()
    off = r.o; base["maxStamina"] = off; r.f32()
    off = r.o; base["timeSinceDeath"] = off; r.f32()
    guardian_power, _ = r._skip_str()
    off = r.o; base["guardianPowerCooldown"] = off; r.f32()

    r.i32()
    n = r.u16()
    item_cheats = []
    for _ in range(n):
        off, cheated = r.skip_item()
        item_cheats.append((off, bool(cheated & 1)))

    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s(); r.i32()
    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s(); r.s()
    r.s(); r.s()
    r.skip_vec3(); r.skip_vec3()
    r.i32()
    for _ in range(r.i32()): r.s(); r.f32()

    sk_ver_off = r.o
    sk_ver = r.i32()
    if sk_ver != 2:
        raise ParseError("skills version %d (expected 2)" % sk_ver)
    sk_count_off = r.o
    sk_count = r.i32()
    sk_entries_off = r.o
    skills = []
    for _ in range(sk_count):
        t = r.i32()
        lvl_off = r.o; lvl = r.f32()
        acc_off = r.o; acc = r.f32()
        skills.append({"type": t, "level": lvl, "acc": acc,
                       "level_off": lvl_off, "acc_off": acc_off})
    sk_end_off = r.o

    for _ in range(r.i32()): r.s(); r.s()
    off = r.o; base["stamina"] = off; r.f32()
    off = r.o; base["maxEitr"] = off; r.f32()
    off = r.o; base["eitr"] = off; r.f32()
    ln = r.i32(); r.o += ln
    if r.o != len(blob):
        raise ParseError("player data end mismatch (%d of %d)" % (r.o, len(blob)))

    return {
        "base": base,
        "skills": skills,
        "guardian_power": guardian_power,
        "item_cheats": item_cheats,
        "sk_ver_off": sk_ver_off, "sk_count_off": sk_count_off,
        "sk_entries_off": sk_entries_off, "sk_end_off": sk_end_off,
    }


class Character:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        with open(self.path, "rb") as f:
            self.raw = bytearray(f.read())
        if len(self.raw) < 20:
            raise ParseError("file too small, does not look like a .fch")
        datasz = struct.unpack_from("<i", self.raw, 0)[0]
        if not (0 < datasz <= len(self.raw) - 8):
            raise ParseError("invalid .fch header")
        self.body = bytes(self.raw[4:4 + datasz])
        self.profile = parse_profile(self.body)
        if self.profile["has_data"]:
            blob = self.body[self.profile["blob_off"]:
                             self.profile["blob_off"] + self.profile["blob_len"]]
            self.player = parse_blob(blob)
        else:
            self.player = None

    @property
    def skills(self):
        return self.player["skills"] if self.player else []


def pack_f32(v):
    return struct.pack("<f", v)


def write_character(ch, skills_levels, base_values, used_cheats, clear_item_cheats=False):
    body = bytearray(ch.body)
    body[ch.profile["flag_off"]] = 1 if used_cheats else 0

    if ch.player is None:
        if base_values or skills_levels:
            raise ParseError("this character has no embedded player data - nothing to edit")
        new_body = bytes(body)
    else:
        blob = bytearray(body[ch.profile["blob_off"]:
                              ch.profile["blob_off"] + ch.profile["blob_len"]])
        for key, val in base_values.items():
            off = ch.player["base"].get(key)
            if off is None:
                raise ParseError("internal error: no field %s" % key)
            blob[off:off + 4] = pack_f32(val)

        if clear_item_cheats:
            for off, _ in ch.player["item_cheats"]:
                blob[off] &= ~1

        old = ch.player["skills"]
        old_map = {s["type"]: s for s in old}
        if skills_levels is not None and skills_levels.keys() != old_map.keys():
            entries = b"".join(
                struct.pack("<iff", t, lvl, acc)
                for t, (lvl, acc) in sorted(skills_levels.items()))
            blob[ch.player["sk_count_off"]:ch.player["sk_end_off"]] = (
                struct.pack("<i", len(skills_levels)) + entries)
        elif skills_levels is not None:
            for t, (lvl, acc) in skills_levels.items():
                s = old_map[t]
                blob[s["level_off"]:s["level_off"] + 4] = pack_f32(lvl)
                blob[s["acc_off"]:s["acc_off"] + 4] = pack_f32(acc)
        new_body = (bytes(body[:ch.profile["blob_len_off"]]) +
                    struct.pack("<i", len(blob)) + bytes(blob))
    return (struct.pack("<i", len(new_body)) + new_body +
            struct.pack("<i", 64) + hashlib.sha512(new_body).digest())


def save_character(ch, target_path, skills_levels, base_values, used_cheats,
                   clear_item_cheats=False):
    if os.path.exists(target_path):
        bak = target_path + ".bak"
        n = 2
        while os.path.exists(bak):
            bak = target_path + ".bak%d" % n
            n += 1
        shutil.copy2(target_path, bak)
        backup_note = os.path.basename(bak)
    else:
        backup_note = None
    data = write_character(ch, skills_levels, base_values, used_cheats,
                           clear_item_cheats)
    with open(target_path, "wb") as f:
        f.write(data)
    return backup_note


def _fmt_skill(s):
    name = SKILLS.get(s["type"], "Skill %d" % s["type"])
    return "%s: level %.0f, exp %.3f" % (name, s["level"], s["acc"])


def _dump_base(ch):
    blob = ch.body[ch.profile["blob_off"]:ch.profile["blob_off"] + ch.profile["blob_len"]]
    for key, label in BASE_FIELDS:
        off = ch.player["base"].get(key)
        if off is not None:
            val = struct.unpack_from("<f", blob, off)[0]
            print("  %-28s %.1f" % (label, val))


def dump(ch):
    p = ch.profile
    print("Character : %s (ID %d)" % (p["name"], p["player_id"]))
    print("Seed      : %s    created: %s" % (p["seed"], p["date_created"]))
    print("Cheater   : %s" % ("YES" if p["used_cheats"] else "no"))
    if ch.player is None:
        print("No embedded player data (the character never entered a world).")
        return
    _dump_base(ch)
    print("Guardian power: %s" % ch.player["guardian_power"])
    sk = ch.player["skills"]
    print("Skills (%d):" % len(sk))
    for s in sk:
        print("   " + _fmt_skill(s))


def selftest(ch, tmp):
    src = bytes(ch.raw)
    p = ch.profile
    skills_levels = {s["type"]: (s["level"], s["acc"]) for s in ch.skills}
    base = {}
    if ch.player:
        blob = src[4 + p["blob_off"]:4 + p["blob_off"] + p["blob_len"]]
        for key in ch.player["base"]:
            base[key] = struct.unpack_from("<f", blob, ch.player["base"][key])[0]
    out = write_character(ch, skills_levels, base, p["used_cheats"])
    ok = (out == src)
    print("selftest rebuild: %s (%d bytes)" % ("OK" if ok else "FAILED", len(out)))
    return ok


def main(argv):
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if not argv:
        import app_gui
        app_gui.run_gui()
        return
    args = [a for a in argv if not a.startswith("--")]
    flags = set(a for a in argv if a.startswith("--"))
    if not args:
        print("no file")
        return 1
    for path in args:
        ch = Character(path)
        if "--selftest" in flags:
            selftest(ch, path)
        dump(ch)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
