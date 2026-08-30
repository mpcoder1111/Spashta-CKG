"""Self-contained runnable proof for @keyframes / animation modeling (spec/css-coverage-roadmap.md P2).

Copies builders/tests/data/cssanim/ to a temp dir OUTSIDE Spashta-CKG (the scanner excludes its own tree),
runs the CSS builder, and asserts:
  @keyframes spin-a/spin-b/wobble        -> 3 Keyframes nodes + defines edges
  spin-a and spin-b have IDENTICAL body_hash (dup detection); wobble differs
  animation: spin-a … / animation-name: spin-b  -> uses_animation to spin-a + spin-b
  wobble is DEFINED but NOT used (dead-animation candidate)
  NO StyleElement 'to'/'from'/'transform' leaks; NO 'linear'/'infinite' Keyframes (stopwords/units filtered)

Run:  python builders/css/verify_animations.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER = Path(__file__).resolve().parent / "build_css_ast.py"
FIXTURE = BUILDER.parent.parent / "tests" / "data" / "cssanim"


def _run() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="spashta_cssanim_"))
    dest = tmp / "cssanim"
    shutil.copytree(FIXTURE, dest)
    out = tmp / "frag.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(dest), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    kf = {n["name"]: n for n in frag["nodes"] if n["node_type"] == "Keyframes"}
    id2name = {n["id"]: n.get("name") for n in frag["nodes"]}
    used = {id2name.get(e["to"], e["to"]).split("::")[-1]
            for e in frag["edges"] if e["edge"] == "uses_animation"}
    style_elems = {n["name"] for n in frag["nodes"] if n["node_type"] == "StyleElement"}

    checks = [
        ("3 Keyframes nodes (spin-a, spin-b, wobble)", {"spin-a", "spin-b", "wobble"} <= set(kf)),
        ("spin-a and spin-b have IDENTICAL body_hash (dup)",
         "spin-a" in kf and "spin-b" in kf and kf["spin-a"].get("body_hash") == kf["spin-b"].get("body_hash")),
        ("wobble body_hash differs", "wobble" in kf and kf["wobble"].get("body_hash") != kf.get("spin-a", {}).get("body_hash")),
        ("uses_animation -> spin-a + spin-b", {"spin-a", "spin-b"} <= used),
        ("wobble is DEFINED but UNUSED (dead-animation candidate)", "wobble" not in used),
        ("no to/from/transform StyleElement leak", not ({"to", "from", "transform"} & style_elems)),
        ("no timing keyword became a Keyframes (linear/infinite)", not ({"linear", "infinite"} & set(kf))),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
