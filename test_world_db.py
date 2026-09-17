#!/usr/bin/env python3
import os
import struct
import sys
import tempfile

from valheim_character_editor import _write_item, _write_varint, write_str
from valheim_world_db import (
    clear_cheated_in_db, db_for_world, find_db_file, scan_bytes, scan_db,
)


def _write_blob(blob):
    return _write_varint(len(blob)) + blob


def _inventory_blob(items):
    seg = struct.pack("<i", 109) + struct.pack("<H", len(items))
    seg += b"".join(_write_item(it) for it in items)
    return seg


def main():
    it_ok = {"hash": -151837501, "x": 1, "y": 0, "stack": 10, "quality": 1,
             "durability": 5000, "cheated": False, "world_level": 0}
    it_bad = dict(it_ok, x=2, cheated=True)
    inv = _inventory_blob([it_ok, it_bad])

    # Wrap inventory as a ZPackage string inside fake .db bytes.
    fake_db = b"\x00" * 40 + write_str("noise") + _write_blob(inv) + b"\xff" * 20

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(fake_db)
        before_size = len(fake_db)

        places, cheated = scan_bytes(fake_db)
        assert cheated == 1, (cheated, places)
        report = scan_db(path)
        assert report["cheated_items"] == 1, report
        assert report["place_count"] == 1, report

        report2, backup = clear_cheated_in_db(path)
        assert backup, "expected backup"
        assert report2.get("cleared") == 1

        with open(path, "rb") as f:
            after = f.read()
        assert len(after) == before_size, "patch must not change file size"

        report3 = scan_db(path)
        assert report3["cheated_items"] == 0, report3

        # find_db_file pairs fwl2/db by save number
        d = tempfile.mkdtemp()
        try:
            fwl2 = os.path.join(d, "_main.3.fwl2")
            db2 = os.path.join(d, "_main.3.db2")
            db = os.path.join(d, "_main.3.db")
            open(fwl2, "wb").close()
            open(db2, "wb").close()
            assert find_db_file(d, fwl2) == db2
            assert db_for_world(fwl2) == db2
            open(db, "wb").close()
            assert find_db_file(d, fwl2) == db2
        finally:
            for name in os.listdir(d):
                os.remove(os.path.join(d, name))
            os.rmdir(d)

        print("test_world_db: OK")
        return 0
    finally:
        for p in (path, path + ".bak"):
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    sys.exit(main())
