# Spec — JavaScript support for Spashta-CKG (2.1)

**Status:** MVP (US-1) IMPLEMENTED + proven · **Type:** Contribution spec (new language builder) ·
**Baseline:** git tag `pre-js-support` · **Author:** Forms Portal team (real-world use case, as with the HTMX adapter)

## 0. As-built — MVP (US-1) done

The vertical slice is implemented and proven. Files added (additive; no existing builder/adapter/schema
behaviour changed):
- `builders/js/build_js_ast.py` — the Tree-sitter builder (File + Function nodes + the core `calls` edge).
- `builders/js/js_language_mapping.json`, `builders/js/builder_js_instructions_for_builder_code_development.json`.
- `builders/js/requirements.txt` — `tree-sitter>=0.23`, `tree-sitter-javascript>=0.23` (first 3rd-party dep).
- `builders/js/verify_js_mvp.py` — self-contained runnable proof.
- `builders/tests/data/js_dummy.js` + `builders/tests/configs/js_config.json` — fixture + config (harness convention).

**Design as built:** two passes over the whole JS file set (one fragment) — pass 1 registers every File +
Function definition (function declarations, `X.y = function/arrow`, and object-literal function-valued members
like `window.fp = { showToast: function(){} }`); pass 2 resolves each call site against the def registry and
emits `calls` **only when the callee resolves to exactly one definition**. An external / cross-language /
dynamic callee becomes `emit_ambiguity(confidence="unresolved")` — never a guessed edge. Cross-file resolution
works because the orchestrator runs one builder over all of a language's files → one fragment → one registry;
namespaced functions get a global name-based id so a call in another file lands on the same node.

**Proof:**
- On the Forms Portal JS: `window.fp.showToast`/`showBanner`/`showError` defs found in `helpers.js`, with
  **17 cross-file `calls` edges** onto `window.fp.*` from `builder.js`, `viewer.js`, `component_gallery.js`
  (the exact "who calls this?" answer US-1 targets), plus the `showError → showBanner` alias delegation.
  Run: `169 nodes, 461 edges, 1960 ambiguities`; **`validate_builder_output.py` → status: pass**.
- Fixture verifier: `python builders/js/verify_js_mvp.py` → all 5 deterministic checks PASS (incl. an external
  callee proven to be an ambiguity, not an edge).

**Opt-in (no disturbance to existing runs):** `project/profile.json` lists active `languages: [python, html,
css]` and excludes javascript, and the orchestrator only runs builders for active languages — so the JS
builder does **not** run in a normal `spashta_refresh.py` until a maintainer adds `"js"` to `languages`. It is
invocable directly meanwhile: `python builders/js/build_js_ast.py --source-root <proj> --out fragment_js.json`.

## 0b. As-built — Phase 2, slice 1: intra-JS event coupling (done)

The first cross-cutting slice: couple an event's **dispatchers** and **listeners** through one shared
`Event` node — the intra-JS slice (both endpoints are JS → provable within the builder like `calls`), and
the direct fix for "an event dispatched in one file, listened in another" invisible coupling.

- `addEventListener('evt', …)` → `registers_event_handler` (enclosing Function/File → Event) [existing edge].
- `X.dispatchEvent(new CustomEvent('evt'))` / `new Event('evt')` → **`dispatches_event`** (enclosing → Event)
  — **one additive edge** added to `core/software_schema/edges.json` (the JS sibling of the existing
  `triggers_event` Template→Event; existing edges untouched, existing builders unaffected).
- A non-literal event name (a variable / event object) → `emit_ambiguity("unresolved_event")`, never a
  guessed edge. Event methods no longer become `unresolved_call` noise (portal ambiguities 1960 → 1751).

**Proof:** on the portal JS, distinct custom `Event` nodes captured (`fp:share-open`, `showToast`,
`openDialog`, `closeDialog`, `saved`, `htmx:*`) with the coupling queryable — e.g. `fp:share-open` is
**dispatched by `builder.js` with no JS listener** (a real finding: the listener is elsewhere/server-side or
dead), while `showToast`/`openDialog` are **listened for in `helpers.js` with no JS dispatcher** (correct —
they are triggered server-side via HTMX `HX-Trigger`). Run: `208 nodes, 670 edges, 1751 ambiguities`;
**`validate_builder_output.py` → status: pass**; `verify_js_mvp.py` → 8/8.

## 0c. As-built — the Vanilla-JS ADAPTER (done, the "like HTMX" layer)

Semantic roles for Vanilla-JS, added exactly the way HTMX was — a `framework_mapping.json` adapter
(Level-1, rule-based, deterministic, additive; annotates roles on nodes the builder already emits, never
mutates structure). **No builder change, no core change.**

- `adapters/vanilla/framework_mapping.json` — rule: a `Function` with an outgoing `registers_event_handler`
  or `dispatches_event` edge IS an event handler/producer → the core **`Signal`** role. Detected via
  `has_outgoing_edge`, the identical mechanism the HTMX adapter uses to detect `Component`
  (calls_api/triggers_event/submits_form). Activate by adding `"vanilla"` to `project/profile.json`
  `frameworks` (opt-in, like the `js` language).
- `builders/js/verify_vanilla_adapter.py` — reuses the REAL engine logic
  (`enrich_runtime_ast.apply_enrichment_logic`), no re-implementation.

**Proof:** `validate_adapter_rules.py adapters/vanilla/framework_mapping.json` → **status: pass** (Signal is a
core node type; `has_outgoing_edge` is a valid rule). `verify_vanilla_adapter.py` → 4/4: `init` + `fireRefresh`
tagged `Signal`, the non-event `helper`/`run` correctly untagged. On the merged graph this makes "all JS event
participants" a first-class queryable role, the vanilla sibling of HTMX's Component/Fragment tagging.

## 0d. As-built — DOM-selector cross-language edges (done) + the cross-language model finding

`queries_dom` — a JS function that selects a DOM element by a **literal** class/id links to a
`StyleClass`/`StyleID` node named by the selector:
- `getElementById('x')` → `StyleID 'x'`; `getElementsByClassName('x')` → `StyleClass 'x'`;
  `querySelector('.c')`/`querySelectorAll('#i')` → a single simple `.class`/`#id` only.
- A compound/dynamic selector (`.a .b`, `[data-x]`, a variable) → `unresolved_selector` ambiguity, never a
  guess. New additive edge `queries_dom` (`Function/Method/Hook/File → StyleClass/StyleID`) in `edges.json`.
- Proof: on the portal JS, **183 `queries_dom` edges**, 49 `StyleClass` + 81 `StyleID` targets;
  `validate_builder_output.py` → status: pass; `verify_js_mvp.py` → 13/13; ambiguities 1751 → 1505.

**IMPORTANT cross-language finding (verified, not assumed).** I tested whether a JS `StyleClass` placeholder
*merges into one node* with the CSS definition, and it does **not** — the CSS builder gives classes
**scoped** ids (`…/main.css::StyleClass::name`) while a by-name placeholder canonicalises to
`StyleClass:name`, and the merger does not reconcile the two. Crucially, **the shipped HTMX feature behaves
the same way**: its 509 `calls_api` edges resolve to Route nodes scoped to the **template path**, not to the
Python view Routes — i.e. Spashta's cross-language model is **placeholder-per-emitter, joined BY NAME at
query/enrichment time, not merged into one node**. So `queries_dom` follows the established convention
faithfully (a name-based `StyleClass`/`StyleID` a query can join to the CSS definition). Folding same-`(type,
name)` nodes into one is a **general merger enhancement** (helps HTMX too), out of scope here and best owned
by the maintainers.

**Deferred (Phase 2 remainder):** `fetch`/`hx-*`→`Route` (a JS `calls_api` edge — the same placeholder
pattern; route-name resolution is framework-specific, best with the maintainers); the optional
same-`(type,name)` merger fold; wiring `js_config.json` into `run_tests.py`.

---

## 1. Intent

Add a **JavaScript builder** so Spashta's Code Knowledge Graph spans the *full stack* of an
HTMX/vanilla-JS + Django app — not just Python/HTML/CSS. The value is **cross-language impact analysis**:
"if I rename this JS function / change this event name / move this selector, what breaks?" — the same
`query_spashta.py impact` power that Python already enjoys, extended to the frontend.

This is **additive**: a new `builders/js/build_js_ast.py` + a `builders/js/js_language_mapping.json` (+ an
optional adapter). Per Spashta's own rule — *"new language = one builder; core untouched"* — no existing
builder/adapter/schema behaviour changes.

## 2. Motivation (the gap)

Today the graph stops at the Python↔template boundary. In a full-stack app a large class of coupling lives
in JS and its links to templates and routes, all currently invisible:
- a JS helper (`window.fp.showToast`) called from many files — rename = grep + hope;
- JS that reads a DOM contract (`querySelector('.fp-x')`, `data-dialog-open`) defined in a template;
- `hx-get`/`fetch()` URLs that resolve to Django views (the HTMX adapter already proved this class);
- custom events dispatched in one file and listened for in another (the invisible coupling).

## 3. Design principles (reuse, don't reinvent)

1. **Reuse the existing pipeline verbatim.** The JS builder is a "camera" like the Python one: walk a
   syntax tree, call `BuildContext.register_node` / `emit_edge`, honour the `SchemaEnforcer` over
   `core/software_schema/edges.json`. No new graph runtime.
2. **Determinism is preserved by the seam that already exists.** The builder emits a **deterministic edge**
   ONLY when the target is statically resolvable (a literal). Anything dynamic goes through the existing
   **`BuildContext.emit_ambiguity(kind, expression, reason, scope, confidence="unresolved")`** — exactly
   the mechanism the Python builder uses for unresolved references. So the deterministic-behaviour promise
   is kept *by construction*: guesses never enter the deterministic layer; they become `unresolved`
   ambiguities that **Level-2 LLM enrichment** may later resolve with a confidence tag.
3. **Cross-language edges are the moat**, not intra-JS call graphs. Prioritise JS↔template↔route resolvers.
4. **Opt-in.** The JS builder is gated behind a flag so an in-progress builder never pollutes or slows an
   existing Python-only project graph (e.g. the Forms Portal's daily `spashta_refresh.py`).

## 4. Parser decision — Tree-sitter

**Decision:** parse JS with **Tree-sitter** via `py-tree-sitter` + `tree-sitter-javascript`.

**Rationale (this is the answer to "JS has no stdlib AST like Python"):**
- **No Node.js runtime.** `py-tree-sitter` is a C library with Python bindings — keeps Spashta's toolchain
  pure-Python, exactly as the Python builder uses stdlib `ast`. `pip install tree-sitter tree-sitter-javascript`.
- **Mature + trusted.** Powers GitHub code-nav, Neovim, many linters. MIT-licensed.
- **Error-tolerant.** Parses partial/broken files (real-world JS) instead of throwing — a builder must never
  crash the whole run on one bad file.
- **Generalises.** Grammars exist for TS/JSX/TSX (and HTML/CSS), so the same builder shape extends later;
  Tree-sitter could eventually unify the HTML/CSS builders too.

**Alternatives rejected (for now):** Node-based parsers (Babel / acorn / TypeScript compiler API) give
richer semantics but force a Node environment + subprocess bridge — offer them later only as an optional
"deep-semantic" enrichment, never the default parser.

## 5. MVP — the vertical slice (US-1)

**One question, end-to-end, and nothing else:** *"If I rename `window.fp.showToast`, which files call it?"*

Scope to make ONLY this work:
- Tree-sitter parses JS **function/method definitions + call sites** (ignore classes, DOM, imports, etc.).
- The builder registers `JsFunction` nodes and emits the existing **`calls`** edge (def ← call).
- `query_spashta.py impact "window.fp.showToast" --depth 1` returns the caller list.

**Acceptance (against a real fixture):** run over the Forms Portal `platform/js/helpers.js` (the `window.fp.*`
namespace) + `response_viewer/static/response_viewer/js/viewer.js`; the caller set for a chosen `window.fp.*`
method matches a hand-labelled expected set. Existing Python/HTML/CSS graph **unchanged** (node/edge counts
identical with the JS builder off).

## 6. Phase 2 — cross-language slices (the actual value)

Each its own slice, each deterministic-when-literal / ambiguity-when-dynamic:
- **JS → template:** a literal `querySelector('.fp-x')` / `getElementById('y')` / `data-*` read → the
  template node that defines that class/id/attr (new `queries_dom` edge). Dynamic selector → `emit_ambiguity`.
- **JS/HTMX → route:** a literal `hx-get`/`fetch('/path')` → the Django route/view (reuse the HTMX adapter's
  URL-resolution learnings; new/`references` edge). Templated/variable URL → `emit_ambiguity`.
- **Event contracts:** `dispatchEvent('fpRvClearNormalFilters')` ↔ `addEventListener('fpRvClearNormalFilters')`
  matched across files (reuse/extend the existing `listens_to` edge).

## 7. Proposed schema additions

Node types: `JsFunction`, `EventListener`, `DomQuery` (mapped in `js_language_mapping.json`).
Edge types: reuse `calls` / `references` / `listens_to`; add `queries_dom`, `dispatches_event`, `fetches`
to `core/software_schema/edges.json` with source/target rules the `SchemaEnforcer` validates. Keep additions
minimal — prefer reusing an existing edge over inventing one.

## 8. Determinism contract (the promise, kept)

| Case | Builder action |
|------|----------------|
| Target is a **string literal** (function name, `'/url'`, `'.class'`, `'#id'`, `'event-name'`) | **deterministic edge** via `emit_edge` |
| Target is **dynamic** (variable, template string, computed selector, delegated dispatch) | **`emit_ambiguity(confidence="unresolved")`** — never a guessed edge |
| Ambiguity later resolved | **Level-2 LLM enrichment** attaches a resolved edge **with a confidence tag** |

The deterministic builder is reproducible: same input → same graph, always. Uncertainty is *labelled and
tiered*, never silently mixed into the deterministic layer.

## 9. Failsafe

- Baseline **git tag `pre-js-support`** (done) — revert point if anything regresses.
- **Additive only:** new files under `builders/js/` + minimal `edges.json` additions; existing builders
  untouched. Verify by rebuilding an existing project graph with the JS builder OFF and diffing node/edge
  counts (must be identical).
- **Opt-in flag** so production project refreshes stay unaffected until JS support is proven.

## 10. Fixture / ground truth

The Forms Portal frontend is offered as the labelled corpus (as HTMX was): `platform/js/helpers.js`
(`window.fp.*`), `viewer.js`/`report.js`, the documented `data-*` / `hx-*` contracts, and
`INTERACTION_PATTERNS.md`. We can supply an expected-edge set per slice for validation.

## 11. Out of scope (deferred)

Full JS grammar coverage; frameworks with heavy runtime magic (React/Vue/Angular); TypeScript type-level
edges; bundler/module-resolution (webpack/vite aliases); minified vendor bundles (`htmx.min.js` is a leaf —
don't parse it); source maps. Tackle only after the deterministic literal-resolvable core is proven.
