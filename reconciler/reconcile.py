"""Compare as-built records with inventory records and list every disagreement.

No model is involved here. Same inputs, same findings, every time.
"""
from __future__ import annotations

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def norm(value):
    return value.strip().upper().replace(" ", "") if isinstance(value, str) else value


def _cable(c: dict) -> dict:
    return {**c, "cable_id": norm(c.get("cable_id")), "from": norm(c.get("from")), "to": norm(c.get("to"))}


def _ends(c: dict) -> frozenset:
    return frozenset((c["from"], c["to"]))


def _rng(r) -> str:
    return f"{r[0]}-{r[1]}" if r else "none"


def _finding(code, severity, record, field, asbuilt, inventory, message, fix, where=None):
    return {"code": code, "severity": severity, "record": record, "field": field,
            "asbuilt": asbuilt, "inventory": inventory, "message": message, "fix": fix, "where": where or {}}


def reconcile(asbuilt: dict, inventory: dict, tolerance: float = 0.05) -> dict:
    """Return findings plus counts. `tolerance` is the allowed length difference (0.05 = 5%)."""
    all_a = [_cable(c) for c in asbuilt.get("cables", [])]
    built = [c for c in all_a if c.get("status", "built") != "not_built"]
    not_built = {c["cable_id"] for c in all_a if c.get("status") == "not_built"}
    inv = [_cable(c) for c in inventory.get("cables", [])]

    used_a, used_i, pairs = set(), set(), []

    def free_a():
        return [k for k in range(len(built)) if k not in used_a]

    def free_i():
        return [k for k in range(len(inv)) if k not in used_i]

    def pair(ka, ki, how):
        used_a.add(ka); used_i.add(ki); pairs.append((ka, ki, how))

    # 1. Same cable id and same two endpoints.
    for ka in free_a():
        for ki in free_i():
            if inv[ki]["cable_id"] == built[ka]["cable_id"] and _ends(inv[ki]) == _ends(built[ka]):
                pair(ka, ki, "exact"); break
    # 2. Same cable id, one unmatched record on each side: the endpoints moved.
    for ka in free_a():
        cid = built[ka]["cable_id"]
        ca = [k for k in free_a() if built[k]["cable_id"] == cid]
        ci = [k for k in free_i() if inv[k]["cable_id"] == cid]
        if len(ca) == 1 and len(ci) == 1:
            pair(ka, ci[0], "endpoint")
    # 3. Same endpoints, different id: probably the same cable under another name.
    alias = {}
    for ka in free_a():
        ci = [k for k in free_i() if _ends(inv[k]) == _ends(built[ka])]
        if len(ci) == 1:
            alias[inv[ci[0]]["cable_id"]] = built[ka]["cable_id"]
            pair(ka, ci[0], "rename")

    findings = []
    for ka, ki, how in sorted(pairs):
        a, i = built[ka], inv[ki]
        record = f"{a['cable_id']} {a['from']} to {a['to']}"
        where = {"cable_id": a["cable_id"], "from": a["from"], "to": a["to"]}
        if how == "rename":
            findings.append(_finding("ID_MISMATCH", "low", record, "cable_id", a["cable_id"], i["cable_id"],
                f"Same endpoints, different name: as-built calls it {a['cable_id']}, inventory calls it {i['cable_id']}.",
                f"Confirm they are the same cable, then rename {i['cable_id']} or record the alias.", where))
        if how == "endpoint":
            findings.append(_finding("ENDPOINT", "medium", record, "endpoints", f"{a['from']} to {a['to']}", f"{i['from']} to {i['to']}",
                f"{a['cable_id']} was built {a['from']} to {a['to']}. Inventory shows {i['from']} to {i['to']}.",
                f"Move {a['cable_id']} in GIS to {a['from']} to {a['to']} and update its length to {a.get('length_ft')} ft.",
                {**where, "inv_from": i["from"], "inv_to": i["to"]}))
        if a.get("fiber_count") is not None and i.get("fiber_count") is not None and a["fiber_count"] != i["fiber_count"]:
            findings.append(_finding("FIBER_COUNT", "high", record, "fiber_count", a["fiber_count"], i["fiber_count"],
                f"{a['cable_id']} was built as {a['fiber_count']}F. Inventory shows {i['fiber_count']}F.",
                f"Set fiber_count to {a['fiber_count']} and add the new strands to the fiber records.", where))
        if how != "endpoint" and a.get("length_ft") and i.get("length_ft"):
            diff = abs(a["length_ft"] - i["length_ft"]) / i["length_ft"]
            if diff > tolerance:
                findings.append(_finding("LENGTH", "medium", record, "length_ft", a["length_ft"], i["length_ft"],
                    f"Length is off by {diff * 100:.1f}%: {a['length_ft']} ft built, {i['length_ft']} ft in inventory.",
                    f"Set length_ft to {a['length_ft']} and redraw the route if it changed.", where))
        if a.get("placement") and i.get("placement") and a["placement"] != i["placement"]:
            findings.append(_finding("PLACEMENT", "medium", record, "placement", a["placement"], i["placement"],
                f"Built {a['placement']}. Inventory shows {i['placement']}.",
                f"Set placement to {a['placement']} and attach the span to the right support structure.", where))

    for ka in free_a():
        a = built[ka]
        findings.append(_finding("MISSING_IN_INVENTORY", "high", f"{a['cable_id']} {a['from']} to {a['to']}", "record",
            f"{a.get('fiber_count')}F, {a.get('length_ft')} ft", "none",
            f"{a['cable_id']} was built and is not in the inventory.",
            f"Add {a['cable_id']} ({a.get('fiber_count')}F, {a['from']} to {a['to']}, {a.get('length_ft')} ft).",
            {"cable_id": a["cable_id"], "from": a["from"], "to": a["to"]}))
    for ki in free_i():
        i = inv[ki]
        cancelled = i["cable_id"] in not_built
        findings.append(_finding("NOT_BUILT" if cancelled else "NOT_IN_ASBUILT", "medium",
            f"{i['cable_id']} {i['from']} to {i['to']}", "record", "not built" if cancelled else "no record", f"{i.get('fiber_count')}F, {i.get('length_ft')} ft",
            f"{i['cable_id']} is in the inventory. " + ("The as-built says it was not built." if cancelled else "The as-built does not mention it."),
            f"Remove {i['cable_id']} or mark it as not built." if cancelled else f"Ask the field whether {i['cable_id']} exists before changing GIS.",
            {"cable_id": i["cable_id"], "from": i["from"], "to": i["to"], "inventory_only": True}))

    # Splices, matched on the branch cable they serve.
    sa = {norm(s["branch_cable"]): s for s in asbuilt.get("splices", [])}
    si = {alias.get(norm(s["branch_cable"]), norm(s["branch_cable"])): s for s in inventory.get("splices", [])}
    for br, a in sa.items():
        at = f"{norm(a['closure_id'])} at {norm(a['structure'])}"
        where = {"structure": norm(a["structure"]), "cable_id": br}
        if br not in si:
            findings.append(_finding("SPLICE_MISSING_IN_INVENTORY", "high", f"Splice to {br}", "record",
                f"{at}: backbone {_rng(a['backbone_fibers'])} to {br} {_rng(a['branch_fibers'])}", "none",
                f"The splice feeding {br} is not in the inventory.",
                f"Add the splice at {at}: backbone {_rng(a['backbone_fibers'])} to {br} {_rng(a['branch_fibers'])}.", where))
            continue
        i = si[br]
        diffs = []
        if norm(a["structure"]) != norm(i["structure"]) or norm(a["closure_id"]) != norm(i["closure_id"]):
            diffs.append(f"location {at} vs {norm(i['closure_id'])} at {norm(i['structure'])}")
        if list(a["backbone_fibers"]) != list(i["backbone_fibers"]):
            diffs.append(f"backbone fibers {_rng(a['backbone_fibers'])} vs {_rng(i['backbone_fibers'])}")
        if list(a["branch_fibers"]) != list(i["branch_fibers"]):
            diffs.append(f"branch fibers {_rng(a['branch_fibers'])} vs {_rng(i['branch_fibers'])}")
        if diffs:
            findings.append(_finding("SPLICE_MISMATCH", "high", f"Splice to {br}", "fiber assignment",
                f"{at}: backbone {_rng(a['backbone_fibers'])} to {br} {_rng(a['branch_fibers'])}",
                f"{norm(i['closure_id'])} at {norm(i['structure'])}: backbone {_rng(i['backbone_fibers'])} to {br} {_rng(i['branch_fibers'])}",
                f"Fiber assignment for {br} disagrees (as-built vs inventory): " + "; ".join(diffs) + ".",
                f"Update the splice record to {at}, backbone {_rng(a['backbone_fibers'])} to {br} {_rng(a['branch_fibers'])}. Check circuits assigned on the old fibers.", where))
    for br, i in si.items():
        if br not in sa:
            findings.append(_finding("SPLICE_NOT_IN_ASBUILT", "medium" if br in not_built else "high", f"Splice to {br}", "record", "no record",
                f"{norm(i['closure_id'])} at {norm(i['structure'])}: backbone {_rng(i['backbone_fibers'])}",
                f"Inventory has a splice feeding {br}. The as-built has none.",
                "Remove it with the cable." if br in not_built else "Confirm in the field before assigning these fibers.",
                {"structure": norm(i["structure"]), "cable_id": br}))

    # The as-built itself must not put one backbone fiber on two branches.
    spl = asbuilt.get("splices", [])
    for x in range(len(spl)):
        for y in range(x + 1, len(spl)):
            a, b = spl[x], spl[y]
            if norm(a["backbone_cable"]) == norm(b["backbone_cable"]) and a["backbone_fibers"][0] <= b["backbone_fibers"][1] and b["backbone_fibers"][0] <= a["backbone_fibers"][1]:
                findings.append(_finding("DOUBLE_ASSIGNED", "high", f"{norm(a['backbone_cable'])} fibers", "backbone_fibers",
                    f"{_rng(a['backbone_fibers'])} to {norm(a['branch_cable'])} and {_rng(b['backbone_fibers'])} to {norm(b['branch_cable'])}", "n/a",
                    f"The as-built puts overlapping backbone fibers on {norm(a['branch_cable'])} and {norm(b['branch_cable'])}.",
                    "Send back to the splicer. One of the two records is wrong.", {"structure": norm(a["structure"])}))

    findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])
    for n, f in enumerate(findings, 1):
        f["n"] = n
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}
    return {"findings": findings, "counts": counts, "cables_compared": len(pairs),
            "splices_compared": len(set(sa) & set(si)), "aliases": alias}
