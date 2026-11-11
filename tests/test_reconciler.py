import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reconciler import extract
from reconciler.evaluate import score
from reconciler.inventory import load_inventory
from reconciler.reconcile import reconcile
from reconciler.report import corrections_csv, corrections_text, text_report

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"


@pytest.fixture
def asbuilt():
    return json.loads((EX / "asbuilt_FX-2231.reference.json").read_text())


@pytest.fixture
def inventory():
    return load_inventory(EX / "inventory_FX-2231.geojson", EX / "inventory_splices_FX-2231.csv")


def codes(result):
    return [(f["code"], f["where"].get("cable_id")) for f in result["findings"]]


def test_inventory_loads_cables_and_splices(inventory):
    assert len(inventory["cables"]) == 9 and len(inventory["splices"]) == 3
    assert inventory["splices"][1]["backbone_fibers"] == [13, 24]


def test_sample_project_findings(asbuilt, inventory):
    r = reconcile(asbuilt, inventory)
    assert r["counts"] == {"high": 5, "medium": 4, "low": 1}
    assert set(codes(r)) == {
        ("FIBER_COUNT", "L-03"), ("MISSING_IN_INVENTORY", "L-05"), ("SPLICE_MISMATCH", "L-03"),
        ("SPLICE_MISMATCH", "L-04"), ("SPLICE_MISSING_IN_INVENTORY", "L-05"), ("LENGTH", "CBL-144-01"),
        ("PLACEMENT", "CBL-144-01"), ("ENDPOINT", "L-04"), ("NOT_BUILT", "L-02"), ("ID_MISMATCH", "L-01")}
    assert r["cables_compared"] == 8 and r["aliases"] == {"LAT-01": "L-01"}
    assert [f["n"] for f in r["findings"]] == list(range(1, 11))


def test_renamed_cable_still_matches_its_splice(asbuilt, inventory):
    r = reconcile(asbuilt, inventory)
    assert not [f for f in r["findings"] if f["code"].startswith("SPLICE") and f["where"]["cable_id"] == "L-01"]


def test_length_tolerance_is_adjustable(asbuilt, inventory):
    assert not [f for f in reconcile(asbuilt, inventory, 0.15)["findings"] if f["code"] == "LENGTH"]
    tight = [f for f in reconcile(asbuilt, inventory, 0.005)["findings"] if f["code"] == "LENGTH"]
    assert len(tight) >= 3


def test_matching_records_produce_no_findings(asbuilt):
    same = {"cables": [c for c in asbuilt["cables"] if c["status"] == "built"], "splices": asbuilt["splices"]}
    assert reconcile(same, copy.deepcopy(same))["findings"] == []


def test_ids_match_regardless_of_case_and_spaces(asbuilt):
    a = {"cables": [{"cable_id": "l-01 ", "fiber_count": 12, "from": "hh-102", "to": "Bldg-110", "length_ft": 240, "placement": "underground", "status": "built"}], "splices": []}
    i = {"cables": [{"cable_id": "L-01", "fiber_count": 12, "from": "BLDG-110", "to": "HH-102", "length_ft": 240, "placement": "underground"}], "splices": []}
    assert reconcile(a, i)["findings"] == []


def test_double_assigned_fibers_are_caught(asbuilt, inventory):
    asbuilt["splices"][3]["backbone_fibers"] = [40, 51]  # overlaps 37-48
    assert any(f["code"] == "DOUBLE_ASSIGNED" for f in reconcile(asbuilt, inventory)["findings"])


def test_inventory_cable_the_notes_never_mention(asbuilt, inventory):
    asbuilt["cables"] = [c for c in asbuilt["cables"] if c["cable_id"] != "L-02"]
    f = [f for f in reconcile(asbuilt, inventory)["findings"] if f["where"].get("cable_id") == "L-02"]
    assert f[0]["code"] == "NOT_IN_ASBUILT" and "Ask the field" in f[0]["fix"]


def test_reports(asbuilt, inventory):
    r = reconcile(asbuilt, inventory)
    rows = corrections_csv(r).strip().split("\n")
    assert rows[0].startswith("n,severity,record") and len(rows) == 11
    assert "10 findings: 5 high, 4 medium, 1 low" in text_report(r)


def test_pdf_and_text_sources_agree():
    pdf, txt = extract.read_source(EX / "asbuilt_FX-2231.pdf"), extract.read_source(EX / "asbuilt_FX-2231.txt")
    for needle in ("CBL-144-01", "bb 13-36 to L-03 1-24", "NOT BUILT", "1310'"):
        assert needle in pdf and needle in txt


def test_answer_key_is_well_formed(asbuilt):
    assert extract.validate(asbuilt) == []


def test_validation_catches_bad_shapes():
    bad = {"cables": [{"cable_id": "X", "status": "built", "from": "HH-1", "to": None, "placement": "buried", "fiber_count": "12"}],
           "splices": [{"closure_id": "SC-1", "structure": "HH-1", "backbone_cable": "B", "branch_cable": "X", "backbone_fibers": [12, 1], "branch_fibers": [1, 12]}]}
    p = "\n".join(extract.validate(bad))
    assert "needs both endpoints" in p and "unknown placement" in p and "whole number" in p and "backbone_fibers must be" in p


def test_corrections_text_reads_top_to_bottom(asbuilt, inventory):
    text = corrections_text(reconcile(asbuilt, inventory), "FX-2231")
    assert text.startswith("CORRECTIONS FOR GIS\nProject FX-2231\n10 corrections: 5 high, 4 medium, 1 low\n")
    assert text.index("HIGH PRIORITY") < text.index("MEDIUM PRIORITY") < text.index("LOW PRIORITY")
    assert "1. L-03 HH-103 to BLDG-300\n   Field      | fiber_count\n   GIS now    | 12\n   Change to  | 24\n   Action     | Set fiber_count to 24" in text
    assert text.rstrip().endswith("End of corrections")
    same = {"cables": [], "splices": []}
    assert "Nothing to correct" in corrections_text(reconcile(same, same))


class FakeClient:
    """Stands in for the Anthropic client so tests need no API key."""
    def __init__(self, text):
        self._text, self.messages, self.prompt = text, self, None

    def create(self, **kw):
        self.prompt = kw["messages"][0]["content"]
        return type("Msg", (), {"content": [type("Block", (), {"text": self._text})()]})()


def test_extract_sends_the_notes_and_parses_the_reply(asbuilt):
    client = FakeClient("```json\n" + json.dumps(asbuilt) + "\n```")
    out = extract.extract("10/14 - Pulled 144ct backbone", client=client)
    assert out == asbuilt and "10/14 - Pulled 144ct backbone" in client.prompt and "{notes}" not in client.prompt


def test_extract_rejects_a_malformed_reply():
    with pytest.raises(ValueError):
        extract.extract("notes", client=FakeClient('{"cables": [{"cable_id": "", "status": "maybe"}], "splices": []}'))


def test_score_is_perfect_against_itself(asbuilt):
    s = score(asbuilt, asbuilt)
    assert s["field_accuracy"] == 1.0 and s["records_found"] == s["records_expected"] == 14 and not s["misses"]


def test_score_counts_wrong_fields_missing_and_invented_records(asbuilt):
    got = copy.deepcopy(asbuilt)
    got["cables"][7]["fiber_count"] = 12          # missed the upsizing on L-03
    got["cables"][2]["length_ft"] = 1180          # took the plan length
    del got["splices"][3]                         # missed the L-05 splice
    got["cables"].append({"cable_id": "L-09", "fiber_count": 12, "from": "HH-101", "to": "BLDG-1", "length_ft": 5, "placement": None, "status": "built"})
    s = score(got, asbuilt)
    assert s["records_found"] == 13 and s["records_extra"] == 1
    assert s["fields_total"] == 10 * 4 + 4 * 3 and s["fields_correct"] == s["fields_total"] - 2 - 3
    assert len(s["misses"]) == 3


NODE = """
const L = require(process.argv[1]);
const {cases} = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify(cases.map(c => { const r = L.reconcile(c.a, c.i, c.t); return {r, s: L.score(c.a, c.ref), t: L.correctionsText(r, c.a.project)}; })));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_javascript_and_python_agree(asbuilt, inventory):
    variant = copy.deepcopy(asbuilt)
    variant["splices"][3]["backbone_fibers"] = [40, 51]
    variant["cables"] = [c for c in variant["cables"] if c["cable_id"] != "L-02"]
    variant["cables"][7]["fiber_count"] = 12
    cases = [{"a": asbuilt, "i": inventory, "t": 0.05, "ref": asbuilt}, {"a": asbuilt, "i": inventory, "t": 0.005, "ref": asbuilt},
             {"a": variant, "i": inventory, "t": 0.05, "ref": asbuilt}, {"a": asbuilt, "i": {"cables": [], "splices": []}, "t": 0.05, "ref": variant}]
    run = subprocess.run(["node", "-e", NODE, str(ROOT / "demo" / "logic.js")], input=json.dumps({"cases": cases}),
                         capture_output=True, text=True, check=True)
    for case, js in zip(cases, json.loads(run.stdout)):
        py = reconcile(case["a"], case["i"], case["t"])
        assert js["r"] == json.loads(json.dumps(py))
        assert js["t"] == corrections_text(py, case["a"].get("project"))
        ps = score(case["a"], case["ref"])
        for k in ("records_expected", "records_found", "records_extra", "fields_correct", "fields_total", "field_accuracy"):
            assert js["s"][k] == ps[k]
        assert js["s"]["misses_count"] == len(ps["misses"])
