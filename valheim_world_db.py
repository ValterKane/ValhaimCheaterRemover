#!/usr/bin/env python3
"""Scan and patch cheated ItemData flags inside Valheim world save files."""

import glob
import os
import re
import shutil
import struct

from valheim_character_editor import ParseError, Reader, _varint, read_item

INV_VERSION = 109
MAX_INV_ITEMS = 128
MIN_ITEM_BYTES = 13
_INV_MARKER = struct.pack("<i", INV_VERSION)


class WorldDbError(Exception):
    pass


def save_num(path):
    m = re.search(r"_main\.(\d+)\.(?:fwl2|db2?)$", path, re.I)
    return int(m.group(1)) if m else -1


def _db_candidates(folder, fwl2_path=None):
    folder = os.path.abspath(folder)
    if fwl2_path:
        n = save_num(fwl2_path)
        if n >= 0:
            for ext in (".db2", ".db"):
                p = os.path.join(folder, "_main.%d%s" % (n, ext))
                if os.path.isfile(p):
                    yield p
    for ext in (".db2", ".db"):
        for p in glob.glob(os.path.join(folder, "_main.*%s" % ext)):
            yield p


def find_db_file(path, fwl2_path=None):
    if not path:
        return None
    path = os.path.abspath(path)
    if os.path.isfile(path):
        low = path.lower()
        if low.endswith((".db", ".db2")):
            return path
        if low.endswith(".fwl2"):
            return find_db_file(os.path.dirname(path), path)
        return None
    if os.path.isdir(path):
        seen = set()
        for p in _db_candidates(path, fwl2_path):
            if p not in seen:
                seen.add(p)
                return p
    return None


def world_data_files(fwl2_path):
    folder = os.path.dirname(os.path.abspath(fwl2_path))
    files = []
    seen = set()
    db = find_db_file(folder, fwl2_path)
    if db:
        files.append(db)
        seen.add(db)
    for p in sorted(glob.glob(os.path.join(folder, "*.chunk"))):
        if p not in seen:
            files.append(p)
            seen.add(p)
    return files


def db_for_world(fwl2_path):
    return find_db_file(os.path.dirname(os.path.abspath(fwl2_path)), fwl2_path)


def iter_embedded_strings(data):
    o = 0
    n = len(data)
    while o < n:
        try:
            length, body_start = _varint(data, o)
        except ParseError:
            o += 1
            continue
        if length <= 0 or body_start + length > n:
            o += 1
            continue
        yield body_start, length, body_start + length
        o = body_start + length


def _item_ok(it):
    if it["stack"] < 1 or it["stack"] > 9999:
        return False
    if it["quality"] < 1 or it["quality"] > 20:
        return False
    if it["x"] > 32 or it["y"] > 32:
        return False
    return True


def _parse_inventory_from(data, start, require_eof=False):
    if start + 6 > len(data):
        return None
    ver = struct.unpack_from("<i", data, start)[0]
    if ver != INV_VERSION:
        return None
    count = struct.unpack_from("<H", data, start + 4)[0]
    if count <= 0 or count > MAX_INV_ITEMS:
        return None
    r = Reader(data)
    r.o = start + 6
    items = []
    try:
        for _ in range(count):
            it = read_item(r)
            if not _item_ok(it):
                return None
            items.append(it)
    except ParseError:
        return None
    end = r.o
    if require_eof and end != len(data):
        return None
    return items, end


def _parse_single_item_from(data, start, require_eof=False):
    if start + 8 > len(data):
        return None
    r = Reader(data)
    r.o = start
    try:
        it = read_item(r)
    except ParseError:
        return None
    if not _item_ok(it):
        return None
    end = r.o
    if require_eof and end != len(data):
        return None
    return [it], end


def _ranges_overlap(a_start, a_end, ranges):
    for b_start, b_end in ranges:
        if a_start < b_end and a_end > b_start:
            return True
    return False


def _record_place(places, claimed, start, end, kind, items):
    offs = [it["cheated_off"] for it in items if it.get("cheated")]
    if not offs or _ranges_overlap(start, end, claimed):
        return False
    claimed.append((start, end))
    places.append({
        "body_start": start,
        "body_end": end,
        "kind": kind,
        "items": len(items),
        "cheated": len(offs),
        "cheated_offs": offs,
    })
    return True


def _scan_binary(data, places, claimed):
    n = len(data)
    i = 0
    while i >= 0 and i < n - 8:
        j = data.find(_INV_MARKER, i)
        if j < 0:
            break
        inv = _parse_inventory_from(data, j, require_eof=False)
        if inv is not None:
            items, end = inv
            _record_place(places, claimed, j, end, "inventory", items)
            i = max(j + 1, end)
        else:
            i = j + 1



def scan_bytes(data):
    places = []
    claimed = []
    seen = set()
    for body_start, _length, body_end in iter_embedded_strings(data):
        if (body_start, body_end) in seen:
            continue
        body = data[body_start:body_end]
        inv = _parse_inventory_from(body, 0, require_eof=True)
        if inv is not None:
            items, _end = inv
            offs = [body_start + it["cheated_off"] for it in items if it.get("cheated")]
            if offs:
                seen.add((body_start, body_end))
                places.append({
                    "body_start": body_start,
                    "body_end": body_end,
                    "kind": "inventory",
                    "items": len(items),
                    "cheated": len(offs),
                    "cheated_offs": offs,
                })
            continue
        single = _parse_single_item_from(body, 0, require_eof=True)
        if single is not None:
            items, _end = single
            offs = [body_start + it["cheated_off"] for it in items if it.get("cheated")]
            if offs:
                seen.add((body_start, body_end))
                places.append({
                    "body_start": body_start,
                    "body_end": body_end,
                    "kind": "item",
                    "items": len(items),
                    "cheated": len(offs),
                    "cheated_offs": offs,
                })
    for place in places:
        claimed.append((place["body_start"], place["body_end"]))
    _scan_binary(data, places, claimed)
    cheated_items = len({off for p in places for off in p["cheated_offs"]})
    return places, cheated_items


def scan_file(path):
    with open(path, "rb") as f:
        data = f.read()
    places, cheated_items = scan_bytes(data)
    return {
        "path": os.path.abspath(path),
        "size": len(data),
        "places": places,
        "cheated_items": cheated_items,
        "place_count": len(places),
    }


def scan_db(path):
    return scan_file(path)


def scan_world(fwl2_path):
    files = world_data_files(fwl2_path)
    reports = [scan_file(p) for p in files]
    cheated_items = sum(r["cheated_items"] for r in reports)
    place_count = sum(r["place_count"] for r in reports)
    return {
        "files": files,
        "reports": reports,
        "cheated_items": cheated_items,
        "place_count": place_count,
    }


def clear_cheated_in_file(path):
    with open(path, "rb") as f:
        data = bytearray(f.read())
    report = scan_file(path)
    if report["cheated_items"] == 0:
        return report, None

    cleared = 0
    for off in {off for p in report["places"] for off in p["cheated_offs"]}:
        if data[off] & 1:
            data[off] &= ~1
            cleared += 1

    backup = None
    if os.path.exists(path):
        bak = path + ".bak"
        n = 2
        while os.path.exists(bak):
            bak = path + ".bak%d" % n
            n += 1
        shutil.copy2(path, bak)
        backup = os.path.basename(bak)

    with open(path, "wb") as f:
        f.write(data)

    report["cleared"] = cleared
    return report, backup


def clear_cheated_in_db(path):
    return clear_cheated_in_file(path)


def clear_cheated_in_world(fwl2_path):
    summary = scan_world(fwl2_path)
    if summary["cheated_items"] == 0:
        return summary, []

    backups = []
    total_cleared = 0
    for rep in summary["reports"]:
        if rep["cheated_items"] == 0:
            continue
        patched, backup = clear_cheated_in_file(rep["path"])
        total_cleared += patched.get("cleared", 0)
        if backup:
            backups.append((rep["path"], backup))
    summary["cleared"] = total_cleared
    return summary, backups
