#!/usr/bin/env python3
import sys

import valheim_items as items_db
from valheim_character_editor import Reader, read_item, _write_item


def main():
    # Hash table spot-checks (values verified against a real 1.0 save).
    for name, h in (("Wood", -151837501), ("Stone", -535531945),
                    ("SwordIron", -110263489), ("IronOre", 411615136),
                    ("CookedMeat", -90783900), ("ArrowFire", -1917784535)):
        assert items_db.ITEM_NAME_TO_HASH.get(name) == h, (name, items_db.ITEM_NAME_TO_HASH.get(name))
        assert items_db.ITEM_HASH_TO_NAME.get(h) == name

    # Serialize -> reparse round-trip for a full item.
    it = {"hash": -151837501, "x": 3, "y": 1, "stack": 50, "quality": 2,
          "durability": 10000, "cheated": False, "world_level": 0}
    r = Reader(_write_item(it))
    got = read_item(r)
    assert r.o == len(_write_item(it)), "leftover bytes"
    assert got["hash"] == it["hash"] and got["x"] == 3 and got["y"] == 1
    assert got["stack"] == 50 and got["quality"] == 2
    assert got["durability"] == 10000 and got["cheated"] is False

    # Minimal item (stack=1, quality=1 -> no extra fields) and cheated flag.
    r = Reader(_write_item({"hash": 1, "x": 0, "y": 0, "stack": 1,
                            "quality": 1, "durability": 0, "cheated": True}))
    got = read_item(r)
    assert got["stack"] == 1 and got["quality"] == 1 and got["cheated"] is True

    print("test_items: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
