"""Turn findings into something a GIS tech can work from."""
from __future__ import annotations

import csv
import io


def corrections_csv(result: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["n", "severity", "record", "field", "inventory_value", "asbuilt_value", "action"])
    for f in result["findings"]:
        w.writerow([f["n"], f["severity"], f["record"], f["field"], f["inventory"], f["asbuilt"], f["fix"]])
    return out.getvalue()


def text_report(result: dict) -> str:
    c = result["counts"]
    lines = [f"{len(result['findings'])} findings: {c['high']} high, {c['medium']} medium, {c['low']} low",
             f"{result['cables_compared']} cable records and {result['splices_compared']} splices compared", ""]
    for f in result["findings"]:
        lines.append(f"{f['n']:>2}. [{f['severity'].upper():6}] {f['record']}")
        lines.append(f"      {f['message']}")
        lines.append(f"      Fix: {f['fix']}")
    return "\n".join(lines)
