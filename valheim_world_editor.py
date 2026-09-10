#!/usr/bin/env python3
"""Read and edit Valheim 1.0 world settings (_main.N.fwl2).

The fwl2 is an int32 length followed by a ZPackage: version, name, seed,
seed value, uid, world-gen version, needs-db flag, then the list of starting
global-key strings.  World modifiers are those strings ("enemydamage 150",
"resourcerate 200").  Only that list is rewritten; the rest of the file is
kept byte-for-byte.
"""

import os
import re
import glob
import shutil
import struct

FILE_VERSION = 41
V_WORLD_GEN_VERSION = 26
V_NEEDS_DB = 30
V_GLOBAL_KEYS = 32


class WorldParseError(Exception):
    pass


def _read7(b, o):
    val = 0
    shift = 0
    while True:
        if o >= len(b):
            raise WorldParseError("truncated file")
        x = b[o]
        o += 1
        val |= (x & 0x7F) << shift
        if not (x & 0x80):
            return val, o
        shift += 7
        if shift > 35:
            raise WorldParseError("invalid string length")


def _write7(n):
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _read_str(b, o):
    n, o = _read7(b, o)
    if o + n > len(b):
        raise WorldParseError("truncated string")
    return b[o:o + n].decode("utf-8"), o + n


def _write_str(s):
    e = s.encode("utf-8")
    return _write7(len(e)) + e


# Exact key strings the game's own Server Options screen writes
# (StartGui_ServerOptions.prefab).  The game marks a world as cheated when a
# starting key is one that screen cannot produce, so only these are written.
SLIDERS = [
    {
        "id": "combat",
        "label": "Combat",
        "note": "Bosses scale with everything else - there is no separate knob.",
        "names": ["playerdamage", "enemydamage", "enemyspeedsize",
                  "enemyleveluprate"],
        "options": [
            ("veryeasy", "Very easy",
             ["playerdamage 125", "enemydamage 50", "enemyspeedsize 90"]),
            ("easy", "Easy",
             ["playerdamage 110", "enemydamage 75", "enemyspeedsize 95"]),
            ("default", "Normal", []),
            ("hard", "Hard",
             ["playerdamage 85", "enemydamage 150", "enemyspeedsize 110",
              "enemyleveluprate 120"]),
            ("veryhard", "Very hard",
             ["playerdamage 70", "enemydamage 200", "enemyspeedsize 120",
              "enemyleveluprate 140"]),
        ],
    },
    {
        "id": "deathpenalty",
        "label": "Death penalty",
        "note": "",
        "names": ["deathkeepequip", "skillreductionrate",
                  "deathdeleteunequipped", "deathdeleteitems",
                  "deathskillsreset"],
        "options": [
            ("casual", "Casual", ["deathkeepequip", "skillreductionrate 15"]),
            ("veryeasy", "Very easy", ["skillreductionrate 15"]),
            ("easy", "Easy", ["skillreductionrate 50"]),
            ("default", "Normal", []),
            ("hard", "Hard",
             ["deathdeleteunequipped", "skillreductionrate 150"]),
            ("hardcore", "Hardcore",
             ["deathdeleteitems", "deathskillsreset"]),
        ],
    },
    {
        "id": "resources",
        "label": "Resources",
        "note": "",
        "names": ["resourcerate"],
        "options": [
            ("muchless", "Much less", ["resourcerate 50"]),
            ("less", "Less", ["resourcerate 75"]),
            ("default", "Normal", []),
            ("more", "More", ["resourcerate 150"]),
            ("muchmore", "Much more", ["resourcerate 200"]),
            ("most", "Most", ["resourcerate 300"]),
        ],
    },
    {
        "id": "raids",
        "label": "Raids",
        "note": "",
        "names": ["eventrate"],
        "options": [
            ("none", "None", ["eventrate 0"]),
            ("default", "Normal", []),
            ("more", "More", ["eventrate 60"]),
            ("muchmore", "Much more", ["eventrate 30"]),
        ],
    },
    {
        "id": "portals",
        "label": "Portals",
        "note": "",
        "names": ["teleportall", "nobossportals", "noportals"],
        "options": [
            ("default", "Normal", []),
            ("teleportall", "Teleport everything", ["teleportall"]),
            ("nobossportals", "No boss portals", ["nobossportals"]),
            ("noportals", "No portals", ["noportals"]),
        ],
    },
]

CUSTOM = "custom"
CUSTOM_LABEL = "Custom (leave unchanged)"


def _key_name(key):
    return key.split(" ", 1)[0].lower()


def _slider(slider_id):
    for s in SLIDERS:
        if s["id"] == slider_id:
            return s
    raise KeyError(slider_id)


def match_option(slider, keys):
    present = set(k.lower() for k in keys)
    best_id = None
    best_n = 0
    for oid, _label, okeys in slider["options"]:
        if not okeys or not all(k.lower() in present for k in okeys):
            continue
        if len(okeys) > best_n:
            best_id, best_n = oid, len(okeys)
    if best_id is not None:
        return best_id
    owned = set(slider["names"])
    has_own = any(_key_name(k) in owned for k in keys)
    return CUSTOM if has_own else "default"


def current_options(keys):
    return {s["id"]: match_option(s, keys) for s in SLIDERS}


def apply_option(keys, slider_id, option_id):
    if option_id == CUSTOM:
        return None
    slider = _slider(slider_id)
    opt = next((o for o in slider["options"] if o[0] == option_id), None)
    if opt is None:
        return None
    names = set(slider["names"])
    out = [k for k in keys if _key_name(k) not in names]
    out.extend(opt[2])
    return out


class World:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        with open(self.path, "rb") as f:
            data = f.read()
        if len(data) < 8:
            raise WorldParseError("file too small to be a world (.fwl2)")
        pkg_len = struct.unpack_from("<i", data, 0)[0]
        if pkg_len < 0 or 4 + pkg_len > len(data):
            raise WorldParseError("invalid .fwl2 length prefix")
        self._extra = data[4 + pkg_len:]
        self.version = 0
        self.name = ""
        self.seed_name = ""
        self.seed = 0
        self.uid = 0
        self.world_gen_version = None
        self.needs_db = None
        self.keys = []
        self._parse(data[4:4 + pkg_len])

    def _i32(self, p, o):
        if o + 4 > len(p):
            raise WorldParseError("truncated world file")
        return struct.unpack_from("<i", p, o)[0], o + 4

    def _parse(self, p):
        self.version, o = self._i32(p, 0)
        if self.version != FILE_VERSION:
            raise WorldParseError(
                "world format version %d (this tool understands %d, the 1.0 "
                "save format)" % (self.version, FILE_VERSION))
        self.name, o = _read_str(p, o)
        self.seed_name, o = _read_str(p, o)
        self.seed, o = self._i32(p, o)
        if o + 8 > len(p):
            raise WorldParseError("truncated world file")
        self.uid = struct.unpack_from("<q", p, o)[0]
        o += 8
        if self.version >= V_WORLD_GEN_VERSION:
            self.world_gen_version, o = self._i32(p, o)
        if self.version >= V_NEEDS_DB:
            if o >= len(p):
                raise WorldParseError("truncated world file")
            self.needs_db = bool(p[o])
            o += 1
        self._head = p[:o]
        if self.version >= V_GLOBAL_KEYS:
            n, o = self._i32(p, o)
            if n < 0 or n > 100000:
                raise WorldParseError("unreasonable global key count (%d)" % n)
            for _ in range(n):
                key, o = _read_str(p, o)
                self.keys.append(key)
        self._foot = p[o:]

    def _package(self):
        return (self._head +
                struct.pack("<i", len(self.keys)) +
                b"".join(_write_str(k) for k in self.keys) +
                self._foot)

    def to_bytes(self):
        pkg = self._package()
        return struct.pack("<i", len(pkg)) + pkg + self._extra

    def current(self):
        return current_options(self.keys)

    def set_modifier(self, slider_id, option_id):
        new = apply_option(self.keys, slider_id, option_id)
        if new is not None:
            self.keys = new

    def save(self, target=None):
        target = target or self.path
        note = None
        if os.path.exists(target):
            bak = target + ".bak"
            n = 2
            while os.path.exists(bak):
                bak = target + ".bak%d" % n
                n += 1
            shutil.copy2(target, bak)
            note = os.path.basename(bak)
        with open(target, "wb") as f:
            f.write(self.to_bytes())
        return note


def save_num(path):
    m = re.search(r"_main\.(\d+)\.fwl2$", path)
    return int(m.group(1)) if m else -1


def find_world_file(path):
    if not path:
        return None
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return path if path.lower().endswith(".fwl2") else None
    if os.path.isdir(path):
        hits = glob.glob(os.path.join(path, "_main.*.fwl2"))
        return max(hits, key=save_num) if hits else None
    return None


def is_world_folder(path):
    return bool(find_world_file(path))


def selftest(world):
    with open(world.path, "rb") as f:
        original = f.read()
    out = world.to_bytes()
    ok = (out == original)
    print("world selftest rebuild: %s (%d bytes)"
          % ("OK" if ok else "FAILED", len(out)))
    return ok


def dump(world):
    print("World : %s" % world.name)
    print("Seed  : %s (%d)" % (world.seed_name, world.seed))
    print("File  : %s" % world.path)
    cur = world.current()
    for s in SLIDERS:
        oid = cur[s["id"]]
        label = next((o[1] for o in s["options"] if o[0] == oid), CUSTOM_LABEL)
        print("  %-14s %s" % (s["label"] + ":", label))
    owned = {n for s in SLIDERS for n in s["names"]}
    other = sorted(k for k in world.keys if _key_name(k) not in owned)
    if other:
        print("Other keys: %s" % ", ".join(other))


def main(argv):
    import sys
    if not argv:
        print("usage: valheim_world_editor.py <world folder or _main.N.fwl2> "
              "[--selftest]")
        return 1
    args = [a for a in argv if not a.startswith("--")]
    flags = set(a for a in argv if a.startswith("--"))
    for path in args:
        wf = find_world_file(path)
        if not wf:
            print("no _main.*.fwl2 found in %s" % path)
            return 1
        world = World(wf)
        if "--selftest" in flags:
            selftest(world)
        dump(world)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
