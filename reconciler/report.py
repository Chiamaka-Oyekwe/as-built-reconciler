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


def corrections_text(result: dict, project: str | None = None) -> str:
    """The same corrections as plain text a person can read top to bottom."""
    c, rule = result["counts"], "=" * 64
    n = len(result["findings"])
    lines = ["CORRECTIONS FOR GIS", f"Project {project}" if project else "Project not named",
             f"{n} correction{'' if n == 1 else 's'}: {c['high']} high, {c['medium']} medium, {c['low']} low", rule]
    for sev in ("high", "medium", "low"):
        group = [f for f in result["findings"] if f["severity"] == sev]
        if not group:
            continue
        lines += ["", f"{sev.upper()} PRIORITY", "-" * 64]
        for f in group:
            lines += [f"{f['n']}. {f['record']}",
                      f"   Field      | {f['field']}",
                      f"   GIS now    | {f['inventory']}",
                      f"   Change to  | {f['asbuilt']}",
                      f"   Action     | {f['fix']}", ""]
    if not n:
        lines += ["", "Nothing to correct. The inventory agrees with the as-built records.", ""]
    lines += [rule, "End of corrections"]
    return "\n".join(lines) + "\n"


def text_report(result: dict) -> str:
    c = result["counts"]
    lines = [f"{len(result['findings'])} findings: {c['high']} high, {c['medium']} medium, {c['low']} low",
             f"{result['cables_compared']} cable records and {result['splices_compared']} splices compared", ""]
    for f in result["findings"]:
        lines.append(f"{f['n']:>2}. [{f['severity'].upper():6}] {f['record']}")
        lines.append(f"      {f['message']}")
        lines.append(f"      Fix: {f['fix']}")
    return "\n".join(lines)
