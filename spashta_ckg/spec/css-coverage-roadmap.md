# Spec — CSS coverage roadmap for Spashta-CKG (2.1)

**Status:** COMPLETE — all 3 phases DONE + merged to master · **Type:** Contribution spec (3 phases; each
additive, config/pattern-driven, deterministic-when-literal) · **Baseline:** git tag `pre-css-coverage`
(created) · **Author:** Forms Portal team (a Django + HTMX + vanilla-JS + hand-written-CSS app — Spashta's
exact target quadrant; hit the CSS gap directly while grounding a frontend-library refactor).

## Intent

Model the **structural** CSS layer so Spashta can answer "who uses this class?", "is this class/animation dead?",
and "is this defined/duplicated in more than one place?" — the questions a frontend refactor needs *before*
editing. Explicitly NOT the cascade (specificity / computed final style is runtime and out of scope, and no
static tool does it). Each phase follows the proven shape: **detect a literal → emit a node + a by-name edge; a
non-literal → an ambiguity, never a guess; additive + config-gated; node-join by name (js-support §0d).**

## Current state (grounded on the Forms Portal graph, 2026-08-02)

- **Definition side EXISTS.** The CSS builder (`build_css_ast.py`, regex_v1) emits `StyleClass` (2229),
  `StyleID` (329), `StyleElement` (770), `Stylesheet` (10), each with a **`defines`** edge from its stylesheet
  (**13432** total). "Which file defines `.x`?" already resolves. Duplicate definitions already fall out: **48**
  StyleClass names are defined in >1 stylesheet today.
- **Script side EXISTS.** `queries_dom` (163) joins JS `querySelector`/`querySelectorAll`/`getElementById` →
  StyleClass/StyleID by name (single literal `.class`/`#id` only; else an `unresolved_selector` ambiguity).
- **GAP 1 — markup usage is UNMODELED.** `uses_style = 0`. The HTML builder extracts the `class` attribute into
  context but emits no edge, so no template↔class link exists. → "who uses `.x`?" and "dead class?" are
  unanswerable despite 2229 classes.
- **GAP 2 — animations are UNMODELED.** The CSS builder emits an ambiguity literally labelled *"Animations
  unmodeled"* for every `@keyframes`; `animation:` references are ignored. → duplicate/dead keyframes invisible
  (the exact case a spinner-consolidation refactor hit).
- **Noise to clean up in passing:** `@keyframes { to {} from {} }` blocks currently leak `to`/`from` into
  `StyleElement` via the element-selector regex; proper keyframe modeling (P2) removes that.

## The generic model — CSS is a cross-language hub joined BY NAME

One `StyleClass` node, three producer edges — framework-agnostic (HTML `class`, Django/Jinja `class`, React
`className`, Vue `:class` all reduce to the same literal class tokens):

| Edge | Producer | Status |
|------|----------|--------|
| `defines` | CSS file `.x { }` | ✅ exists |
| `uses_style` | markup `class="x"` | ❌ **P1** |
| `queries_dom` | script `querySelector('.x')` / `classList.add('x')` | ✅ (query only; `classList` = **P3**) |

Every insight query (dead class, usage, duplicate) is a graph question over these three by-name edges.

## Phases (each independently shippable — fixture + verifier + baseline; rebuild-and-prove on the portal)

### P1 — `uses_style` (markup `class=""` → StyleClass)  *(the #1 gap, highest impact)*
The HTML builder tokenizes each `class="a b c"` attribute into per-token **`uses_style`** edges
(Template/Fragment → StyleClass), literal tokens only; a token containing `{{`/`{%` (e.g. `fp-{{ x }}`) is
skipped as a dynamic ambiguity. New edge `uses_style` (`Template/Fragment → StyleClass`). Config-gated
(a `class_usage` rule in the HTML mapping). **Unlocks:** *"which templates use `.fp-bulk-busy-btn`?"* (+ the JS
`queries_dom` users), and **dead-class** = a StyleClass with `defines` but no `uses_style`/`queries_dom` inbound.
Completes the CSS triangle.

**P1 as-built (DONE — merged to master):** additive + config-gated. New edge `uses_style` (`Template/Fragment
→ StyleClass`) in `edges.json`; a `class_usage` config in `html_language_mapping.json`; `StructureWalker`
gained `_emit_class_usage` (called from `handle_starttag`) + the edge registered in `_collect_allowed_edges`.
**Deterministic rule:** only the literal PREFIX up to the first template expression is tokenized — a Django
attr `class="static-a static-b {% if x %}cond{% endif %}"` resolves `static-a`/`static-b` and emits ONE
`dynamic_class_unresolved` ambiguity for the `{% … %}` remainder, so template keywords (`if`/`endif`) never
become bogus classes and a `class="fp-{{ v }}"` token never guesses. The StyleClass placeholder joins by name
to the CSS `defines` + JS `queries_dom` (js-support §0d). Fixture `builders/tests/data/cssuse/` +
`verify_class_usage.py` (**6/6 PASS**; the template + oob verifiers still green). **Proof on Forms Portal:**
**3964** `uses_style` edges; structural + P1/P5 edges unchanged. **Unlocked (both hand-grepped before):**
*dead-CSS* = 237 of 2126 classes have `defines` but no `uses_style`/`queries_dom` (candidates — some are
JS-toggled via `classList`, refined in P3); *class usage* = `.fp-bulk-busy-btn` → `_bulk_review_table.html` +
`bulk_landing.html`.

### P2 — `@keyframes` / animation modeling
Replace the *"Animations unmodeled"* ambiguity with a real **`Keyframes`** (a.k.a. Animation) node +
**`defines`** (Stylesheet → Keyframes); a rule with `animation:`/`animation-name: X` → **`uses_animation`**
(StyleClass/Stylesheet → Keyframes), the name joined by name. Optionally carry a normalized body-hash attribute
so *identical* keyframes are detectable by a query (the 119 case: 6 byte-identical rotations). Also stops the
`to`/`from` StyleElement leak. New node `Keyframes` + edge `uses_animation`. **Unlocks:** duplicate/dead
animations; *"what animates with `platform-spin`?"*.

**P2 as-built (DONE — merged to master):** additive + config-gated. New node `Keyframes` (nodes.json, carries a
normalized `body_hash`) + new edge `uses_animation` (`Stylesheet/StyleClass → Keyframes`) in edges.json;
`defines.to` extended with `Keyframes`; an `animations` config in `css_language_mapping.json`. The CSS builder's
legacy *"Animations unmodeled"* ambiguity is replaced (when `animations` is configured) by `_model_animations`:
brace-balanced extraction of each `@keyframes NAME { … }` → a `Keyframes` node + `body_hash` (whitespace-
normalized) + `defines` edge; then the `@keyframes` blocks are **blanked** (newlines kept) so their `to`/`from`/
percent stops no longer leak into `StyleElement`; then each `animation:`/`animation-name:` value →
`uses_animation` per identifier token (a duration `0.6s` fails the identifier fullmatch; a timing keyword like
`linear`/`infinite` is a stopword → filtered). Config-gated, off = the old ambiguity (byte-identical). Fixture
`builders/tests/data/cssanim/` + `verify_animations.py` (**7/7 PASS** — incl. the identical-`body_hash` dup, the
dead-animation, and the no-`to`/`from`-leak cases). **Proof on Forms Portal:** 10 `Keyframes` + 10
`uses_animation`; `StyleElement` 770→761 (leak cleaned); structural + P1 edges unchanged. The portal shows **0
dead + 0 identical-duplicate** keyframes — the correct post-119 state (the 6 identical spins already
consolidated to `platform-spin`), and the fixture proves the capability flags both when present.

### P3 — query commands + `classList` usage
- `query_spashta` insight commands over the new edges: **`dead-css`** (StyleClass/Keyframes defined, zero
  `uses_style` + `queries_dom` + `uses_animation`), **`class-usage <name>`** (all users across templates + JS),
  **`dup-styles`** (a StyleClass with >1 definer / a Keyframes with an identical-body twin).
- Extend JS `queries_dom` to `classList.add/remove/toggle('x')` and `el.className = 'x'` (literal only) so a
  JS-toggled class is a real usage → cuts dead-css false positives.

**P3 as-built (DONE — merged to master):** additive; no schema change (reuses the P1/P2 edges). **Query
commands** in `query_spashta.py` over a shared `_css_index` (defines / uses_style+queries_dom / uses_animation
grouped by style-node NAME): **`dead-css`** (`--kind class|keyframes|all`), **`class-usage <name>`**,
**`dup-styles`** — each prints a "CANDIDATES, confirm before deleting" note (a class may be dynamic/JS-toggled;
a >1-file class may be an intentional override). **JS `classList`:** `build_js_ast.py` gained
`_DOM_CLASSLIST_METHODS` + `_is_classlist_callee` (the generic `add`/`remove`/`toggle` names count only when
the callee is `<obj>.classList.<method>`) → `queries_dom` StyleClass; a `Set.add('x')` is correctly ignored;
`className = 'x'` deferred (assignment, multi-class — a follow-up). Fixture `classlist_dummy.js` +
`verify_classlist.py` (needs tree-sitter; skips cleanly without it). **Proof on Forms Portal:** the three
commands work — `class-usage fp-bulk-busy-btn` → `respondent.css` (defines) + `bulk_landing.html` +
`_bulk_review_table.html` (used_by); `dead-css` = 206 classes; `dup-styles` = 48 (e.g. `badge` in
`option_lists.css` + `user_auth.css`). The classList change raised `queries_dom` **163 → 213** and dropped
dead-css **237 → 206** — 31 JS-toggled classes correctly reclassified as used (the accuracy refinement,
demonstrated). Structural + P1/P2 edges unchanged.

## Status: ALL THREE PHASES DONE + merged to master

| Phase | Adds | Portal proof | Unlocks |
|-------|------|--------------|---------|
| P1 | `uses_style` (markup→class) | 3964 edges | class usage · dead-class |
| P2 | `Keyframes` + `uses_animation` (+body_hash) | 10 + 10; leak 770→761 | dead/duplicate animations |
| P3 | `dead-css`/`class-usage`/`dup-styles` cmds + JS `classList` | queries_dom 163→213; dead-css 237→206 | the day-to-day queries |

The CSS triangle (define / use / query) is complete; cascade/computed-styles remain out of scope by design.

**P4 follow-up fix (DONE — merged to master):** using the P1–P3 data surfaced a pre-existing gap in the CSS
builder's `class_selector` regex — its lookahead `(?=[\s,{:])` **missed the first class of a compound selector**
(`.btn-busy.htmx-request` never captured `.btn-busy`, so it read as "undefined-but-applied"). Broadened the
lookahead to also accept `.` `>` `+` `~` `[` (compound / child / sibling / attribute); the name still requires a
letter/`_`/`-` start so a numeric value (`1.5em`) never matches. Fixture `builders/tests/data/cssdef/` +
`verify_compound_selector.py` (**6/6 PASS**; the animation verifier still green). **Proof:** `.btn-busy` now
resolves as defined; distinct DEFINED classes 2126→2131 (+5 real compound-first classes — bounded, no
false-positive flood); the undefined-but-applied signal dropped its 5 compound false positives.

## Determinism contract (all phases)

| Case | Action |
|------|--------|
| literal class / animation name (`class="x"`, `animation: x`, `classList.add('x')`) | deterministic edge to the by-name StyleClass/Keyframes node |
| dynamic (`class="fp-{{ v }}"`, a variable, a computed name) | `emit_ambiguity(…)`, never a guessed edge |

## Failsafe (all phases)

Baseline tag `pre-css-coverage`; additive only (new edges/nodes in the schema + new config; existing builders/
edges/other languages untouched); config-gated (empty config → feature off, graph identical); a fixture +
`verify_*` runnable proof per phase; rebuild-and-diff on the portal (structural edges `defines`/`imports`/
`contains_member` stable). "Defined in >1 place" and "no usage" are **candidate** lists for human judgment
(a media-query override / a JS-toggled class), not automatic defects — the tool narrows, it doesn't decide.

## Out of scope (by design, not a limitation to fix)

The **cascade** — specificity, which rule's property wins, the computed final value — is runtime/semantic and
unmodelable statically (and unneeded for grounding a refactor). Preprocessor (SCSS/Less) source, CSS-in-JS
runtime styles, `@media`/`@supports` condition semantics, inline `style=""` values. Structure only.
