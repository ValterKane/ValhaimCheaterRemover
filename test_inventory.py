#!/usr/bin/env python3
import os
import struct
import sys
import tempfile

from valheim_character_editor import (
    Character, write_character, _uniques_with_rows, _parse_inv_rows_from_uniques,
    INV_ROWS_MIN, INV_ROWS_MAX,
)


def _base_values(ch):
    p = ch.profile
    blob = ch.body[p["blob_off"]:p["blob_off"] + p["blob_len"]]
    return {
        key: struct.unpack_from("<f", blob, off)[0]
        for key, off in ch.player["base"].items()
    }


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    sample = os.path.join(root, "abebra.fch")
    if not os.path.isfile(sample):
        print("test_inventory: skip (abebra.fch not found)")
        return 0

    ch = Character(sample)
    assert ch.player["inv_rows"] == 6, ch.player["inv_rows"]
    inv_uniques = [u for u in ch.player["uniques"] if u.startswith("invrows")
                   or u.startswith("invslot")]
    assert inv_uniques == ["invrows 6", "invslot1", "invslot2"], inv_uniques

    max_y = max(it["y"] for it in ch.player["inventory"])
    assert max_y == 5, max_y

    skills = {s["type"]: (s["level"], s["acc"]) for s in ch.skills}
    base = _base_values(ch)
    out = write_character(ch, skills, base, ch.profile["used_cheats"])
    assert out == bytes(ch.raw), "unchanged save should round-trip byte-identical"

    # Changing rows updates uniques only.
    out5 = write_character(ch, skills, base, ch.profile["used_cheats"], inv_rows=5)
    from valheim_character_editor import parse_profile, parse_blob
    datasz5 = struct.unpack_from("<i", out5, 0)[0]
    body5 = out5[4:4 + datasz5]
    prof5 = parse_profile(body5)
    blob5 = body5[prof5["blob_off"]:prof5["blob_off"] + prof5["blob_len"]]
    p5 = parse_blob(blob5)
    assert p5["inv_rows"] == 5, p5["inv_rows"]
    assert "invslot2" not in p5["uniques"]
    assert "invrows 5" in p5["uniques"]

    # Collect + save all items preserves extended slots.
    items = list(ch.player["inventory"])
    out_items = write_character(ch, skills, base, ch.profile["used_cheats"], items=items)
    with tempfile.NamedTemporaryFile(suffix=".fch", delete=False) as tmp:
        tmp.write(out_items)
        tmp_path = tmp.name
    try:
        ch2 = Character(tmp_path)
        assert ch2.player["inv_rows"] == 6
        assert len(ch2.player["inventory"]) == len(items)
        assert max(it["y"] for it in ch2.player["inventory"]) == 5
    finally:
        os.unlink(tmp_path)

    assert _parse_inv_rows_from_uniques(["invrows 5", "invslot1"]) == 5
    merged = _uniques_with_rows(["GP_Moder", "invrows 6", "invslot1", "invslot2"], 4)
    assert "invrows" not in " ".join(merged)
    assert merged == ["GP_Moder"]
    merged6 = _uniques_with_rows(["GP_Moder"], 6)
    assert "invrows 6" in merged6 and "invslot1" in merged6 and "invslot2" in merged6

    assert INV_ROWS_MIN == 4 and INV_ROWS_MAX == 6

    print("test_inventory: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
