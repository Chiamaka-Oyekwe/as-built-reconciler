"""Read as-built notes and return structured cable and splice records.

Foremen do not write notes to a schema. One line says "144ct", the next says
"144F", lengths show up as sheath marks, and a cancelled lateral is a sentence.
This is the part a language model is good at. Its output is checked for shape
here and scored against a hand-made answer key in evaluate.py.
"""
from __future__ import annotations

import json
from pathlib import Path

PLACEMENTS = ("underground", "aerial", None)

PROMPT = """You are reading as-built closeout notes for a fiber construction project.
Pull out every cable segment and every splice. Use only what the notes say.

Return JSON only, in this shape:
{
  "project": "<project number or null>",
  "cables": [{"cable_id": str, "fiber_count": int|null, "from": str|null, "to": str|null,
              "length_ft": number|null, "placement": "underground"|"aerial"|null,
              "status": "built"|"not_built"}],
  "splices": [{"closure_id": str, "structure": str, "backbone_cable": str,
               "backbone_fibers": [first, last], "branch_cable": str, "branch_fibers": [first, last]}]
}

Rules:
- One cable record per span between two structures. A backbone pulled through five handholes is four records with the same cable_id.
- Write handholes as HH-<number> and buildings as BLDG-<street number>.
- "ct" and "F" both mean fiber count. "UG" means underground.
- If a length is given as sheath marks, subtract them. If the notes give a built length and a plan length, use the built length.
- A cable the notes say was deferred, cancelled or not built gets status "not_built" and null for what is unknown.
- If a cable was moved in the field, record where it was actually built.
- "bb" means the backbone cable. Express or pass-through fibers are not splices; leave them out.
- Fiber ranges are inclusive pairs, for example [13, 36].

Notes:
<notes>
{notes}
</notes>"""


def read_source(path: str | Path) -> str:
    """Text from a .txt file or a text-based PDF."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return path.read_text()


def validate(records: dict) -> list[str]:
    problems = []
    for n, c in enumerate(records.get("cables", []), 1):
        if not c.get("cable_id"):
            problems.append(f"cable {n}: no cable_id")
        if c.get("status") not in ("built", "not_built"):
            problems.append(f"cable {n}: status must be built or not_built")
        if c.get("status") == "built" and not (c.get("from") and c.get("to")):
            problems.append(f"cable {n}: built cable needs both endpoints")
        if c.get("placement") not in PLACEMENTS:
            problems.append(f"cable {n}: unknown placement {c.get('placement')!r}")
        if c.get("fiber_count") is not None and not isinstance(c["fiber_count"], int):
            problems.append(f"cable {n}: fiber_count must be a whole number")
    for n, s in enumerate(records.get("splices", []), 1):
        for key in ("closure_id", "structure", "backbone_cable", "branch_cable"):
            if not s.get(key):
                problems.append(f"splice {n}: no {key}")
        for key in ("backbone_fibers", "branch_fibers"):
            r = s.get(key)
            if not (isinstance(r, list) and len(r) == 2 and all(isinstance(v, int) for v in r) and r[0] <= r[1]):
                problems.append(f"splice {n}: {key} must be [first, last]")
    if "cables" not in records or "splices" not in records:
        problems.append("missing cables or splices list")
    return problems


def parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    records = json.loads(raw)
    problems = validate(records)
    if problems:
        raise ValueError("Extraction failed validation:\n" + "\n".join(problems))
    return records


def extract(notes: str, client=None, model: str | None = None) -> dict:
    """Ask Claude for the records. Needs the `anthropic` package and ANTHROPIC_API_KEY."""
    import os
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model or os.environ.get("RECONCILER_MODEL", "claude-sonnet-5-5"),
        max_tokens=4000,
        messages=[{"role": "user", "content": PROMPT.replace("{notes}", notes)}],
    )
    return parse(msg.content[0].text)
