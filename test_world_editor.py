#!/usr/bin/env python3
import os
import struct
import sys
import tempfile

import valheim_world_editor as w


def s(x):
    b = x.encode("utf-8")
    return bytes([len(b)]) + b


def build(keys):
    pkg = (struct.pack("<i", 41) + s("TestWorld") + s("ABCDEFGHIJ") +
           struct.pack("<i", 12345) + struct.pack("<q", 67890) +
           struct.pack("<i", 2) + b"\x01" +
           struct.pack("<i", len(keys)) + b"".join(s(k) for k in keys))
    return struct.pack("<i", len(pkg)) + pkg


def main():
    keys = ["deathkeepequip", "skillreductionrate 15", "resourcerate 200"]
    raw = build(keys)
    fd, path = tempfile.mkstemp(suffix=".fwl2")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(raw)
        world = w.World(path)
        assert world.name == "TestWorld", world.name
        assert world.seed_name == "ABCDEFGHIJ"
        assert world.seed == 12345
        assert world.uid == 67890
        assert world.keys == keys, world.keys
        assert world.to_bytes() == raw, "rebuild changed bytes"

        cur = world.current()
        assert cur["deathpenalty"] == "casual", cur
        assert cur["resources"] == "muchmore", cur
        assert cur["combat"] == "default", cur

        world.set_modifier("combat", "hard")
        assert "enemydamage 150" in world.keys
        assert "playerdamage 85" in world.keys
        assert "resourcerate 200" in world.keys, "other sliders untouched"
        assert "preset" not in " ".join(world.keys)

        world.set_modifier("deathpenalty", "hardcore")
        assert "skillreductionrate 15" not in world.keys, "old value removed"
        assert "deathkeepequip" not in world.keys, "old toggle removed"
        assert "deathskillsreset" in world.keys

        cur = world.current()
        assert cur["combat"] == "hard", cur
        assert cur["deathpenalty"] == "hardcore", cur

        before = list(world.keys)
        world.set_modifier("deathpenalty", "custom")
        assert world.keys == before, "custom must not touch the keys"

        note = world.save()
        assert note, "expected a backup"
        with open(path, "rb") as f:
            back = f.read()
        assert back == build(world.keys), "saved bytes differ from expected"
        assert w.World(path).current()["combat"] == "hard"

        world.set_modifier("combat", "default")
        assert not any(k.startswith(("playerdamage", "enemydamage",
                                     "enemyspeedsize", "enemyleveluprate"))
                       for k in world.keys), "normal must drop the keys"
        assert "deathskillsreset" in world.keys, "other sliders untouched"

        unknown = ["enemydamage 200"]
        assert w.current_options(unknown)["combat"] == "custom", \
            "partial key set must read as custom"

        print("test_world_editor: OK")
        return 0
    finally:
        for p in (path, path + ".bak"):
            if os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    sys.exit(main())
