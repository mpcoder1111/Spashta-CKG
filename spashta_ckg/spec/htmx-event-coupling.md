# Spec — HTMX event-listener coupling for Spashta-CKG (2.1)

**Status:** IMPLEMENTED (US-1) + proven · **Type:** Contribution spec (extends the JS support + HTMX adapter) ·
**Baseline:** git tag `pre-htmx-event-coupling` (created) · **Author:** Forms Portal team (real-world use
case, surfaced by `scripts/frontend_audit.py`)

## 0. As-built — US-1 done (additive; existing behaviour preserved)

The vertical slice is implemented and proven. Files touched (all additive — no other builder/adapter changed,
core untouched except one allowlist widening):

- `core/software_schema/edges.json` — `listens_to.from` widened `[Function, Method]` → `+[Template, Fragment]`
  (an allowlist widening; every existing `listens_to` edge stays valid).
- `builders/html/html_language_mapping.json` — the `hx-trigger` rule gains `"listener_edge": "listens_to"`.
- `builders/html/build_html_ast.py` — `_collect_allowed_edges` registers a rule's optional `listener_edge`;
  `_process_interaction` emits the **existing `triggers_event` unchanged**, then (when the rule declares a
  `listener_edge`) `_emit_htmx_listeners` splits the `hx-trigger` value into clauses and, for each clause
  carrying a **`from:`** modifier, emits a `listens_to` edge onto an Event node named by the **bare event
  name** (a trailing `[filter]` + modifiers stripped). A templated/dynamic name (`{{ … }}` or a configured
  dynamic pattern) → `emit_ambiguity("unresolved_event")`, never a guessed edge. `import re` added.
- `builders/tests/data/htmx_trigger_dummy.html` — fixture (from:body, a `[filter]`, a self-trigger, a
  dynamic name). `builders/html/verify_htmx_event_coupling.py` — self-contained runnable proof.

**Proof:**
- Fixture verifier: `python builders/html/verify_htmx_event_coupling.py` → **6/6 PASS** (listens_to→bare
  `app:reload`; `[filter]` stripped → `app:sync`; self-trigger `click` has NO listens_to; `triggers_event`
  preserved; dynamic `{{ live_event }}` is an ambiguity not an edge). Fragment validates:
  `validate_builder_output.py builders/tests/outputs/htmx_trigger_fragment.json` → **status: pass**,
  `schema_errors: []`.
- On the Forms Portal graph (rebuilt): `fp:share-open` and `fp:reference-open` now show **COUPLED=True** — a
  JS `dispatches_event` (from `builder.js`) joins BY NAME with a template `listens_to` (from `builder.html`),
  the two false orphans `scripts/frontend_audit.py` flagged. **11 `listens_to` edges** emitted.
- **Additive:** `triggers_event` **63 → 63** (preserved — the HTMX adapter's Component detection unaffected);
  `dispatches_event` **8 → 8**; `listens_to` **0 → 11** (new). Graph 19539n/28261e → 19569n/28298e.

**Node-join model (as js-support §0d):** the template `listens_to` lands on a per-emitter placeholder
`…/builder.html::Event::fp:share-open`; the JS `dispatches_event` on `js::event::fp:share-open` — **joined BY
NAME** (both `fp:share-open`), not merged into one node. The polluted `…::Event::fp:share-open from:body` node
from the untouched `triggers_event` still exists; folding same-`(type,name)` Event nodes into one is the
general merger enhancement (js-support §0d) — deferred to the maintainers.

## 1. Intent

Make an HTMX `hx-trigger="<event> from:<target>"` a **listener** on the SAME Event node that a JS
`dispatchEvent(new CustomEvent('<event>'))` targets — so the cross-language coupling *"this event is
dispatched in JS and listened for by this template"* is queryable. Today that coupling is invisible: the JS
dispatcher and the HTMX listener land on **different** Event nodes, so `query_spashta.py impact` on the event
shows the dispatcher OR the listener, never both, and any orphaned-event audit reports **false positives**.

This is the direct fix for the finding in the Forms Portal frontend ruggedization pass: `fp:share-open` and
`fp:reference-open` (dispatched by `builder.js`) looked like orphans, but are genuinely heard via
`hx-trigger="fp:share-open from:body"` in `builder.html`. The portal's `test_frontend_contracts` guard works
around this by scanning templates for `hx-trigger` directly; this spec removes the need for that workaround at
the *graph* level.

## 2. Motivation (the gap — grounded, not assumed)

Verified against the live graph (`code_knowledge_graph_enriched.json`) and the HTML builder mapping:

- **The event name is not parsed.** `builders/html/html_language_mapping.json` maps `hx-trigger` →
  `triggers_event` (`target_node_type: Event`) but uses the **entire attribute value** as the Event NAME:
  - `hx-trigger="fp:share-open from:body"` → Event node **`fp:share-open from:body`** (modifier included);
  - `hx-trigger="click[!event.target.closest('.dc-row-actions') && …]"` → Event node named after the **whole
    filter expression**. The bare event name (`fp:share-open`, `click`) is never isolated.
- **The nodes don't join.** The JS builder emits `dispatches_event → js::event::fp:share-open` (bare, global
  by-name); the HTML builder emits `triggers_event → …/builder.html::Event::fp:share-open from:body` (scoped,
  name-polluted). Two different nodes → no coupling, even by name (the names differ).
- **Wrong semantics.** `triggers_event` models the template as the *dispatcher*. But an `hx-trigger` with a
  `from:` clause (or any custom event) means the element **listens** for an event fired elsewhere — the sibling
  of JS `registers_event_handler`, not a dispatch.

Net effect on the graph today (2 real examples): `fp:share-open` and `fp:reference-open` each have a JS
`dispatches_event` and a template `triggers_event` on **separate, name-mismatched** Event nodes → the
"dispatched here, listened there" coupling the js-support spec set out to make visible is still invisible for
the HTMX-listener half.

## 3. Design principles (reuse, don't reinvent — same as js-support)

1. **Reuse the pipeline verbatim.** Only the HTML builder's `hx-trigger` handling changes (+ at most one edge
   in `core/software_schema/edges.json`). The JS builder, the core runtime, and every other builder/adapter
   are **untouched**. Additive.
2. **Determinism by the existing seam.** An `hx-trigger` event name is a **literal** in the template
   (`fp:share-open`, `click`), so the edge is always deterministic. Modifiers/filters (`from:`, `delay:`,
   `[…]`) are **edge metadata**, never part of the node name. A fully templated/`{{ var }}` trigger (rare) →
   `emit_ambiguity("unresolved_event")`, never a guessed edge.
3. **Canonical Event node, joined by name.** Normalise the Event node to the **bare event name** so the HTMX
   edge lands on the same by-name node the JS builder uses (`Event:<name>` / `js::event::<name>` — pick ONE
   shared canonicalisation both emitters use). This is the exact placeholder-per-emitter-joined-by-name model
   the shipped `queries_dom` (JS→StyleClass) and HTMX `calls_api` (→Route) features already follow.
4. **Opt-in.** Rides the already-active `htmx` framework / `html` language — no new flag; a project without
   HTMX is unaffected (no `hx-trigger` → no edges).

## 4. Design — the slice (US-1)

**One question, end-to-end:** *"Which templates listen (via HTMX) for the custom event this JS dispatches?"*

1. **Parse `hx-trigger` into clauses.** Split on `,` (HTMX allows multiple triggers). For each clause, take the
   **first whitespace-delimited token, stripped of a trailing `[…]` filter**, as the bare event name; the rest
   (`from:body`, `delay:500ms`, `once`, the filter) is captured as **edge metadata** (`modifiers`, `filter`).
2. **Canonicalise the Event node by bare name** (shared with the JS builder's convention) so `fp:share-open`
   from the template and `fp:share-open` from JS are the SAME node.
3. **Emit the right edge by semantics:**
   - a clause **with a `from:` clause** (listening for an event fired on another element — the JS-dispatch case)
     → the **listener** edge (reuse `registers_event_handler`, the JS listener sibling, so JS `addEventListener`
     and HTMX `hx-trigger from:` are ONE queryable "listeners" set; OR a new `listens_to` if the schema prefers
     a template-source distinction — decide at build time, prefer reuse);
   - a plain self-trigger (`hx-trigger="click"`, no `from:`, a native event on the element itself) → keep the
     existing `triggers_event`.
4. **Determinism contract** (identical to js-support §8): literal event name → deterministic edge; templated /
   dynamic → `emit_ambiguity(confidence="unresolved")`.

**Schema:** prefer reusing `registers_event_handler` (source widened to `Template`/`Element`) over inventing an
edge; if the `SchemaEnforcer`'s source/target rules make that unclean, add a minimal `listens_to`
(`Template/Element → Event`) to `edges.json` — one additive edge, existing edges untouched.

## 5. Acceptance (against the Forms Portal corpus)

- `fp:share-open` and `fp:reference-open` each become **ONE** Event node carrying a `dispatches_event`
  (`builder.js`) **and** a listener edge (`builder.html`); `query_spashta.py impact "…::Event::fp:share-open"`
  returns **both** the JS dispatcher and the HTMX-listening template.
- A **graph-only** orphaned-event check (dispatched-with-no-listener over `dispatches_event` vs the union of
  `registers_event_handler` + the new HTMX listener edges) returns **0** — i.e. `scripts/frontend_audit.py`'s
  template-scan workaround is no longer needed for correctness (it can then read the coupling straight from the
  graph).
- **Existing graph unchanged with the change OFF / for non-`from:` triggers** — node/edge counts for a run
  without any `hx-trigger from:` are identical (additive proof, like js-support §9). The `triggers_event` count
  for plain self-triggers is preserved.

## 6. Failsafe

- Baseline **git tag `pre-htmx-event-coupling`** — revert point.
- **Additive only:** the HTML builder's `hx-trigger` branch + (at most) one `edges.json` addition; JS
  builder + core + other builders untouched. Verify by rebuilding the portal graph and diffing counts.
- A fixture (`builders/tests/data/` + the harness convention) with a literal `hx-trigger="evt from:body"` + a
  matching JS `dispatchEvent('evt')`, plus a `verify_*` runnable proof asserting the two couple on one node,
  and a templated `hx-trigger="{{ x }}"` proven to be an ambiguity — mirrors `verify_js_mvp.py`.

## 7. Out of scope (deferred)

Full HTMX trigger-modifier semantics (`delay`/`throttle`/`queue` timing); `hx-trigger` polling
(`every 2s`); non-`from` DOM-bubbling nuances; the general same-`(type,name)` node-merger fold (js-support §0d
— helps here too but is a core merger enhancement owned by the maintainers). Tackle only after the literal
event-name coupling is proven.
