"""Proof that the class_selector regex captures a class regardless of the following combinator
(spec/css-coverage-roadmap.md P4 fix). Runs the CSS builder over builders/tests/data/cssdef/ and asserts:
  .foo.bar        -> BOTH foo AND bar (compound — foo was previously MISSED)
  .baz > .qux     -> baz + qux
  .attr[data-…]   -> attr    (attribute selector)
  .pseudo:hover   -> pseudo
  .plain          -> plain
  and NO bogus class from a value ('1.5em' / '0.3s' → no '5em'/'3s' StyleClass).

Run:  python builders/css/verify_compound_selector.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_css_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "cssdef"


def _run() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="spashta_cssdef_"))
    dest = tmp / "cssdef"
    shutil.copytree(FIXTURE, dest)
    out = tmp / "frag.json"
    subprocess.run([sys.executable, str(BUILDER), "--source-root", str(dest), "--out", str(out)],
                   check=True, capture_output=True, text=True)
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    classes = {n["name"] for n in frag["nodes"] if n["node_type"] == "StyleClass"}
    checks = [
        ("compound .foo.bar -> BOTH foo AND bar", {"foo", "bar"} <= classes),
        ("child .baz > .qux -> baz + qux", {"baz", "qux"} <= classes),
        ("attribute .attr[…] -> attr", "attr" in classes),
        ("pseudo .pseudo:hover -> pseudo", "pseudo" in classes),
        (".plain -> plain", "plain" in classes),
        ("no numeric-value false class (1.5em/0.3s)", not ({"5em", "3s"} & classes)),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
