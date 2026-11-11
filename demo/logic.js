// Same rules as reconciler/reconcile.py and evaluate.py, for the browser demo.
const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 };
const norm = (v) => (typeof v === "string" ? v.trim().toUpperCase().replace(/ /g, "") : v);
const cab = (c) => Object.assign({}, c, { cable_id: norm(c.cable_id), from: norm(c.from), to: norm(c.to) });
const sameEnds = (a, b) => (a.from === b.from && a.to === b.to) || (a.from === b.to && a.to === b.from);
const rng = (r) => (r ? `${r[0]}-${r[1]}` : "none");
const none = (v) => (v === null || v === undefined ? "None" : v);
const finding = (code, severity, record, field, asbuilt, inventory, message, fix, where) =>
  ({ code, severity, record, field, asbuilt, inventory, message, fix, where: where || {} });

function reconcile(asbuilt, inventory, tolerance = 0.05) {
  const allA = (asbuilt.cables || []).map(cab);
  const built = allA.filter((c) => (c.status || "built") !== "not_built");
  const notBuilt = new Set(allA.filter((c) => c.status === "not_built").map((c) => c.cable_id));
  const inv = (inventory.cables || []).map(cab);
  const usedA = new Set(), usedI = new Set(), pairs = [];
  const freeA = () => built.map((_, k) => k).filter((k) => !usedA.has(k));
  const freeI = () => inv.map((_, k) => k).filter((k) => !usedI.has(k));
  const pair = (ka, ki, how) => { usedA.add(ka); usedI.add(ki); pairs.push([ka, ki, how]); };

  for (const ka of freeA()) for (const ki of freeI()) {
    if (inv[ki].cable_id === built[ka].cable_id && sameEnds(inv[ki], built[ka])) { pair(ka, ki, "exact"); break; }
  }
  for (const ka of freeA()) {
    if (usedA.has(ka)) continue;
    const cid = built[ka].cable_id;
    const ca = freeA().filter((k) => built[k].cable_id === cid), ci = freeI().filter((k) => inv[k].cable_id === cid);
    if (ca.length === 1 && ci.length === 1) pair(ka, ci[0], "endpoint");
  }
  const alias = {};
  for (const ka of freeA()) {
    if (usedA.has(ka)) continue;
    const ci = freeI().filter((k) => sameEnds(inv[k], built[ka]));
    if (ci.length === 1) { alias[inv[ci[0]].cable_id] = built[ka].cable_id; pair(ka, ci[0], "rename"); }
  }

  const findings = [];
  pairs.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  for (const [ka, ki, how] of pairs) {
    const a = built[ka], i = inv[ki];
    const record = `${a.cable_id} ${a.from} to ${a.to}`, where = { cable_id: a.cable_id, from: a.from, to: a.to };
    if (how === "rename") findings.push(finding("ID_MISMATCH", "low", record, "cable_id", a.cable_id, i.cable_id,
      `Same endpoints, different name: as-built calls it ${a.cable_id}, inventory calls it ${i.cable_id}.`,
      `Confirm they are the same cable, then rename ${i.cable_id} or record the alias.`, where));
    if (how === "endpoint") findings.push(finding("ENDPOINT", "medium", record, "endpoints", `${a.from} to ${a.to}`, `${i.from} to ${i.to}`,
      `${a.cable_id} was built ${a.from} to ${a.to}. Inventory shows ${i.from} to ${i.to}.`,
      `Move ${a.cable_id} in GIS to ${a.from} to ${a.to} and update its length to ${none(a.length_ft)} ft.`,
      Object.assign({}, where, { inv_from: i.from, inv_to: i.to })));
    if (a.fiber_count != null && i.fiber_count != null && a.fiber_count !== i.fiber_count)
      findings.push(finding("FIBER_COUNT", "high", record, "fiber_count", a.fiber_count, i.fiber_count,
        `${a.cable_id} was built as ${a.fiber_count}F. Inventory shows ${i.fiber_count}F.`,
        `Set fiber_count to ${a.fiber_count} and add the new strands to the fiber records.`, where));
    if (how !== "endpoint" && a.length_ft && i.length_ft) {
      const diff = Math.abs(a.length_ft - i.length_ft) / i.length_ft;
      if (diff > tolerance) findings.push(finding("LENGTH", "medium", record, "length_ft", a.length_ft, i.length_ft,
        `Length is off by ${(diff * 100).toFixed(1)}%: ${a.length_ft} ft built, ${i.length_ft} ft in inventory.`,
        `Set length_ft to ${a.length_ft} and redraw the route if it changed.`, where));
    }
    if (a.placement && i.placement && a.placement !== i.placement)
      findings.push(finding("PLACEMENT", "medium", record, "placement", a.placement, i.placement,
        `Built ${a.placement}. Inventory shows ${i.placement}.`,
        `Set placement to ${a.placement} and attach the span to the right support structure.`, where));
  }
  for (const ka of freeA()) {
    const a = built[ka];
    findings.push(finding("MISSING_IN_INVENTORY", "high", `${a.cable_id} ${a.from} to ${a.to}`, "record",
      `${none(a.fiber_count)}F, ${none(a.length_ft)} ft`, "none", `${a.cable_id} was built and is not in the inventory.`,
      `Add ${a.cable_id} (${none(a.fiber_count)}F, ${a.from} to ${a.to}, ${none(a.length_ft)} ft).`,
      { cable_id: a.cable_id, from: a.from, to: a.to }));
  }
  for (const ki of freeI()) {
    const i = inv[ki], cancelled = notBuilt.has(i.cable_id);
    findings.push(finding(cancelled ? "NOT_BUILT" : "NOT_IN_ASBUILT", "medium", `${i.cable_id} ${i.from} to ${i.to}`, "record",
      cancelled ? "not built" : "no record", `${none(i.fiber_count)}F, ${none(i.length_ft)} ft`,
      `${i.cable_id} is in the inventory. ` + (cancelled ? "The as-built says it was not built." : "The as-built does not mention it."),
      cancelled ? `Remove ${i.cable_id} or mark it as not built.` : `Ask the field whether ${i.cable_id} exists before changing GIS.`,
      { cable_id: i.cable_id, from: i.from, to: i.to, inventory_only: true }));
  }

  const sa = new Map((asbuilt.splices || []).map((s) => [norm(s.branch_cable), s]));
  const si = new Map((inventory.splices || []).map((s) => [alias[norm(s.branch_cable)] || norm(s.branch_cable), s]));
  const eq = (x, y) => x[0] === y[0] && x[1] === y[1];
  for (const [br, a] of sa) {
    const at = `${norm(a.closure_id)} at ${norm(a.structure)}`, where = { structure: norm(a.structure), cable_id: br };
    if (!si.has(br)) {
      findings.push(finding("SPLICE_MISSING_IN_INVENTORY", "high", `Splice to ${br}`, "record",
        `${at}: backbone ${rng(a.backbone_fibers)} to ${br} ${rng(a.branch_fibers)}`, "none", `The splice feeding ${br} is not in the inventory.`,
        `Add the splice at ${at}: backbone ${rng(a.backbone_fibers)} to ${br} ${rng(a.branch_fibers)}.`, where));
      continue;
    }
    const i = si.get(br), diffs = [];
    if (norm(a.structure) !== norm(i.structure) || norm(a.closure_id) !== norm(i.closure_id)) diffs.push(`location ${at} vs ${norm(i.closure_id)} at ${norm(i.structure)}`);
    if (!eq(a.backbone_fibers, i.backbone_fibers)) diffs.push(`backbone fibers ${rng(a.backbone_fibers)} vs ${rng(i.backbone_fibers)}`);
    if (!eq(a.branch_fibers, i.branch_fibers)) diffs.push(`branch fibers ${rng(a.branch_fibers)} vs ${rng(i.branch_fibers)}`);
    if (diffs.length) findings.push(finding("SPLICE_MISMATCH", "high", `Splice to ${br}`, "fiber assignment",
      `${at}: backbone ${rng(a.backbone_fibers)} to ${br} ${rng(a.branch_fibers)}`,
      `${norm(i.closure_id)} at ${norm(i.structure)}: backbone ${rng(i.backbone_fibers)} to ${br} ${rng(i.branch_fibers)}`,
      `Fiber assignment for ${br} disagrees (as-built vs inventory): ${diffs.join("; ")}.`,
      `Update the splice record to ${at}, backbone ${rng(a.backbone_fibers)} to ${br} ${rng(a.branch_fibers)}. Check circuits assigned on the old fibers.`, where));
  }
  for (const [br, i] of si) {
    if (!sa.has(br)) findings.push(finding("SPLICE_NOT_IN_ASBUILT", notBuilt.has(br) ? "medium" : "high", `Splice to ${br}`, "record", "no record",
      `${norm(i.closure_id)} at ${norm(i.structure)}: backbone ${rng(i.backbone_fibers)}`, `Inventory has a splice feeding ${br}. The as-built has none.`,
      notBuilt.has(br) ? "Remove it with the cable." : "Confirm in the field before assigning these fibers.", { structure: norm(i.structure), cable_id: br }));
  }
  const spl = asbuilt.splices || [];
  for (let x = 0; x < spl.length; x++) for (let y = x + 1; y < spl.length; y++) {
    const a = spl[x], b = spl[y];
    if (norm(a.backbone_cable) === norm(b.backbone_cable) && a.backbone_fibers[0] <= b.backbone_fibers[1] && b.backbone_fibers[0] <= a.backbone_fibers[1])
      findings.push(finding("DOUBLE_ASSIGNED", "high", `${norm(a.backbone_cable)} fibers`, "backbone_fibers",
        `${rng(a.backbone_fibers)} to ${norm(a.branch_cable)} and ${rng(b.backbone_fibers)} to ${norm(b.branch_cable)}`, "n/a",
        `The as-built puts overlapping backbone fibers on ${norm(a.branch_cable)} and ${norm(b.branch_cable)}.`,
        "Send back to the splicer. One of the two records is wrong.", { structure: norm(a.structure) }));
  }
  const sorted = findings.map((f, k) => [f, k]).sort((p, q) => SEVERITY_ORDER[p[0].severity] - SEVERITY_ORDER[q[0].severity] || p[1] - q[1]).map((p) => p[0]);
  sorted.forEach((f, k) => { f.n = k + 1; });
  const counts = { high: 0, medium: 0, low: 0 };
  sorted.forEach((f) => { counts[f.severity] += 1; });
  let both = 0; for (const k of sa.keys()) if (si.has(k)) both += 1;
  return { findings: sorted, counts, cables_compared: pairs.length, splices_compared: both, aliases: alias };
}

function score(extracted, reference) {
  const same = (a, b) => {
    if (typeof a === "string" || typeof b === "string") return norm(a) === norm(b);
    if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < 0.5;
    return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  };
  const cableKey = (c) => c.status === "not_built" ? norm(c.cable_id) + "|not_built" : norm(c.cable_id) + "|" + [norm(c.from), norm(c.to)].sort().join("~");
  const spliceKey = (s) => norm(s.closure_id) + "|" + norm(s.branch_cable);
  const misses = []; let correct = 0, total = 0, found = 0, expected = 0, extra = 0;
  for (const [name, key, fields] of [["cables", cableKey, ["fiber_count", "length_ft", "placement", "status"]], ["splices", spliceKey, ["structure", "backbone_fibers", "branch_fibers"]]]) {
    const got = new Map((extracted[name] || []).map((r) => [key(r), r])), want = new Map((reference[name] || []).map((r) => [key(r), r]));
    expected += want.size;
    for (const k of got.keys()) if (!want.has(k)) extra += 1;
    for (const [k, w] of want) {
      const label = `${name.slice(0, -1)} ${k.split("|")[0]}`;
      if (!got.has(k)) { misses.push(`${label}: not extracted`); total += fields.length; continue; }
      found += 1;
      for (const f of fields) { total += 1; if (same(got.get(k)[f], w[f])) correct += 1; else misses.push(`${label}: ${f} differs`); }
    }
  }
  return { records_expected: expected, records_found: found, records_extra: extra, fields_correct: correct, fields_total: total,
    field_accuracy: total ? Math.round((correct / total) * 10000) / 10000 : 1, misses_count: misses.length };
}

function correctionsText(result, project) {
  const c = result.counts, rule = "=".repeat(64), n = result.findings.length;
  const lines = ["CORRECTIONS FOR GIS", project ? `Project ${project}` : "Project not named",
    `${n} correction${n === 1 ? "" : "s"}: ${c.high} high, ${c.medium} medium, ${c.low} low`, rule];
  for (const sev of ["high", "medium", "low"]) {
    const group = result.findings.filter((f) => f.severity === sev);
    if (!group.length) continue;
    lines.push("", `${sev.toUpperCase()} PRIORITY`, "-".repeat(64));
    for (const f of group) lines.push(`${f.n}. ${f.record}`, `   Field      | ${f.field}`, `   GIS now    | ${f.inventory}`, `   Change to  | ${f.asbuilt}`, `   Action     | ${f.fix}`, "");
  }
  if (!n) lines.push("", "Nothing to correct. The inventory agrees with the as-built records.", "");
  lines.push(rule, "End of corrections");
  return lines.join("\n") + "\n";
}

if (typeof module !== "undefined") module.exports = { reconcile, score, norm, correctionsText };
