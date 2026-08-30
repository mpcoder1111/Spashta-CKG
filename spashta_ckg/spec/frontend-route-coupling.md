# Spec — Frontend→Django route coupling for Spashta-CKG (2.1)

**Status:** IMPLEMENTED (US-1 + US-1b + US-2) + proven · **Type:** Contribution spec (Django URLconf
modelling + template `{% url %}` resolution + query by-name fallback) · **Baseline:** git tag
`pre-route-coupling` (created) · **Author:** Forms Portal team (real-world use case — an HTMX-heavy Django app)

## Rule conformance (builder_rules.json) — audited

`emit_only_observed_nodes` ✓ (a Route is observed from a `path()` call). `do_not_infer_semantics` ✓ —
detection is a STRUCTURAL pattern (a call to a configured name), the same class as
`node_classification_policy` (Field/Constant/TestCase) and `string_reference_policy` (extract a string arg
from a known function → match a node → emit an edge). `edge_emission_policy.emit_only_if_mapping_exists` ✓
(`resolves_to` is in `edge_mappings`). `symbolic_reference_policy` / ambiguity ✓ (dynamic name / unproven
view → an ambiguity, never a guessed edge). **Two-pass correction (US-2):** the Route NODE is registered in
**pass 1** (StructureWalker, like Field/Constant), the `resolves_to` EDGE in **pass 2** (RelationWalker) — the
first cut wrongly registered the node in pass 2; the refactor is behaviour-preserving (215 → 215 before US-2's
resolver upgrades). View resolution returns a **proven** id or one-or-none `(app, unique-name)` match — never
a multi-candidate guess.

## 0. As-built — US-1 + US-1b done (additive; config-gated; framework-agnostic by config)

Files touched (all additive — the route model is off when `route_registrations={}`; existing structural
edges untouched):

- `core/software_schema/edges.json` — new `resolves_to` edge (`Route → Function/Method/Class`).
- `builders/python/python_language_mapping.json` — `edge_mappings.resolves_to` + a **config-driven,
  framework-agnostic `route_registrations`** block: `django = {call_names:[path,re_path,url], name_kwarg:name,
  view_arg_index:1, namespace_var:app_name}`. A new framework = a new entry (no builder change).
- `builders/python/build_python_ast.py` — the `SchemaEnforcer` stores `route_registrations`; the
  `RelationWalker` gains `visit_Module` (capture `app_name` → normal pass-2 traversal → `_extract_routes`)
  which walks for a configured route-registration call, and for each `name=<literal>` registers a **Route
  node `app_name:name`** + a **`resolves_to` edge to the view** (resolved via an import map: `views.foo` →
  `pkg/views.py::foo`, with the builder's own resolver as fallback). A dynamic `name=` → `unresolved_route`
  ambiguity; an unproven view (CBV `.as_view()`, string path) → `unresolved_route_view`. Never a guessed edge.
- `builders/html/build_html_ast.py` — a Route-target attribute value matching `{% url 'name' … %}` resolves
  to the **bare url-name** (args → dropped), so the template's `calls_api` Route joins BY NAME to the Python
  Route. A dynamic `{% url var %}` / `{{ … }}` is left as a full-value placeholder (no regression).
- `runtime/query_spashta.py` (US-1b) — `trace_deps` (behind `impact`/`dependencies`) expands a
  **placeholder** node (Route/Event/StyleClass) to its same-`(type,name)` siblings and follows their edges as
  ONE logical node, **at every hop** — so a multi-hop query crosses the cross-emitter boundary: e.g.
  `impact "<view>" --depth 2` → the view's urls.py Route → its template-side Route siblings → the **templates
  that hx-get it** ("change this view → what frontend breaks?"). `impact "app:url-name"` → the templates;
  `dependencies "app:url-name"` → the view. Non-placeholder traversals are unchanged. Benefits the earlier
  event + selector work too.
- Fixture `builders/tests/data/route_urls_dummy.py` + `route_template.html`;
  `builders/python/verify_route_coupling.py` — self-contained proof (**8/8 PASS**).

The view resolver is TIERED (US-2), each tier deterministic (never a multi-candidate guess), and every edge
carries a `confidence`:
- **structural** (proven): a function view `views.foo` via the import map (`module.py::foo` exists), or the
  builder's own symbol table (a direct `from x import view`; a same-module def).
- **heuristic** (labelled, `heuristic_policy`): a one-or-none `(app, unique-name)` match — the app being the
  import module's app OR **this urls.py's own app** (Django convention: an app's urls.py serves its own
  views). Covers a **CBV** `MyView.as_view()` (unwrap → resolve the class), a **decomposed views PACKAGE**
  `app/views/` re-exporting the def, a relative `from . import views`, and a root URLconf importing another
  app's view by bare name. `>1` candidate → skip (ambiguity), never a guess.
- unresolvable (string-path, a genuinely 3rd-party/absent view) → `unresolved_route_view` ambiguity.

**Proof (Forms Portal corpus):** **379 `resolves_to`** edges — **100%** of routes, **0** unresolved —
split **214 structural** (proven) + **165 heuristic** (labelled, so a consumer can keep only proven edges).
`query_spashta.py impact "data_collections:dataset_worklist"` → the **3 templates** that `hx-get` it;
`dependencies "…dataset_worklist"` → the **view** `dataset_worklist_settings`. Route nodes 571 → 925.
Fixture verifier **9/9 PASS** (incl. the CBV case).

**Additive:** structural edges stable (`defines` 13899, `imports` 7625, `contains_member` 2431, `has_field`
563, `extends` 114); `resolves_to` 0 → 215 (new); `calls_api` 558 → 535 (the intended url-name **dedup** — two
`{% url 'x' a %}`/`{% url 'x' b %}` in one template now share one `Route('x')`). Python route extraction is
config-gated (`route_registrations={}` → `visit_Module` == plain `generic_visit`, no route work). Node-join is
BY NAME (js-support §0d); the same-`(type,name)` merger fold stays deferred (the US-1b query fallback covers
the CLI need). Baseline tag: `pre-route-coupling`.

## 1. Intent

Answer the question a frontend-heavy team asks constantly: **"which Django view does this `hx-get` /
`href` / form call, and what breaks if I rename this URL?"** — the frontend↔backend impact edge, the mirror
of what `query_spashta.py impact` already gives Python.

Concretely: resolve a template's `hx-get="{% url 'app:name' … %}"` (and `href`, `hx-post`, `action`) to the
**Django route** `app:name` and its **view function**, so `impact "Route::app:name"` returns BOTH the view
that serves it AND every template/element that calls it.

## 2. Motivation (the gap — grounded, not assumed)

Verified against the live graph (`code_knowledge_graph_enriched.json`):

- **Templates already emit `calls_api` (558 edges) — but to a dead placeholder.** The HTML builder maps
  `hx-get`/`hx-post`/`action`/`href` → `calls_api` → a **Route node named by the RAW attribute string**, e.g.
  `Route::{% url 'data_collections:dataset_worklist' d.id %}` (the whole template tag, args included).
  **453 of 571 Route nodes are `{% url … %}` placeholder strings.**
- **There is NO Django-side route model.** No URLconf node, no url-name Route, no `view → route` edge
  (`handles_route`/`resolves_to` — 0 edges). The Python builder never reads `urls.py`. So the `calls_api`
  target resolves to **nothing on the backend**: you can see "this template calls *some* url tag", never
  "this template calls the `dataset_worklist` **view**".
- **JS `fetch('/path')` → Route is a non-issue here** (0 `calls_api` from a `.js` file; an HTMX app uses
  `hx-*` in templates, not `fetch`). It stays **deferred** (framework-specific URL parsing, low value).

Net: the frontend↔backend edge — the single most useful frontend impact query — is invisible. Rename a URL
name or move a view and Spashta can't tell you which `hx-get` breaks.

## 3. Design principles (reuse, don't reinvent — same as js-support / htmx-event-coupling)

1. **Reuse the pipeline + the existing `calls_api` edge.** Add a **Django URLconf source** (a small builder
   or a Python-builder/adapter rule) that emits a **Route node named by the url-name** (`app:name`) with a
   `resolves_to` edge to the **view** it maps to. Reuse `calls_api` for the template side.
2. **Deterministic by the existing seam.** `{% url 'literal-name' args %}` has a **literal** name → resolve
   the Route node NAME to the bare `app:name` (args are edge metadata). `{% url variable %}` / `{{ dyn }}` /
   a computed reverse → `emit_ambiguity("unresolved_route")`, never a guessed edge.
3. **Join BY NAME (js-support §0d).** The template's `calls_api → Route('app:name')` and the URLconf's
   `Route('app:name') → resolves_to → view` are placeholder-per-emitter, **joined by the url-name** — the
   same model as `queries_dom`→CSS and the htmx-event-coupling `listens_to`.
4. **Opt-in / additive.** A new builder/adapter gated behind the active `django` framework; the Python/HTML/JS
   builders + core are otherwise untouched (at most one `resolves_to` edge added to `edges.json`). A non-Django
   project is unaffected.

## 4. Design — the slice (US-1)

**One question, end-to-end:** *"Which view serves this url-name, and which templates call it?"*

**(a) Model the Django URLconf.** Parse `urls.py` (`path()`/`re_path()`/`url()` + `include()` with an app
`namespace`) into, per pattern with a `name=`:
   - a **Route node** named by the fully-qualified url-name (`app_namespace:name`, or bare `name` when
     un-namespaced);
   - a **`resolves_to` edge** Route → the **view** (a `Function`/`Method`/CBV `Class`) — deterministic when the
     view is a direct import reference; a string view path / lambda → ambiguity.
   Reuse the Python builder's import resolution to land the view on its real node id. (Where a clean
   Python-builder rule isn't possible, ship it as a tiny dedicated `builders/django_urls/` reader — additive.)

**(b) Resolve the template `{% url %}` placeholder to the bare url-name.** In the HTML builder's `calls_api`
   emission, when the attribute value matches `{% url 'app:name' … %}`, use **`app:name`** as the Route node
   name (args → edge metadata), instead of the whole tag string. A dynamic `{% url variable %}` →
   `emit_ambiguity("unresolved_route")`. (`href`/`action` with a literal `/path/` stays as today or is a v2
   path-resolver — out of scope for US-1, which targets the `{% url %}` form our templates actually use.)

**(c) The coupling falls out by name.** `impact "Route::app:name"` now returns the view (`resolves_to`) AND
   every template that `calls_api` it.

**Determinism contract** (identical to the prior specs):

| Case | Builder action |
|------|----------------|
| `{% url 'literal:name' … %}` / a directly-imported view | **deterministic edge** (Route named `literal:name`; `resolves_to` → the view) |
| `{% url variable %}` / a string-path view / a computed reverse | **`emit_ambiguity("unresolved_route")`** — never a guessed edge |

## 5. Acceptance (against the Forms Portal corpus)

- A URLconf Route node `data_collections:dataset_worklist` exists with a `resolves_to` edge to the
  `dataset_worklist` view; `query_spashta.py impact "…Route::data_collections:dataset_worklist"` returns the
  **view** + the **templates** whose `hx-get`/`href` call it (e.g. `dataset_worklist.html`, the home nav).
- The 453 `{% url %}` placeholder Route names collapse onto the **bare url-names** (a `{% url 'x' a %}` and a
  `{% url 'x' b %}` in two templates land on the SAME `Route::x`).
- **Additive:** with the `django` URLconf source OFF, node/edge counts are identical; `calls_api` count is
  preserved (only the Route *name* it points to is resolved). Python/HTML/JS builders otherwise untouched.
- (Optional, US-1b) `query_spashta.py impact` gains a **by-name fallback** for placeholder node types
  (Route/Event/StyleClass) so the cross-emitter coupling resolves from the CLI without a merged node — the
  cheap win noted in the htmx-event-coupling retro; benefits events + selectors too.

## 6. Failsafe

- Baseline **git tag `pre-route-coupling`** — revert point.
- **Additive only:** a new URLconf source + the HTML `{% url %}` name-resolution + (at most) one `resolves_to`
  edge in `edges.json`; existing builders/edges untouched. Verify by rebuilding and diffing counts with the
  source OFF (identical).
- Fixtures + a `verify_route_coupling.py` runnable proof: a `urls.py` with `path('x/', views.x, name='x')` +
  a template `hx-get="{% url 'x' %}"` → assert the Route('x')→view `resolves_to` and the template→Route('x')
  `calls_api` couple on the bare name; a `{% url variable %}` proven to be an ambiguity.

## 7. Out of scope (deferred)

JS `fetch('/path')` / `hx-*`-in-JS → Route (we don't use `fetch`; framework-specific path parsing — a later
slice); literal `/path/` → route resolution (needs URL-pattern matching, not just name lookup); `{% url %}`
**argument/arity** validation against the pattern; class-based-view method granularity; the general
same-`(type,name)` node-merger fold (js-support §0d — the by-name join carries US-1). Tackle only after the
literal url-name coupling is proven.
