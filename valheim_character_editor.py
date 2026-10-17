#!/usr/bin/env python3
import struct, hashlib, sys, os, shutil, datetime

# Valheim 1.0.20 bumped both (46/33 -> 47/34) without changing the layout
# this editor reads; 34 only appends data after the last field we touch.
PROFILE_VERSIONS = (46, 47)
PLAYERDATA_VERSIONS = (33, 34)
INV_ROWS_FALLBACK = 4      # backpack rows before any upgrade
INV_ROWS_MAX = 256         # y is one byte, so no item can sit past row 255

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


def _fmt_versions(vs):
    return "%d-%d" % (min(vs), max(vs)) if len(vs) > 1 else str(vs[0])


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


def _read_num_items(r):
    b = r.byte()
    return ((b & 0x7F) << 8) | r.byte() if b & 0x80 else b


def read_item(r):
    # durability is fixed-point: hundredths of a point (10000 = 100.0)
    dur = r.i32()
    x = r.byte(); y = r.byte(); wl = r.byte()
    flags = r.byte()
    quality = r.u16() if flags & 4 else 1
    stack = r.u16() if flags & 8 else 1
    variant = r.i32() if flags & 0x10 else 0
    crafter_id, crafter_name = 0, ""
    if flags & 0x20:
        crafter_id = r.i64(); crafter_name = r.s()
    phash = r.i32() if flags & 0x40 else 0
    custom = []
    if flags & 0x80:
        for _ in range(_read_num_items(r)):
            k = r.s(); v = r.s()
            custom.append((k, v))
    cheated_off = r.o
    cheated = r.byte() & 1
    return {
        "hash": phash, "x": x, "y": y, "world_level": wl,
        "quality": quality, "stack": stack, "durability": dur,
        "variant": variant, "crafter_id": crafter_id, "crafter_name": crafter_name,
        "custom": custom, "flags": flags,
        "cheated": bool(cheated), "cheated_off": cheated_off,
    }


def parse_profile(body):
    r = Reader(body)
    ver = r.i32(); nstats = r.i32(); nbuckets = r.i32()
    if ver not in PROFILE_VERSIONS:
        raise ParseError("profile version %d (supported: %s - the current game)"
                         % (ver, _fmt_versions(PROFILE_VERSIONS)))
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


def inv_rows_from_uniques(uniques):
    for u in uniques:
        if u.startswith("invrows "):
            try:
                return max(1, min(INV_ROWS_MAX, int(u.split(" ", 1)[1])))
            except ValueError:
                pass
    return INV_ROWS_FALLBACK


def inv_rows_for(items, declared):
    # never lowered: an item past the declared count would be dropped on save
    deepest = max((int(it["y"]) for it in items), default=-1) + 1
    return max(declared, deepest)


def parse_blob(blob):
    r = Reader(blob)
    pd = r.i32()
    if pd not in PLAYERDATA_VERSIONS:
        raise ParseError("player data version %d (supported: %s)"
                         % (pd, _fmt_versions(PLAYERDATA_VERSIONS)))

    base = {}
    off = r.o
    base["maxHealth"] = off; r.f32()
    off = r.o; base["health"] = off; r.f32()
    off = r.o; base["maxStamina"] = off; r.f32()
    off = r.o; base["timeSinceDeath"] = off; r.f32()
    guardian_power, _ = r._skip_str()
    off = r.o; base["guardianPowerCooldown"] = off; r.f32()

    r.i32()
    inv_count_off = r.o
    n = r.u16()
    items = []
    for _ in range(n):
        start = r.o
        it = read_item(r)
        it["raw"] = bytes(blob[start:r.o])
        items.append(it)
    inv_items_end = r.o
    item_cheats = [(it["cheated_off"], it["cheated"]) for it in items]

    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s(); r.i32()
    for _ in range(r.i32()): r.s()
    for _ in range(r.i32()): r.s()
    # global keys; "invrows N" is one of them
    declared_rows = inv_rows_from_uniques([r.s() for _ in range(r.i32())])
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
    tail_off = r.o
    # Player data 34 (game 1.0.20) appends the drop-luck state past this
    # point. It is only ever read; every write below patches the blob in
    # place, so whatever sits there is kept byte for byte.
    if tail_off > len(blob) or (pd < 34 and tail_off != len(blob)):
        raise ParseError("player data end mismatch (%d of %d)" % (tail_off, len(blob)))
    drops = parse_drop_state(blob, tail_off) if pd >= 34 else []

    return {
        "base": base,
        "skills": skills,
        "guardian_power": guardian_power,
        "item_cheats": item_cheats,
        "inventory": items, "inv_rows": inv_rows_for(items, declared_rows),
        "inv_count_off": inv_count_off, "inv_items_end": inv_items_end,
        "sk_ver_off": sk_ver_off, "sk_count_off": sk_count_off,
        "sk_entries_off": sk_entries_off, "sk_end_off": sk_end_off,
        "version": pd, "tail_off": tail_off, "drops": drops,
    }


def parse_drop_state(blob, off):
    """The 1.0.20 tail: int32 count, then (int32 key, int32 misses) pairs.

    Key = stable hash of the drop prefab + drop chance in tenths of a percent,
    so one prefab shows up once per chance (star levels raise it). The value is
    how many rolls have missed in a row; the game keeps it across sessions so
    rare drops even out. Anything after the pairs is left undecoded."""
    try:
        r = Reader(blob)
        r.o = off
        n = r.i32()
        if not (0 <= n <= 100000):
            return []
        return [{"key": r.i32(), "misses": r.i32()} for _ in range(n)]
    except ParseError:
        return []


def decode_drop_key(key, hash_to_name):
    """Split a drop-state key into (prefab name, chance in tenths of a percent).

    Keys are the prefab's stable hash plus the per-mille chance, and chances
    are at most 1000, so the hash is whichever known one sits within that
    distance below the key. Unknown prefabs come back as (None, None)."""
    k = key & 0xffffffff
    for h, name in hash_to_name.items():
        d = (k - (h & 0xffffffff)) & 0xffffffff
        if 0 < d <= 1000:
            return name, d
    return None, None


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


def _write_str(s):
    body = s.encode("utf-8")
    n = len(body)
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out) + body


def _write_item(it):
    quality = int(it.get("quality", 1))
    stack = int(it.get("stack", 1))
    variant = int(it.get("variant", 0))
    crafter_id = int(it.get("crafter_id", 0))
    crafter_name = it.get("crafter_name", "") or ""
    custom = list(it.get("custom", []))
    # bits 0x01/0x02 are the game's own; keep whatever the item had
    flags = (int(it.get("flags", 0)) & 0x03) | 0x40
    if quality != 1:
        flags |= 4
    if stack != 1:
        flags |= 8
    if variant:
        flags |= 0x10
    if crafter_id or crafter_name:
        flags |= 0x20
    if custom:
        flags |= 0x80
    b = bytearray()
    b += struct.pack("<i", int(it["durability"]))
    b += bytes([it["x"], it["y"], it.get("world_level", 0), flags])
    if flags & 4:
        b += struct.pack("<H", quality)
    if flags & 8:
        b += struct.pack("<H", stack)
    if flags & 0x10:
        b += struct.pack("<i", variant)
    if flags & 0x20:
        b += struct.pack("<q", crafter_id) + _write_str(crafter_name)
    b += struct.pack("<i", it["hash"])
    if flags & 0x80:
        n = len(custom)
        b += bytes([0x80 | (n >> 8), n & 0xFF]) if n >= 0x80 else bytes([n])
        for k, v in custom:
            b += _write_str(k) + _write_str(v)
    b += bytes([1 if it.get("cheated") else 0])
    return bytes(b)


def _item_bytes(it):
    if "raw" in it:
        b = bytearray(it["raw"])
        b[-1] = 1 if it.get("cheated") else 0
        return bytes(b)
    return _write_item(it)


def write_character(ch, skills_levels, base_values, used_cheats, clear_item_cheats=False,
                    items=None):
    body = bytearray(ch.body)
    body[ch.profile["flag_off"]] = 1 if used_cheats else 0

    if ch.player is None:
        if base_values or skills_levels or items:
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

        if items is None and clear_item_cheats:
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

        if items is not None:
            if clear_item_cheats:
                for it in items:
                    it["cheated"] = False
            seg = struct.pack("<H", len(items)) + b"".join(_item_bytes(it) for it in items)
            blob[ch.player["inv_count_off"]:ch.player["inv_items_end"]] = seg

        new_body = (bytes(body[:ch.profile["blob_len_off"]]) +
                    struct.pack("<i", len(blob)) + bytes(blob))
    return (struct.pack("<i", len(new_body)) + new_body +
            struct.pack("<i", 64) + hashlib.sha512(new_body).digest())


def save_character(ch, target_path, skills_levels, base_values, used_cheats,
                   clear_item_cheats=False, items=None):
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
                           clear_item_cheats, items)
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
