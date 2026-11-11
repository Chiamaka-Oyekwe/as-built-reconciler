# As-Built Reconciler

A crew finishes a fiber job and sends back closeout notes. The notes say a lateral was upsized, a handhole flooded so the splice moved, one span went aerial because the duct collapsed. Then nobody updates the GIS.

Months later someone assigns a circuit to fibers the inventory says are free at a closure that was never built. I have chased that kind of error. It starts as a records problem and ends as an outage or a truck roll.

This tool reads the closeout notes, compares every cable and splice with the GIS inventory, and lists what disagrees, worst first, with the fix for each.

**Live demo:** https://claude.ai/artifact/KvfLeS7NAbcYVB5KUyu65i

## What it finds

On the sample project (made up, 10 cable records, 4 splices) it reports ten disagreements:

```
10 findings: 5 high, 4 medium, 1 low
8 cable records and 3 splices compared

 1. [HIGH  ] L-03 HH-103 to BLDG-300
      L-03 was built as 24F. Inventory shows 12F.
      Fix: Set fiber_count to 24 and add the new strands to the fiber records.
 4. [HIGH  ] Splice to L-04
      Fiber assignment for L-04 disagrees (as-built vs inventory): location SC-105 at HH-105
      vs SC-104 at HH-104; backbone fibers 37-48 vs 25-36.
 6. [MEDIUM] CBL-144-01 HH-103 to HH-104
      Length is off by 11.0%: 1310 ft built, 1180 ft in inventory.
 ...
```

| Check | Severity |
|---|---|
| Fiber count differs | High |
| Cable built, not in inventory | High |
| Splice fibers or location differ | High |
| Splice missing from inventory | High |
| Same backbone fiber spliced to two branches | High |
| Endpoints moved | Medium |
| Length off by more than the tolerance (5% by default) | Medium |
| Aerial vs underground | Medium |
| In inventory, never built | Medium |
| Same cable under a different name | Low |

## Try it

```
python -m reconciler.cli reconcile examples/asbuilt_FX-2231.reference.json \
    examples/inventory_FX-2231.geojson --splices examples/inventory_splices_FX-2231.csv \
    --csv corrections.csv
```

`corrections.csv` is the work list for whoever fixes the GIS: record, field, old value, new value, action.

## Use your own data

In the demo, drop files onto the page:

- **As-built:** closeout notes as `.txt` or a text-based `.pdf`, or a records `.json` written by the `extract` command.
- **Inventory:** cables as `.geojson` (properties `cable_id`, `fiber_count`, `from_struct`, `to_struct`, `length_ft`, `placement`) and splices as `.csv` (`closure_id, structure, backbone_cable, bb_start, bb_end, branch_cable, br_start, br_end`).

Files are read in the browser and are not stored. Notes are sent to Claude only when you press Extract. Do not load records you are not allowed to share.

The same files work on the command line, as shown above.

## Where the AI is, and where it isn't

Foremen do not write to a schema. One line says "144ct", the next says "144F". A length shows up as two sheath marks. A cancelled lateral is half a sentence. A model reads that well, and writing a parser for it is a losing fight.

Comparing two sets of records is the opposite. It has to give the same answer every time, so it is plain code.

| Step | Who does it |
|---|---|
| Read the notes (text or PDF) into cable and splice records | Claude, `reconciler/extract.py` |
| Reject output that is the wrong shape | Code, `extract.validate` |
| Score the reading against a hand-made answer key | Code, `reconciler/evaluate.py` |
| Match records and list disagreements | Code, `reconciler/reconcile.py` |

```
export ANTHROPIC_API_KEY=...
python -m reconciler.cli extract examples/asbuilt_FX-2231.pdf > records.json
python -m reconciler.cli evaluate records.json examples/asbuilt_FX-2231.reference.json
```

`evaluate` reports how many records were found and what share of fields match the key, and lists each miss. That number is how I would decide whether to trust the reader on a new contractor's notes: build a key for one of their jobs, score it, then decide.

The sample notes include the traps I would expect to trip a reader: a built length next to a plan length, a lateral moved in the field, a count changed by change order, a cable that was cancelled, and express fibers that are not splices.

## How records are matched

1. Same cable ID and same two endpoints.
2. Same cable ID with one unmatched record on each side: the endpoints moved.
3. Same endpoints under a different ID: probably a rename. The alias carries over, so the splice records still line up.

Whatever is left is either built and missing from the GIS, or in the GIS and not in the notes. Splices are matched on the branch cable they feed.

## What it does not do

- It reads text. A scanned redline drawing with no text layer needs OCR first, and that is not in here.
- It trusts the as-built. If the notes are wrong, the findings are wrong. A cable in the GIS that the notes never mention is flagged "ask the field", not "delete".
- Length is compared as a number. It does not re-measure geometry.
- The sample project is synthetic. No employer or customer data is in this repository.

## Tests

```
pip install pytest pypdf
python -m pytest
```

Seventeen tests. One runs the browser version of the rules in Node and checks it returns the same findings as the Python, so the demo cannot drift from the tool.

## Layout

```
reconciler/   extract, evaluate, reconcile, report, inventory loader, CLI
examples/     closeout notes (.txt and .pdf), answer key, GIS inventory (GeoJSON), splice table (CSV)
demo/         browser version (build with: python demo/build.py)
tests/
```
