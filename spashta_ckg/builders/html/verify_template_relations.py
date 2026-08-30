"""Self-contained runnable proof for template inheritance/includes (spec/fullstack-coupling-roadmap.md P1).

Copies builders/tests/data/tpl/ to a temp dir OUTSIDE Spashta-CKG (the scanner excludes its own tree),
runs the HTML builder over it, and asserts: {% extends "tpl/base.html" %} -> extends_template (page→base);
{% include "tpl/_partial.html" %} -> includes_template (page→partial). Both target the physical Template
matched by its /templates/-relative logical name.

Run:  python builders/html/verify_template_relations.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_html_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "tpl"


def _run() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="spashta_tpl_"))
    dest = tmp / "tpl"
    shutil.copytree(FIXTURE, dest)
    out = tmp / "frag.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(dest), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()

    def pairs(etype: str) -> set:
        return {(e["from"].split("/")[-1], e["to"].split("/")[-1])
                for e in frag["edges"] if e["edge"] == etype}

    extends = pairs("extends_template")
    includes = pairs("includes_template")

    checks = [
        ("{% extends %} -> extends_template page.html -> base.html",
         ("page.html", "base.html") in extends),
        ("{% include %} -> includes_template page.html -> _partial.html",
         ("page.html", "_partial.html") in includes),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
