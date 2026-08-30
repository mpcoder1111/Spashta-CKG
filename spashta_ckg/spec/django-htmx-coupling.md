# Spec — Django/HTMX call couplings for Spashta-CKG (2.1)

**Status:** IMPLEMENTED + proven · **Type:** Contribution spec (config-driven Python call couplings) ·
**Baseline:** git tag `pre-django-htmx-coupling` (created) · **Author:** Forms Portal team (extensive
real-world use of Spashta on a Django + HTMX app)

## 0. As-built — done (additive; config-gated; pattern-driven)

Three cross-language couplings that a full-stack Django+HTMX app needs, all the SAME pattern (detect a known
call → extract a LITERAL string arg → match/emit a target node + edge), driven by ONE config
`call_couplings` so a new coupling = a new entry (no builder change):

- **A. `render()` → template** (`renders_template`, `Function → Template`). Implements the DEFINED-but-
  unimplemented `builder_rules.json` `string_reference_policy` (known_template_functions render / get_template
  / render_to_string / select_template). *"Which view renders this template?"* — the missing half of
  view↔template (the route work did template→view). **177 edges** on the portal.
- **B. `reverse()` / `redirect()` / `reverse_lazy('app:name')` → route** (`calls_api`, `Function → Route` —
  `calls_api.from` widened to add Function/Method). A Python view referencing a url-name now couples to the
  Route registered from `urls.py` (an EXACT in-registry match — the Route nodes are built in the same Python
  run). So `impact "app:name"` shows the templates that hx-get it AND the **views that redirect to it**.
  **161 edges**.
- **C. HX-Trigger helper → JS event** (`dispatches_event`, `Function → Event`). A configured HX-Trigger
  function (`_append_hx_trigger(resp, 'rvRefresh', …)` — the project declares its helper + the event-name arg
  index) emits a `dispatches_event` onto an Event named by the literal, which **joins the JS listener by name**
  at merge. Completes the event picture (JS-dispatch→HTMX-listen from the earlier spec; this is
  Python-dispatch→JS-listen). Proof: `showToast` is now dispatched by `notify_toast` AND listened by
  `helpers.js`.

**Files (all additive):** `core/software_schema/edges.json` (`renders_template` added; `calls_api.from`
widened) · `builders/python/python_language_mapping.json` (edge mappings + the `call_couplings` config) ·
`builders/python/build_python_ast.py` (`SchemaEnforcer` stores `call_couplings`; `RelationWalker.visit_Call`
gains `_couple_call` — a literal-arg → edge emitter; a cross-builder target (Template/Event not in the Python
registry) becomes a by-name/path reference placeholder joined at merge, js-support §0d) ·
`runtime/query_spashta.py` (a **Template** joins by its logical, `/templates/`-relative name so a render()
placeholder and the physical HTML Template unite) · fixture `django_coupling_dummy.py` +
`verify_django_htmx_coupling.py` (**4/4 PASS**).

**Determinism / rules:** a literal string arg → a deterministic edge; a non-literal → `unresolved_coupling`
ambiguity (never a guess). Structural policy (`string_reference_policy` / a call pattern), like the route
work. Structural edges stable (`defines`/`imports`/`contains_member` unchanged). Config-gated
(`call_couplings={}` → off). Node-join by name/logical-path (§0d).

**CLI queries this unlocks (Forms Portal, proven):**
- `impact "Template:…/dataset_table.html"` → `data_collections/views.py::dataset_table` (which view renders it).
- `impact "app:name"` → templates + Python views that reverse to it; `dependencies` → the serving view.
- `impact "showToast"` → the Python dispatcher (`notify_toast`) + the JS listener (`helpers.js`).

## 1. Intent

Extend the frontend↔backend coupling to the remaining Django/HTMX call patterns we hit constantly, so
Spashta's `impact` spans render/redirect/HX-Trigger — not just `hx-get`/`{% url %}`.

## 2. Motivation (grounded)

`renders_template` was **0** edges (a defined, unimplemented policy); **0** Python→Route edges (`references`
is model-only); and JS events (`showToast`, `rvRefresh`, `saved`) were listened in JS but never dispatched —
fired server-side via the `HX-Trigger` response header, invisible to Spashta.

## 3. Design principles

Reuse the pipeline + the ONE call-coupling config; deterministic-when-literal (else ambiguity); cross-builder
targets are by-name/path placeholders joined at merge (never a builder dependency); opt-in / additive; a new
coupling or framework helper is a config entry, not code.

## 4. Determinism contract

| Case | Action |
|------|--------|
| Known call, arg is a **string literal** | deterministic edge to an existing node OR a by-name/path placeholder |
| Known call, arg is **dynamic** (var, f-string, computed) | `emit_ambiguity("unresolved_coupling")` |

## 5. Out of scope (deferred)

`HttpResponse(headers={'HX-Trigger': json.dumps({…})})` inline (event names buried in a JSON dict literal — a
follow-up); `render()` with a **variable** template name; `include()` URL-namespace trees; the same-`(type,
name)` node-merger fold (the query by-name/logical join carries it).
