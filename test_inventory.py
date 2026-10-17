#!/usr/bin/env python3
import hashlib
import os
import struct
import sys
import tempfile

import app_gui
import valheim_character_editor as c
import valheim_items
from valheim_character_editor import Character, inv_rows_for, inv_rows_from_uniques


def s(x):
    b = x.encode("utf-8")
    return bytes([len(b)]) + b


def item(h, x, y, cheated=False):
    return (struct.pack("<i", 100) + bytes([x, y, 0, 0x40]) +
            struct.pack("<i", h) + bytes([1 if cheated else 0]))


def build_blob(rows, items, version=33, tail=b""):
    # a minimal but structurally complete PlayerData blob
    b = bytearray()
    b += struct.pack("<i", version)                     # player data version
    b += struct.pack("<4f", 100.0, 100.0, 100.0, 0.0)   # health, stamina, tsd
    b += s("Eikthyr")                                   # guardian power
    b += struct.pack("<f", 0.0)                         # guardian power cooldown
    b += struct.pack("<i", 1)                           # inventory version
    b += struct.pack("<H", len(items)) + b"".join(item(*i) for i in items)
    b += struct.pack("<i", 0) * 4                       # four empty string lists
    # the fifth list is the global keys; "invrows N" sits in it
    b += struct.pack("<i", 2) + s("HildirMap") + s("invrows %d" % rows)
    b += struct.pack("<i", 0) * 3                       # three more
    b += s("") + s("")                                  # two loose strings
    b += bytes(24)                                      # two vec3
    b += struct.pack("<i", 0)
    b += struct.pack("<i", 0)
    b += struct.pack("<i", 2)                           # skills version
    b += struct.pack("<i", 1) + struct.pack("<iff", 1, 10.0, 0.5)
    b += struct.pack("<i", 0)
    b += struct.pack("<3f", 10.0, 10.0, 10.0)           # stamina, maxEitr, eitr
    b += struct.pack("<i", 0)                           # trailing byte block
    b += tail                                           # 1.0.20+ extra state
    return bytes(b)


def build_profile(blob, version=46):
    b = bytearray()
    b += struct.pack("<iii", version, 205, 1)  # profile version, stats, buckets
    b += bytes(4 * 205)                      # one float per stat
    b += struct.pack("<i", 0) * 9            # eight float dicts + sub count
    b += bytes([0])                          # first spawn
    b += struct.pack("<i", 0)                # no known worlds
    b += s("Tester") + struct.pack("<q", 1) + s("seed")
    b += bytes([0])                          # m_usedCheats
    b += struct.pack("<q", 1700000000)       # date created
    b += bytes([1])                          # has embedded player data
    b += struct.pack("<i", len(blob)) + blob
    return bytes(b)


def build_fch(rows, items, profile_version=46, data_version=33, tail=b""):
    body = build_profile(build_blob(rows, items, data_version, tail), profile_version)
    return (struct.pack("<i", len(body)) + body +
            struct.pack("<i", 64) + hashlib.sha512(body).digest())


def expect_parse_error(raw, path, needle):
    with open(path, "wb") as f:
        f.write(raw)
    try:
        Character(path)
    except c.ParseError as e:
        assert needle in str(e), str(e)
    else:
        raise AssertionError("accepted a file it should reject: %s" % needle)


class Stub:
    pass


def collect_as_gui(items, rows):
    # run the GUI's own collection slice, without a Tk root
    st = Stub()
    st.inv_items = {(i["x"], i["y"]): i for i in items}
    st.inv_rows = rows
    return app_gui.EditorApp._collect_inventory(st)


def test_item_roundtrip():
    # An item with every optional block: quality, stack, variant, crafter,
    # custom data, plus the game's own low flag bits. Re-encoding it from the
    # parsed fields must reproduce the bytes exactly.
    raw = (struct.pack("<i", 35000) + bytes([3, 1, 0, 0xFF]) +
           struct.pack("<HH", 4, 2) + struct.pack("<i", 7) +
           struct.pack("<q", 953783831) + s("Mikeyy") +
           struct.pack("<i", 1234) + bytes([1]) + s("k") + s("v") + bytes([1]))
    it = c.read_item(c.Reader(raw))
    assert (it["quality"], it["stack"], it["variant"]) == (4, 2, 7)
    assert (it["crafter_id"], it["crafter_name"]) == (953783831, "Mikeyy")
    assert it["custom"] == [("k", "v")] and it["cheated"]
    assert c._write_item(it) == raw, "item re-encoding is lossy"
    # editing a field keeps the extras
    it["stack"] = 1
    again = c.read_item(c.Reader(c._write_item(it)))
    assert again["stack"] == 1 and again["crafter_name"] == "Mikeyy"
    assert again["custom"] == [("k", "v")] and again["flags"] & 0x03 == 0x03
    # a plain new item from the GUI needs none of the optional keys
    assert c._write_item({"hash": 5, "x": 0, "y": 0, "stack": 1, "quality": 1,
                          "durability": 100}) == item(5, 0, 0)
    # a 3-byte varint string length still round-trips
    long = "x" * 300
    assert c.read_str(c._write_str(long), 0) == (long, len(c._write_str(long)))

    # moving a slot rewrites only x/y, inside the raw bytes too
    moved = app_gui.EditorApp._relocated(dict(it, raw=raw), (5, 2))
    assert (moved["x"], moved["y"]) == (5, 2) and moved["raw"][4:6] == bytes([5, 2])
    assert moved["raw"][6:] == raw[6:]
    assert app_gui.pretty_name("ArmorPaddedCuirass") == "Armor Padded Cuirass"
    assert app_gui.pretty_name("Fish4_cave") == "Fish 4 cave"
    assert app_gui.pretty_name("HelmetDrake") == "Helmet Drake"


def main():
    test_item_roundtrip()
    # Row count comes out of the "invrows N" global key.
    assert inv_rows_from_uniques(["GP_Eikthyr", "invrows 6"]) == 6
    assert inv_rows_from_uniques(["invrows 4"]) == 4
    assert inv_rows_from_uniques([]) == c.INV_ROWS_FALLBACK
    assert inv_rows_from_uniques(["invrows junk"]) == c.INV_ROWS_FALLBACK
    # a corrupt count can't size the grid past what a byte addresses
    assert inv_rows_from_uniques(["invrows 999999999"]) == c.INV_ROWS_MAX
    assert inv_rows_from_uniques(["invrows 0"]) == 1

    # items below the declared count raise it, so none are ever hidden
    assert inv_rows_for([{"y": 3}], 4) == 4
    assert inv_rows_for([{"y": 5}], 4) == 6
    assert inv_rows_for([{"y": 1}], 6) == 6
    assert inv_rows_for([], 4) == 4

    # (hash, x, y): two items sit in rows 4 and 5, one in the first row.
    slots = [(1, 0, 0), (2, 0, 4), (3, 1, 5)]
    want = [(0, 0), (0, 4), (1, 5)]
    raw = build_fch(6, slots)
    fd, path = tempfile.mkstemp(suffix=".fch")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(raw)
        ch = Character(path)
        assert ch.player["inv_rows"] == 6, ch.player["inv_rows"]
        assert sorted((i["x"], i["y"]) for i in ch.player["inventory"]) == want, \
            ch.player["inventory"]

        # The GUI slice used to drop everything past row 3.
        kept = collect_as_gui(ch.player["inventory"], ch.player["inv_rows"])
        assert len(kept) == 3, "rows 4-5 dropped by the GUI slice: %r" % (kept,)

        # Saving those items through the writer keeps them.
        out = c.write_character(ch, None, {}, ch.profile["used_cheats"],
                                False, list(kept))
        with open(path, "wb") as f:
            f.write(out)
        again = Character(path)
        assert sorted((i["x"], i["y"]) for i in again.player["inventory"]) == want, \
            again.player["inventory"]

        # A save that touches nothing must not change a single byte.
        with open(path, "wb") as f:
            f.write(raw)
        ch = Character(path)
        assert c.write_character(ch, None, {}, ch.profile["used_cheats"]) == raw, \
            "idle save changed the file"

        # A save declaring 4 rows but holding a row-5 item still keeps it.
        with open(path, "wb") as f:
            f.write(build_fch(4, [(1, 0, 0), (2, 0, 5)]))
        ch = Character(path)
        assert ch.player["inv_rows"] == 6, ch.player["inv_rows"]
        assert len(collect_as_gui(ch.player["inventory"], ch.player["inv_rows"])) == 2

        # Valheim 1.0.20: profile 47 / player data 34, with the drop-luck
        # state appended after the last field the editor edits. Issue #4.
        # Keys are prefab hash + chance in tenths of a percent.
        h = valheim_items.ITEM_NAME_TO_HASH
        tail = (struct.pack("<i", 3) +
                struct.pack("<ii", h["TrophyNeck"] + 50, 21) +
                struct.pack("<ii", h["TrophyHare"] + 100, 2) +
                struct.pack("<ii", 12345, 1) +                 # unknown prefab
                struct.pack("<i", 0))                           # empty 2nd list
        raw47 = build_fch(6, slots, 47, 34, tail)
        with open(path, "wb") as f:
            f.write(raw47)
        ch = Character(path)
        assert ch.player["version"] == 34
        drops = ch.player["drops"]
        assert [d["misses"] for d in drops] == [21, 2, 1], drops
        rev = valheim_items.ITEM_HASH_TO_NAME
        assert c.decode_drop_key(drops[0]["key"], rev) == ("TrophyNeck", 50)
        assert c.decode_drop_key(drops[1]["key"], rev) == ("TrophyHare", 100)
        assert c.decode_drop_key(drops[2]["key"], rev) == (None, None)
        # a garbage count can't blow up the parse; it just yields nothing
        junk = build_fch(6, slots, 47, 34, struct.pack("<i", 5) + b"\x01\x02")
        with open(path, "wb") as f:
            f.write(junk)
        assert Character(path).player["drops"] == []
        assert c.write_character(Character(path), None, {}, 0) == junk
        with open(path, "wb") as f:
            f.write(raw47)
        ch = Character(path)
        assert sorted((i["x"], i["y"]) for i in ch.player["inventory"]) == want
        assert c.write_character(ch, None, {}, ch.profile["used_cheats"]) == raw47, \
            "idle save of a 1.0.20 file changed it"
        # editing the inventory and skills keeps the unknown tail intact
        kept = collect_as_gui(ch.player["inventory"], ch.player["inv_rows"])
        out = c.write_character(ch, {1: (20.0, 0.0), 2: (5.0, 0.0)}, {"health": 50.0},
                                False, True, list(kept)[:2])
        assert out.endswith(tail + struct.pack("<i", 64) + hashlib.sha512(
            out[4:-68]).digest()), "tail lost on save"
        with open(path, "wb") as f:
            f.write(out)
        again = Character(path)
        assert len(again.player["inventory"]) == 2
        assert [s["type"] for s in again.skills] == [1, 2]

        # a 34 blob whose last length prefix overruns the data is still rejected
        short = build_blob(4, [], 34)[:-4] + struct.pack("<i", 99)
        body = build_profile(short, 47)
        expect_parse_error(struct.pack("<i", len(body)) + body + struct.pack("<i", 64) +
                           hashlib.sha512(body).digest(), path, "end mismatch")
        # a 33 blob with unexplained bytes at the end is still rejected
        expect_parse_error(build_fch(4, [], 46, 33, b"xx"), path, "end mismatch")
        # and versions past what we know stay refused with a clear message
        expect_parse_error(build_fch(4, [], 48, 34), path, "profile version 48")
        expect_parse_error(build_fch(4, [], 47, 35), path, "player data version 35")

        print("test_inventory: OK")
        return 0
    finally:
        for p in (path, path + ".bak"):
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    sys.exit(main())
