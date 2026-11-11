"""Read the GIS side: a GeoJSON export of cables and a CSV of splice records."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def load_inventory(geojson_path: str | Path, splices_csv: str | Path | None = None) -> dict:
    data = json.loads(Path(geojson_path).read_text())
    cables = []
    for f in data["features"]:
        p = f["properties"]
        if p.get("layer") != "cable":
            continue
        cables.append({
            "cable_id": p["cable_id"], "fiber_count": p.get("fiber_count"),
            "from": p.get("from_struct"), "to": p.get("to_struct"),
            "length_ft": p.get("length_ft"), "placement": p.get("placement"),
        })
    splices = []
    if splices_csv:
        with open(splices_csv, newline="") as fh:
            for r in csv.DictReader(fh):
                splices.append({
                    "closure_id": r["closure_id"], "structure": r["structure"],
                    "backbone_cable": r["backbone_cable"],
                    "backbone_fibers": [int(r["bb_start"]), int(r["bb_end"])],
                    "branch_cable": r["branch_cable"],
                    "branch_fibers": [int(r["br_start"]), int(r["br_end"])],
                })
    return {"cables": cables, "splices": splices}
