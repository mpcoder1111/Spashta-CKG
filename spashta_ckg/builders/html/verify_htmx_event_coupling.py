"""Self-contained runnable proof for the HTMX event-listener coupling (spec/htmx-event-coupling.md US-1).

Runs the HTML builder on builders/tests/data/htmx_trigger_dummy.html and asserts the deterministic
contract: an hx-trigger with a `from:` clause emits a listens_to edge onto a BARE-named Event node
(the JS-dispatch coupling — joins by name with the JS builder's dispatches_event('<name>')); a plain
self-trigger does NOT; the [filter] is stripped; the existing triggers_event is preserved; a templated
event name is an ambiguity, not a guessed edge.

Run:  python builders/html/verify_htmx_event_coupling.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUILDER_DIR = Path(__file__).resolve().parent
BUILDER = BUILDER_DIR / "build_html_ast.py"
FIXTURE = BUILDER_DIR.parent / "tests" / "data" / "htmx_trigger_dummy.html"


def _run() -> dict:
    out = Path(tempfile.gettempdir()) / "spashta_htmx_coupling_fragment.json"
    subprocess.run(
        [sys.executable, str(BUILDER), "--source-root", str(FIXTURE), "--out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.read_text("utf-8"))


def main() -> int:
    frag = _run()
    by_id = {n["id"]: n["name"] for n in frag["nodes"]}
    events = {n["name"] for n in frag["nodes"] if n["node_type"] == "Event"}

    def targets(edge_type: str) -> set:
        return {by_id.get(e["to"], e["to"]) for e in frag["edges"] if e["edge"] == edge_type}

    listens = targets("listens_to")
    triggers = targets("triggers_event")
    ambig_exprs = {a["expression"] for a in frag["ambiguities"]}

    checks = [
        ("listens_to -> bare Event 'app:reload' (from:body)", "app:reload" in listens),
        ("listens_to -> bare Event 'app:sync' ([filter] stripped)", "app:sync" in listens),
        ("bare Event node 'app:reload' exists", "app:reload" in events),
        ("self-trigger 'click' has NO listens_to", "click" not in listens),
        ("existing triggers_event preserved (raw 'click' value)", "click" in triggers),
        ("dynamic '{{ live_event }}' event is an ambiguity, not a listens_to",
         all("live_event" not in t for t in listens)
         and any("live_event" in x for x in ambig_exprs)),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
