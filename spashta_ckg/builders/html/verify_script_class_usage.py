"""Proof for inline-<script> class usage (spec/dead-code-accuracy.md P3). Runs the HTML builder over
builders/tests/data/scriptcls/ and asserts a template's inline <script> yields uses_style edges:
  classList.toggle("dc-check--disabled", …) -> uses_style dc-check--disabled  (two-arg toggle)
  classList.add("fp-active") / remove("fp-hidden") -> uses_style each
  querySelector(".dc-worklist-check") -> uses_style dc-worklist-check
  querySelector(".a > .b")  -> NOT emitted (compound selector, unmodeled)
  classList.add(computedName) -> NOT emitted (variable, unmodeled)

Run:  python builders/html/verify_script_class_usage.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_html_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "scriptcls"


def _run() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="spashta_scriptcls_"))
    dest = tmp / "scriptcls"
    shutil.copytree(FIXTURE, dest)
    out = tmp / "frag.json"
    subprocess.run([sys.executable, str(BUILDER), "--source-root", str(dest), "--out", str(out)],
                   check=True, capture_output=True, text=True)
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    id2name = {n["id"]: n.get("name") for n in frag["nodes"]}
    used = {id2name.get(e["to"], e["to"]).split("::")[-1]
            for e in frag["edges"] if e["edge"] == "uses_style"}
    checks = [
        ("classList.toggle(two-arg) -> uses_style dc-check--disabled", "dc-check--disabled" in used),
        ("classList.add/remove -> fp-active + fp-hidden", {"fp-active", "fp-hidden"} <= used),
        ("querySelector('.x') -> uses_style dc-worklist-check", "dc-worklist-check" in used),
        ("compound querySelector('.a > .b') NOT emitted", "a" not in used and "b" not in used),
        ("variable classList.add(computedName) NOT emitted (no bogus 'computedName')",
         "computedName" not in used),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
