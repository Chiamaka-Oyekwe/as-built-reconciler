"""Score an extraction against a hand-made answer key, field by field."""
from __future__ import annotations

from .reconcile import norm

CABLE_FIELDS = ("fiber_count", "length_ft", "placement", "status")
SPLICE_FIELDS = ("structure", "backbone_fibers", "branch_fibers")


def _cable_key(c):
    if c.get("status") == "not_built":
        return (norm(c["cable_id"]), "not_built")
    return (norm(c["cable_id"]), frozenset((norm(c.get("from")), norm(c.get("to")))))


def _splice_key(s):
    return (norm(s["closure_id"]), norm(s["branch_cable"]))


def _same(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return norm(a) == norm(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.5
    return a == b


def score(extracted: dict, reference: dict) -> dict:
    """Records found, records invented, and the share of fields that match."""
    misses, correct, total, found, expected, extra = [], 0, 0, 0, 0, 0
    for name, key, fields in (("cables", _cable_key, CABLE_FIELDS), ("splices", _splice_key, SPLICE_FIELDS)):
        got = {key(r): r for r in extracted.get(name, [])}
        want = {key(r): r for r in reference.get(name, [])}
        expected += len(want)
        extra += len(set(got) - set(want))
        for k, w in want.items():
            label = f"{name[:-1]} {k[0]}"
            if k not in got:
                misses.append(f"{label}: not extracted")
                total += len(fields)
                continue
            found += 1
            for f in fields:
                total += 1
                if _same(got[k].get(f), w.get(f)):
                    correct += 1
                else:
                    misses.append(f"{label}: {f} is {got[k].get(f)!r}, expected {w.get(f)!r}")
    return {"records_expected": expected, "records_found": found, "records_extra": extra,
            "fields_correct": correct, "fields_total": total,
            "field_accuracy": round(correct / total, 4) if total else 1.0, "misses": misses}
