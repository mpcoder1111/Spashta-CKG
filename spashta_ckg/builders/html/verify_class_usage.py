"""Self-contained runnable proof for markup class usage (spec/css-coverage-roadmap.md P1).

Copies builders/tests/data/cssuse/ to a temp dir OUTSIDE Spashta-CKG (the scanner excludes its own tree),
runs the HTML builder, and asserts:
  class="fp-card fp-card--wide"                       -> uses_style to StyleClass 'fp-card' + 'fp-card--wide'
  class="btn-primary btn-busy"                        -> uses_style to 'btn-primary' + 'btn-busy'
  class="fp-label {% if active %}fp-label--on{% endif %}" -> uses_style to 'fp-label' (literal prefix);
                                                         the {% ... %} remainder -> a dynamic ambiguity
  class="fp-{{ icon }}"                               -> NO edge, a dynamic ambiguity (templated token)
  and NO bogus StyleClass 'if' / 'endif' / 'active' is emitted.

Run:  python builders/html/verify_class_usage.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_html_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "cssuse"


def _run() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="spashta_cssuse_"))
    dest = tmp / "cssuse"
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
    used = {id2name.get(e["to"], e["to"]).split("::")[-1]
            for e in frag["edges"] if e["edge"] == "uses_style"}
    classes = {n["name"] for n in frag["nodes"] if n["node_type"] == "StyleClass"}
    ambig = sum(1 for a in frag.get("ambiguities", []) if a["kind"] == "dynamic_class_unresolved")

    checks = [
        ("multi-token literal -> uses_style fp-card + fp-card--wide",
         {"fp-card", "fp-card--wide"} <= used),
        ("uses_style btn-primary + btn-busy", {"btn-primary", "btn-busy"} <= used),
        ("literal class before {% %} resolves (fp-label)", "fp-label" in used),
        ("literal class BETWEEN tags is now captured (fp-label--on) [dead-code-accuracy P1]",
         "fp-label--on" in used),
        ("NO bogus class from template keywords (if/endif/active not StyleClass)",
         not ({"if", "endif", "active"} & classes)),
        ("variable-split partial NOT emitted (fp-{{icon}} -> 'fp-' rejected)",
         "fp-" not in used and "fp" not in classes),
        ("templated attribute -> a dynamic_class_unresolved ambiguity", ambig >= 2),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
