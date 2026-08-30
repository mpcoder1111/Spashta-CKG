"""Self-contained runnable proof for HTMX out-of-band swaps (spec/fullstack-coupling-roadmap.md P5).

Copies builders/tests/data/oob/ to a temp dir OUTSIDE Spashta-CKG (the scanner excludes its own tree), runs
the HTML builder, and asserts:
  <div id="form-messages" hx-swap-oob="true">        -> oob_swaps -> StyleID 'form-messages'
  <span id="rv-count" hx-swap-oob="outerHTML">       -> oob_swaps -> StyleID 'rv-count' (swap value ignored; id is the target)
  <div id="dyn-{{ field.id }}" hx-swap-oob="true">   -> NO edge (dynamic id -> ambiguity)
  <button hx-target="#form-messages">               -> targets_element -> StyleID '#form-messages' (unchanged/regression)

NOTE: OOB uses the BARE element id ('form-messages'), which unifies by name with the CSS StyleID
(#form-messages { } -> 'form-messages') and JS getElementById('form-messages'); hx-target keeps the
'#form-messages' spelling (a pre-existing separate quirk, out of scope for P5).

Run:  python builders/html/verify_oob_swaps.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_html_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "oob"


def _run() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="spashta_oob_"))
    dest = tmp / "oob"
    shutil.copytree(FIXTURE, dest)
    out = tmp / "frag.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(dest), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    id2name = {n["id"]: n.get("name") for n in frag["nodes"]}

    def targets(etype: str) -> set:
        return {id2name.get(e["to"], e["to"]).split("::")[-1]
                for e in frag["edges"] if e["edge"] == etype}

    oob = targets("oob_swaps")
    tgt = targets("targets_element")
    dyn_ambig = any("dyn-" in a.get("expression", "") for a in frag.get("ambiguities", []))

    checks = [
        ("bare hx-swap-oob -> oob_swaps StyleID 'form-messages'", "form-messages" in oob),
        ("hx-swap-oob='outerHTML' targets the id, not the swap value ('rv-count')", "rv-count" in oob),
        ("dynamic id -> no oob edge + an ambiguity", "outerHTML" not in oob and dyn_ambig),
        ("hx-target still emits targets_element -> '#form-messages' (regression)",
         "#form-messages" in tgt),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
