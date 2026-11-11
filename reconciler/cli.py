"""Command line entry point.

    python -m reconciler.cli reconcile examples/asbuilt_FX-2231.reference.json \\
        examples/inventory_FX-2231.geojson --splices examples/inventory_splices_FX-2231.csv
    python -m reconciler.cli extract examples/asbuilt_FX-2231.pdf > records.json
    python -m reconciler.cli evaluate records.json examples/asbuilt_FX-2231.reference.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluate import score
from .extract import extract, read_source
from .inventory import load_inventory
from .reconcile import reconcile
from .report import corrections_csv, text_report


def cmd_reconcile(a) -> int:
    asbuilt = json.loads(Path(a.asbuilt).read_text())
    result = reconcile(asbuilt, load_inventory(a.inventory, a.splices), a.tolerance / 100)
    print(text_report(result))
    if a.csv:
        Path(a.csv).write_text(corrections_csv(result))
        print(f"\nCorrections written to {a.csv}")
    return 1 if result["counts"]["high"] else 0


def cmd_extract(a) -> int:
    json.dump(extract(read_source(a.source)), sys.stdout, indent=2)
    print()
    return 0


def cmd_evaluate(a) -> int:
    s = score(json.loads(Path(a.extracted).read_text()), json.loads(Path(a.reference).read_text()))
    print(f"Records: {s['records_found']} of {s['records_expected']} found, {s['records_extra']} extra")
    print(f"Fields:  {s['fields_correct']} of {s['fields_total']} correct ({s['field_accuracy'] * 100:.1f}%)")
    for m in s["misses"]:
        print("  " + m)
    return 0 if not s["misses"] and not s["records_extra"] else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reconciler", description="Compare as-built records with GIS inventory.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconcile", help="list disagreements between as-built records and inventory")
    r.add_argument("asbuilt"); r.add_argument("inventory"); r.add_argument("--splices")
    r.add_argument("--tolerance", type=float, default=5.0, help="allowed length difference, percent (default 5)")
    r.add_argument("--csv", help="write a corrections file for the GIS team")
    r.set_defaults(func=cmd_reconcile)
    e = sub.add_parser("extract", help="read notes (.txt or .pdf) into records with Claude")
    e.add_argument("source"); e.set_defaults(func=cmd_extract)
    v = sub.add_parser("evaluate", help="score an extraction against an answer key")
    v.add_argument("extracted"); v.add_argument("reference"); v.set_defaults(func=cmd_evaluate)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
