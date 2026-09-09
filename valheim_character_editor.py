#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valheim Character Editor (.fch v46).

Read/edit a Valheim 1.0 character file (PlayerProfile format v46):
- clear the Cheater flag (m_usedCheats),
- base stats from the embedded Player.Save (health/stamina/eitr/...),
- skills (level + experience), add/remove skills.

File layout:  [i32 size][ZPackage profile body][i32 64][SHA-512 of body].
Structures mirror the decompiled game code (assembly_valheim.dll):
PlayerProfile.SavePlayerToDisk / Player.Save / Inventory.Save / ItemData.Save.

Console:  python valheim_character_editor.py <file.fch> [--dump | --selftest]
GUI:      run without arguments (or drag & drop a file onto the program/exe).
"""
import struct, hashlib, sys, os, shutil, datetime

PROFILE_VERSION = 46
PLAYERDATA_VERSION = 33

# skill type -> display name
SKILLS = {
    1: "Swords", 2: "Knives", 3: "Clubs", 4: "Polearms", 5: "Spears",
    6: "Blocking", 7: "Axes", 8: "Bows", 9: "ElementalMagic",
    10: "BloodMagic", 11: "Unarmed", 12: "Pickaxes", 13: "WoodCutting",
    14: "Crossbows", 100: "Jump", 101: "Sneak", 102: "Run", 103: "Swim",
    104: "Fishing", 105: "Cooking", 106: "Farming", 107: "Crafting",
    108: "Dodge", 110: "Ride",
}

BASE_FIELDS = [
    # (key, label)
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


# ---------------------------------------------------------------- reading
def _varint(b, o):
    """7-bit string length prefix, as written by BinaryWriter.Write(string)."""
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
    """Sequential reader over a ZPackage-like stream."""
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

    # compound types
    def skip_vec3(self): self.o += 12
    def skip_item(self):
        """ItemData.Load (format >= Version.Item.Smaller, currently 109)."""
        self.i32()          # durability*100
        self.byte(); self.byte(); self.byte()   # gridPos.x/y, worldLevel
        flags = self.byte()
        if flags & 4: self.u16()        # quality
        if flags & 8: self.u16()        # stack
        if flags & 0x10: self.i32()     # variant
        if flags & 0x20: self.i64(); self.s()   # crafterID + name
        if flags & 0x40: self.i32()     # prefab hash
        if flags & 0x80:                # custom data (count in 1-2 bytes)
            cnt = self.byte()
            if cnt & 0x80:
                cnt = ((cnt & 0x7F) << 8) | self.byte()
            for _ in range(cnt):
                self.s(); self.s()
        self.byte()          # item cheated flags


def skip_float_dict(r):
    """[i32 count] * (string, f32)"""
    cnt = r.i32()
    for _ in range(cnt):
        r.s(); r.f32()


# ---------------------------------------------------------------- profile
def parse_profile(body):
    """Parse the profile body (v46). Returns a dict of offsets and fields.

    Stops after the m_playerData blob (the last field of the body).
    """
    r = Reader(body)
    ver = r.i32(); nstats = r.i32(); nbuckets = r.i32()
    if ver != PROFILE_VERSION:
        raise ParseError("profile version %d (only %d is supported - the current game)"
                         % (ver, PROFILE_VERSION))
    if nstats != 205 or not (1 <= nbuckets <= 20):
        raise ParseError("unexpected parameters (stats=%d, buckets=%d)" % (nstats, nbuckets))
    for _ in range(nbuckets):
        r.o += 4 * nstats
        skip_float_dict(r)          # m_knownWorlds
        skip_float_dict(r)          # m_knownWorldKeys
        skip_float_dict(r)          # m_knownCommands
        sub = r.i32()               # 5 x m_enemyStats
        for _ in range(sub):
            skip_float_dict(r)
        skip_float_dict(r)          # m_itemPickupStats
        skip_float_dict(r)          # m_itemCraftStats
        skip_float_dict(r)          # m_pickableStats
        skip_float_dict(r)          # m_foodEatenStats
        skip_float_dict(r)          # m_piecesPlacedStats
    first_spawn = r.byte()
    nworlds = r.i32()
    for _ in range(nworlds):        # m_worldData
        r.i64()                     # uid
        r.byte(); r.skip_vec3()     # custom spawn
        r.byte(); r.skip_vec3()     # logout
        r.byte(); r.skip_vec3()     # death
        r.skip_vec3()               # home
        if r.byte():                # mapData
            ln = r.i32(); r.o += ln
    name, _ = r._skip_str()
    player_id = r.i64()
    seed, _ = r._skip_str()

    flag_off = r.o                 # m_usedCheats (bool)
    used_cheats = r.byte()
    date_created = datetime.datetime.fromtimestamp(
        r.i64(), datetime.timezone.utc).date()  # UnixTimeSeconds

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


# ------------------------------------------------------- Player.Save blob
def parse_blob(blob):
    """Parse the embedded Player.Save (v33) in Player.Save() order.

    Returns: base - f32 field offsets, skills - description of the skills block.
    """
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

    # inventory: i32 version, u16 count, then items
    r.i32()
    n = r.u16()
    for _ in range(n):
        r.skip_item()

    # known recipes/stations/materials/tutorials/uniques/trophies/biomes/texts
    for _ in range(r.i32()): r.s()                       # knownRecipes
    for _ in range(r.i32()): r.s(); r.i32()              # knownStations
    for _ in range(r.i32()): r.s()                       # knownMaterial
    for _ in range(r.i32()): r.s()                       # shownTutorials
    for _ in range(r.i32()): r.s()                       # m_uniques
    for _ in range(r.i32()): r.s()                       # m_trophies
    for _ in range(r.i32()): r.s()                       # knownBiome
    for _ in range(r.i32()): r.s(); r.s()                # knownTexts
    r.s(); r.s()                                         # beard, hair
    r.skip_vec3(); r.skip_vec3()                         # skin and hair color
    r.i32()                                              # modelIndex
    for _ in range(r.i32()): r.s(); r.f32()              # food: name + time

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

    # customData + stamina/eitr + build panel binary
    for _ in range(r.i32()): r.s(); r.s()
    off = r.o; base["stamina"] = off; r.f32()
    off = r.o; base["maxEitr"] = off; r.f32()
    off = r.o; base["eitr"] = off; r.f32()
    ln = r.i32(); r.o += ln                              # m_buildUi
    if r.o != len(blob):
        raise ParseError("player data end mismatch (%d of %d)" % (r.o, len(blob)))

    return {
        "base": base,
        "skills": skills,
        "guardian_power": guardian_power,
        "sk_ver_off": sk_ver_off, "sk_count_off": sk_count_off,
        "sk_entries_off": sk_entries_off, "sk_end_off": sk_end_off,
    }


# ------------------------------------------------------------- opening
class Character:
    """An opened .fch: original bytes + parsed structure."""
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


# ------------------------------------------------------------- writing
def pack_f32(v):
    return struct.pack("<f", v)


def write_character(ch, skills_levels, base_values, used_cheats):
    """Assemble a new .fch from the model. Returns a bytearray of the file.

    skills_levels: {skill_type: (level, exp)} - the target set of skills.
    base_values:   {key: float} - base field edits (by offsets from ch).
    used_cheats:   target value of the flag.
    """
    body = bytearray(ch.body)
    body[ch.profile["flag_off"]] = 1 if used_cheats else 0

    if ch.player is None:
        if base_values or skills_levels:
            raise ParseError("this character has no embedded player data - nothing to edit")
        new_body = bytes(body)
    else:
        blob = bytearray(body[ch.profile["blob_off"]:
                              ch.profile["blob_off"] + ch.profile["blob_len"]])
        b_off = ch.profile["blob_off"]
        for key, val in base_values.items():
            off = ch.player["base"].get(key)
            if off is None:
                raise ParseError("internal error: no field %s" % key)
            blob[off:off + 4] = pack_f32(val)

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


def save_character(ch, target_path, skills_levels, base_values, used_cheats):
    """Write with a backup kept next to the file (never overwrites a .bak)."""
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
    data = write_character(ch, skills_levels, base_values, used_cheats)
    with open(target_path, "wb") as f:
        f.write(data)
    return backup_note


# ------------------------------------------------------------- console
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
    """Check: rebuilding without edits yields a byte-identical file."""
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
