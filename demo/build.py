"""Assemble demo/index.html from the template, the browser logic and the sample project."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from reconciler.extract import PROMPT  # noqa: E402
from reconciler.inventory import load_inventory  # noqa: E402

REPO = "https://github.com/Chiamaka-Oyekwe/as-built-reconciler"
ex = ROOT / "examples"
js = lambda v: json.dumps(v).replace("</", "<\\/")
html = (HERE / "template.html").read_text()
html = html.replace("/*__NOTES__*/", js((ex / "asbuilt_FX-2231.txt").read_text()))
html = html.replace("/*__REFERENCE__*/", js(json.loads((ex / "asbuilt_FX-2231.reference.json").read_text())))
html = html.replace("/*__INVENTORY__*/", js(load_inventory(ex / "inventory_FX-2231.geojson", ex / "inventory_splices_FX-2231.csv")))
html = html.replace("/*__PROMPT__*/", js(PROMPT))
html = html.replace("/*__LOGIC__*/", (HERE / "logic.js").read_text().split("if (typeof module")[0])
html = html.replace("/*__PDFJS__*/", js({
    "lib": "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
    "worker": "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js"}))
html = html.replace("/*__JSZIP__*/", js("https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"))
html = html.replace("/*__REPO__*/", REPO)
(HERE / "index.html").write_text(html)
# GitHub Pages serves the docs/ folder, so anyone can open the demo without an account.
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(html)
print(f"wrote demo/index.html ({len(html):,} bytes)")
