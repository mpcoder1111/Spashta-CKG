"""Self-contained runnable proof for classList class usage (spec/css-coverage-roadmap.md P3).

Runs the JS builder over builders/tests/data/classlist_dummy.js and asserts:
  el.classList.add("fp-active") / .toggle("is-open") / .remove("fp-hidden") -> queries_dom StyleClass (each)
  set.add("notaclass")   -> NO edge (add on a non-classList object)
  document.querySelector(".existing") -> queries_dom 'existing' (regression, unchanged)

Requires tree-sitter + tree-sitter-javascript (the JS builder's parser). Skips cleanly if absent.

Run:  python builders/js/verify_classlist.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_js_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "classlist_dummy.js"


def main() -> int:
    out = Path(tempfile.mkdtemp(prefix="spashta_classlist_")) / "frag.json"
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
    used = {id2name.get(e["to"], e["to"]).split("::")[-1]
            for e in frag["edges"] if e["edge"] == "queries_dom"}

    checks = [
        ("classList.add/toggle/remove -> queries_dom StyleClass",
         {"fp-active", "is-open", "fp-hidden"} <= used),
        ("Set.add('notaclass') is NOT a class edge", "notaclass" not in used),
        ("querySelector('.existing') still resolves (regression)", "existing" in used),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
