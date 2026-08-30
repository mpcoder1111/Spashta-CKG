# Spec — Dead-code query accuracy for Spashta-CKG (2.1)

**Status:** COMPLETE — 4 phases DONE + merged to master · **Type:** Contribution spec (accuracy — fewer false positives in the
`dead-css` family) · **Baseline:** git tag `pre-dead-code-accuracy` · **Author:** Forms Portal team (hit this
directly while running the #60 dead-CSS cleanup — ~35% of `dead-css` candidates were false positives).

## The generic principle

**An unresolved reference is not a non-reference.** A "dead" query answers "defined, with ZERO inbound use
edges" — but three things make a *used* symbol look unused, and a precise dead-query must account for all
three (the same shape applies to dead-css, dead routes, dead templates, unused anything):

1. **Interleaved-with-dynamic** — a literal reference sits between template tags
   (`class="a {% if x %}b{% endif %}"`), so it was dropped as "dynamic" even though `a` and `b` are literal.
2. **Framework/runtime-injected** — a symbol added at runtime by a framework (HTMX's `htmx-request`), never in
   source, will *always* look dead.
3. **Reference in an un-parsed region** — a use inside a region the builder doesn't parse (a `<script>` block
   embedded in a template — the JS builder scans `.js` *files* only).

The current state (measured on the Forms Portal #60 cleanup): 9 of 26 `dead-css` candidates were false
positives — ① 7, ② 1, ③ 1. Each category has a targeted fix; none is a guess.

## Phases

### P1 — Tag-stripping class tokenizer *(fixes ①, the majority — a builder refinement)*
Today `_emit_class_usage` (css-coverage P1) tokenizes only the **literal prefix up to the first template tag**,
so `class="fp-label {% if active %}fp-label--on{% endif %}"` captured `fp-label` but dropped `fp-label--on`
(→ it read as dead). **Fix:** strip each `{% … %}`/`{{ … }}` tag (replace with a space — a token boundary),
then tokenize the remaining literal text. The tag *contents* (`if`/`active`/`endif`) are removed with the tag,
so no bogus class leaks; the literal class *between* tags (`fp-label--on`) becomes a real `uses_style` edge. A
token split by a variable (`fp-{{ v }}` → `fp-`) is rejected (a dangling leading/trailing `-`), staying a
dynamic ambiguity. Deterministic; strictly *more* complete than the prefix rule.

**P1 as-built (DONE):** `_emit_class_usage` (`build_html_ast.py`) now `re.sub`-strips `{% … %}`/`{{ … }}` → a
space, then tokenizes; a token is emitted only if it fully matches `[A-Za-z_]([\w-]*[A-Za-z0-9_])?` (rejecting
a dangling-hyphen partial from a variable split). The dynamic ambiguity is still recorded when the attribute
carried any tag (so P2 can see the residue). Fixture updated + `verify_class_usage.py` (**7/7** — incl.
`fp-label--on` now captured + `fp-{{icon}}→'fp-'` rejected); template/oob/compound/animation verifiers green.

**P2 as-built (DONE):** `query_spashta dead-css` now partitions unused classes into **`dead_classes`**
(provably unused), **`dynamically_referenced`** (name appears in a `dynamic_class_unresolved` ambiguity), and
**`framework`** (matches `_FRAMEWORK_CLASS_PREFIXES`, default `htmx-`). Query-only (no rebuild).

**P1+P2 proof on Forms Portal:** `dead-css` classes **191 → 142** (P1 turned ~49 conditional classes into real
`uses_style` edges). Of the 9 false positives found by hand in the #60 cleanup, **8 are now auto-resolved**: the
7 `{% if %}` classes report **used** (dropped from dead), `htmx-request` → **framework**. The 9th
(`dc-check--disabled`, toggled in an inline `<script>`) correctly stays in `dead` — that's P3. *(fixes ②, and ①'s residue — query-only)*
`query_spashta dead-css` gains: (a) a **framework allowlist** (default `htmx-*`, extensible) — an allowlisted
class is reported under `framework`, not `dead`; (b) **ambiguity-awareness** — a "dead" class whose name still
appears in a `dynamic_class_unresolved` ambiguity (the P1 residue: `fp-{{ v }}`-style) is reported under
`dynamic`, not `dead`. So the output partitions into **dead** (provably) / **dynamic** / **framework** — the
`dead` list becomes high-precision. No rebuild (pure query).

### P3 — Inline-`<script>` class usage *(fixes ③ — an HTML-builder addition)*
The HTML builder extracts `<script>` block text and scans it for `classList.add/remove/toggle('x')` and
`querySelector('.x')`/`getElementById('y')` **string literals** → `uses_style`/`queries_dom` (StyleClass/
StyleID by name), closing the "JS in a template, not a `.js` file" blind spot. Literal-only (a variable
selector stays unmodeled); config-gated.

**P3 as-built (DONE — merged to master):** additive (reuses `uses_style`; no schema change). A `script_class_usage`
config (`classlist_methods`, `query_methods`) + a `_emit_inline_script_usage(ctx, scanned)` pass in
`build_html_ast.py` (a sibling of the P1 template-relations pass) — regex-scans each template's `<script>…</script>`
blocks for `.classList.add/remove/toggle('x')` (a bare class, incl. a two-arg `toggle`) and
`querySelector('.x')`/`querySelectorAll('.x')` (a SIMPLE `.class` — the closing quote right after the name, so a
compound `.a > .b` doesn't match) → `uses_style` (Template → StyleClass). A variable selector isn't literal →
unmodeled. Fixture `builders/tests/data/scriptcls/` + `verify_script_class_usage.py` (**5/5**). **Proof:**
`dc-check--disabled` (toggled in `dataset_worklist.html`'s inline script) drops out of `dead` — the last of the
9 hand-found false positives, now auto-resolved.

### P4 — variable-modifier awareness *(a 4th category, found running the #60 cleanup — query-only)*
A BEM modifier filled by a variable — `class="x x--{{ status }}"` — never emits the literal `x--archived`, so
`x--archived`/`x--draft`/… look dead even though they're applied at runtime. **Fix:** in `dead-css`, a dead
`x--suffix` whose base appears as `x--{{`/`x--{%` in a `dynamic_class_unresolved` ambiguity → classified
`dynamically_referenced`, not `dead`. Query-only; **safe-directional** (only ever moves a class *out* of
`dead` — it can keep a genuinely-removed variant, never delete a used one). **Proof on Forms Portal:** the
`fp-status-badge--{{ form.status }}` and `fp-quality-band--{{ grade }}` families reclassify correctly, and
`dead-css` **121 → 58** (63 BEM variable-modifier variants portal-wide reclaimed from false-dead).

## Result (4 phases, Forms Portal)

The 9 false positives found by hand in the #60 dead-CSS cleanup are **100% auto-classified** now:
**P1** the 7 `{% if %}` classes → real `uses_style` edges (`used`); **P2** `htmx-request` → `framework`;
**P3** `dc-check--disabled` (inline `<script>`) → `used`. `dead-css` classes went **208 (raw) → 140 (precise)**,
and the output partitions into `dead` / `dynamically_referenced` / `framework`. The `dead` list stays a
CANDIDATE list (a class built entirely in Python still can't be seen) — but the systematic false-positive
categories are gone, so the remaining #60 cleanup batches are a quick scan, not a slog.

## Determinism contract

| Case | Action |
|------|--------|
| a literal class between template tags | `uses_style` (P1) |
| a class split by a variable (`fp-{{ v }}`) | a `dynamic_class_unresolved` ambiguity → reported `dynamic` (P2), never a guessed edge |
| a framework-injected class (`htmx-*`) | reported `framework` (P2), never `dead` |
| a literal `classList/querySelector('.x')` in an inline `<script>` | `uses_style`/`queries_dom` (P3) |
| a variable selector in a `<script>` | unmodeled (no guess) |

## Failsafe

Baseline `pre-dead-code-accuracy`; additive (P1 only *adds* edges; P2 only *re-partitions* output; P3 is new,
config-gated). A fixture + `verify_*` per builder phase; rebuild-and-diff (structural edges stable). The `dead`
partition stays a **candidate** list (a class built entirely in Python, or test-only, still needs a human
glance) — the goal is high precision, not omniscience.

## Out of scope

Full JS parsing of `<script>` blocks (only the literal DOM-selector calls); `style=""` inline styles; the
cascade. Framework allowlists beyond a small default + project extension.
