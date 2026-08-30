"""Self-contained runnable proof for named-callback-reference call resolution (spec/js-callback-refs.md).

Runs the JS builder over builders/tests/data/callback_ref_dummy.js and asserts:
  addEventListener('DOMContentLoaded', init)      -> calls wireUp -> init      (bare identifier)
  addEventListener('click', handleClick)          -> calls wireUp -> handleClick (member-expression callee unaffected; bare id here)
  addEventListener('load', fp.showToast)           -> calls fireToast -> window.fp.showToast (trailing-property fallback)
  addEventListener('change', function(evt){...})  -> NO new edge (inline handler — nothing to resolve)
  addEventListener('keydown', notDefinedAnywhere) -> unresolved_call ambiguity, NOT a guessed edge
  A DIRECT call (registers_event_handler itself, from addEventListener) is UNCHANGED — still emitted.

Requires tree-sitter + tree-sitter-javascript (the JS builder's parser). Skips cleanly if absent.

Run:  python builders/js/verify_callback_refs.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_js_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "callback_ref_dummy.js"


def main() -> int:
    out = Path(tempfile.mkdtemp(prefix="spashta_cbref_")) / "frag.json"
    r = subprocess.run([sys.executable, str(BUILDER), "--source-root", str(FIXTURE), "--out", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        if "tree-sitter" in (r.stderr + r.stdout).lower() or "missing parser" in (r.stderr + r.stdout).lower():
            print("  [SKIP] tree-sitter not installed — run where the JS builder's parser is available.")
            return 0
        print(r.stderr[-500:])
        return 1
    frag = json.loads(out.read_text("utf-8"))
    id2name = {n["id"]: n.get("name") for n in frag["nodes"]}

    def calls_pairs():
        # names are file-scoped ("wireUp") or GLOBAL dotted ("window.fp.showToast" — no "::" to split);
        # splitting only the id (not the resolved `name`) avoids truncating a dotted name to its tail.
        return {(id2name.get(e["from"], e["from"]).split("::")[-1], id2name.get(e["to"], e["to"]))
                for e in frag["edges"] if e["edge"] == "calls"}

    calls = calls_pairs()
    reh_events = {id2name.get(e["to"], e["to"]) for e in frag["edges"] if e["edge"] == "registers_event_handler"}
    unresolved = [a for a in frag.get("ambiguities", []) if a["kind"] == "unresolved_call"]

    checks = [
        ("bare-identifier handler ref -> calls wireUp -> init",
         ("wireUp", "init") in calls),
        ("bare-identifier handler ref -> calls wireUp -> handleClick",
         ("wireUp", "handleClick") in calls),
        ("dotted handler ref (trailing-property fallback) -> calls fireToast -> window.fp.showToast",
         ("fireToast", "window.fp.showToast") in calls),
        ("inline anonymous handler -> no bogus calls edge (nothing named to resolve)",
         not any(t == "evt" for _, t in calls)),
        ("unresolved handler name -> unresolved_call ambiguity, not a guessed edge",
         any(a.get("expression") == "notDefinedAnywhere" for a in unresolved)),
        ("registers_event_handler still fires for every addEventListener (unchanged)",
         len(reh_events) >= 4),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
