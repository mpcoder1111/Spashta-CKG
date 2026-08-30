# Spec — Full-stack coupling roadmap for Spashta-CKG (2.1)

**Status:** COMPLETE — all 5 phases DONE + merged to master · **Type:** Contribution spec (5 phases; each additive, config/pattern-
driven, deterministic-when-literal) · **Baseline:** git tag `pre-fullstack-roadmap` (created) · **Author:**
Forms Portal team (a Django + HTMX + vanilla-JS app — Spashta's exact target quadrant)

## Intent

Complete the remaining Django/HTMX/Python couplings so Spashta models the WHOLE request + presentation graph,
not just the seams shipped in the prior specs (js-support · htmx-event-coupling · frontend-route-coupling ·
django-htmx-coupling). Each phase follows the proven shape: **detect a structural pattern → extract a LITERAL
→ match/emit a node + edge; a non-literal → an ambiguity, never a guess; additive + config-gated; node-join by
name/logical-path (js-support §0d).**

## Phases (each independently shippable, with a fixture + verifier + baseline)

### P1 — Template inheritance & includes  *(the #1 gap for a template-driven app)*
`{% extends "base.html" %}` → **`extends_template`** (Template→Template); `{% include "partial.html" %}` →
**`includes_template`** (Template→Template). Answers *"if I change `base.html` / a partial, which templates
break?"* — unanswerable today, and we use base templates + partials heavily. HTML-builder **second pass**
(all Template nodes registered first), match the target by its logical `/templates/`-relative name (the
`query_spashta` Template join already unites logical↔physical). Config `template_relations` (tag → edge).

**P1 as-built (DONE — merged to master `48f11be`):** additive + config-gated. Added `extends_template` +
`includes_template` to `edges.json` (both `Template/Fragment → Template/Fragment`); `template_relations`
config in `html_language_mapping.json` (tag → edge); `build_html_ast.py` gained a **second pass**
(`_emit_template_relations`) that runs after all Template nodes are registered, extracts the literal path from
`{% extends %}`/`{% include %}`, and matches the target Template by its `/templates/`-relative logical name
(`re.split(r"(?:^|/)templates/", s)[-1]`); a dynamic/`{{…}}` path → `unresolved_template_ref` ambiguity, never
a guess. `query_spashta._template_logical` uses the same split so a logical placeholder and the physical
Template unite. Fixture `builders/tests/data/tpl/` + `verify_template_relations.py` (**2/2 PASS**, copies to a
tempdir outside Spashta-CKG since the scanner excludes its own tree). **Proof on Forms Portal:** 65
`extends_template` + 368 `includes_template` edges; `impact` on `_scope_rows.html` lists the three templates
that include it; `defines`/`imports`/`contains_member` unchanged.

### P2 — `include()` URL-namespace tree
Root `urls.py` `path('admin/', include('portal_core.urls'), namespace=…)` → model the include hierarchy so a
route's fully-qualified namespace is correct even across included URLconfs (today namespaces come from a
module `app_name`). A Python-builder addition reusing the route-registration config; deterministic on a
literal module path, ambiguity on a dynamic include.

**P2 as-built (DONE — merged to master):** additive + config-gated. Added `includes_urlconf` (`File → File`)
to `edges.json`; `include_registrations` config in `python_language_mapping.json` (`call_names:["include"]`,
`module_arg_index`, `namespace_kwarg`, `edge`); `RelationWalker._resolve_includes(module_node)` — walked at
pass-2 module level beside `_resolve_routes` (because `include()`/`path()` live in the `urlpatterns = [...]`
RHS which `visit_Assign` does not recurse into — the reason a `visit_Call` hook, tried first, saw nothing).
A literal `include('module.path')` resolves the sub-URLconf File via `_find_module_id` (the import resolver)
and emits the edge; a literal `namespace=` rides as edge metadata; a non-literal module arg (a variable or an
inline `include([...])` list) → an `unresolved_include` ambiguity, never a guess. Fixture
`builders/tests/data/urlinc/` + `verify_include_tree.py` (**4/4 PASS**). **Proof on Forms Portal:** 17
`includes_urlconf` edges (the root urlconf's includes — `urls.py → ai_urls.py`, `→ analytics_urls.py`, …);
`defines`/`imports`/`contains_member` + the P1 edges unchanged. *Deferred remainder:* propagating the include
namespace onto each route's fully-qualified name across the tree — our stack sets `namespace=` equal to each
app's `app_name`, so the same-module derivation already resolves route names correctly (no gap to close for
us); the edge + namespace-metadata is the deterministic literal core, and the propagation builds on it when a
project that overrides namespace needs it.

### P3 — Generic inline `HX-Trigger`
Complete coupling C without a project helper: detect `response['HX-Trigger'] = '<event>'` and
`= json.dumps({'<event>': …})` (event names = the string literal / the dict-literal keys) →
`dispatches_event` (Function→Event). Removes the one project-specific config value (`_append_hx_trigger`) from
the shipped default; a bare-string or literal-dict HX-Trigger resolves for ANY HTMX+Django project.

**P3 as-built (DONE — merged to master):** additive + config-gated; NO new edge (reuses `dispatches_event`).
A new GENERIC config `header_event_dispatch` (a framework fact — the `HX-Trigger*` header NAMES, not a
project helper → shippable by default); `RelationWalker.visit_Assign` gained `_couple_header_dispatch(node)`:
for a `Subscript` target whose key is a configured header, the VALUE decides the events — a bare string
(comma-split) → one `Event` per name; `json.dumps({..})` over a **dict literal** → one `Event` per string-key
(via `_hx_trigger_events`); a computed value (a variable / non-literal dict) → an `unresolved_hx_trigger`
ambiguity, never a guess. The Event node-or-placeholder logic was factored into a shared `_named_target_id`
helper (also now used by `_couple_call`), so the Python-dispatched Event joins the JS listener by name at
merge. The project's `_append_hx_trigger` call-coupling stays (it passes the event as an ARG — a complementary
path the generic body-detection can't recover, since the helper dumps a computed dict). Fixture
`hx_dispatch_dummy.py` + `verify_hx_dispatch.py` (**4/4 PASS**). **Proof on Forms Portal:** the direct
`resp['HX-Trigger'] = 'rvRefresh'` in `response_viewer/views/_common.py` — previously **missed** — is now a
`dispatches_event` from `_rv_refresh`; `fp:share-open`/`fp:reference-open` + the literal-dict events also
resolve; 14 `dispatches_event` edges total; structural + P1/P2 edges unchanged; the prior `verify_django_htmx_coupling`
stays 4/4 (no regression).

### P4 — Django forms & signals
`class X(forms.ModelForm): class Meta: model = Y` → **`references`/`uses_model`** (Form→Model); a
`@receiver(sig, …)` / `signal.connect(handler)` → **`listens_to`** (handler→Signal). Rounds out the Django
model layer; structural detection (a base class / a decorator), like the TestCase/Field policy.

**P4 as-built (DONE — merged to master):** additive + config-gated. NEW edge `uses_model` (`Class → Class`,
distinct from `references`/FK) in `edges.json`; the `@receiver` case reuses the existing `listens_to`
(`Function → Signal`, already in the schema) via a `receives_signal → listens_to` mapping. Two GENERIC configs
in `python_language_mapping.json`: `model_form_binding` (base classes `ModelForm`/`ModelSerializer` + the
`Meta.model` attr) and `signal_receivers` (the `receiver` decorator + signal-arg index). `visit_ClassDef`
gained `_couple_model_form` — a class extending a configured base with a nested `class Meta: model = X` →
`uses_model` to the Model Class resolved by name (`_class_by_name`, heuristic, like the FK resolver); a
non-name `model` attr → `unresolved_model_binding`. `_handle_function` gained `_couple_signal_receiver` — a
`@receiver(SIGNAL, …)` decorator → `listens_to` to a `Signal` node named by the arg (via `_named_target_id`,
joined by name); a non-name signal → `unresolved_signal`. Fixture `forms_signals_dummy.py` +
`verify_forms_signals.py` (**2/2 PASS**). **Honest scope note:** the Forms Portal itself uses **NO ModelForm
and NO Django signals** (HTMX + service functions instead), so P4 is a **GENERIC Spashta contribution proven
at the fixture level only** — there are no portal instances to light up (`uses_model = 0` on the rebuilt
portal graph, structural + P1/P2/P3 edges byte-stable — the proof that a project lacking these patterns is
unaffected). It rounds out the Django model layer for any project that DOES use them.

### P5 — HTMX out-of-band swaps
`hx-swap-oob="true"` on an element with an `id` + `hx-select-oob` → the OOB target coupling, so an
OOB-refreshed fragment (our slicers/tables) is traceable. HTML-builder attribute rule, the `targets_element`
sibling.

**P5 as-built (DONE — merged to master):** additive + config-gated. NEW edge `oob_swaps` (`Template/Fragment
→ StyleID`) in `edges.json` — a distinct sibling of `targets_element` (a request's hx-target). A new
attribute-interaction field `value_from_context` lets a rule target the element's OWN context attribute (its
`id`) rather than the triggering attribute's value: `hx-swap-oob` refreshes the element with the SAME id, so
the coupling target is the **bare id** (`form-messages`), which unifies by name with the CSS StyleID
(`#form-messages{}` → `form-messages`) and JS `getElementById('form-messages')`. A **templated** id
(`id="x-{{ var }}"`) → a `dynamic_value_unresolved` ambiguity, checked **locally on the brace markers** in the
`value_from_context` branch (the shared `dynamic_patterns` are the literal strings `"{{ }}"`/`"{% %}"` = only
empty braces, and broadening that shared check would wrongly ambiguate a `{% url %}` value BEFORE the route
regex extracts its name — so the check stays local). Fixture `builders/tests/data/oob/` + `verify_oob_swaps.py`
(**4/4 PASS**; P1 template verifier no regression). **Proof on Forms Portal:** 28 `oob_swaps` edges;
*"which fragments OOB-refresh `#form-messages`?"* → `_conflict_banner`, `_dedup_banner`, `_mutation_warning`,
`_notification_banner` — previously unanswerable, now traceable ("rename `#form-messages` in the base → these
break"); structural + P1/P2/P3 edges unchanged. *Deferred:* `hx-select-oob` and the `#`-vs-bare hx-target
spelling normalization (a pre-existing separate quirk).

---

## Status: ALL FIVE PHASES DONE + merged to Spashta master

| Phase | Coupling | New edge(s) | Portal proof | Self-benefit |
|-------|----------|-------------|--------------|--------------|
| P1 | `{% extends %}`/`{% include %}` | `extends_template`, `includes_template` | 65 + 368 edges | HIGH (template-driven app) |
| P2 | `include('app.urls')` URL tree | `includes_urlconf` | 17 edges | MED (root urlconf tree) |
| P3 | inline `response['HX-Trigger']` | *(reuses `dispatches_event`)* | `rvRefresh`/`fp:*` now caught | HIGH (direct header writes) |
| P4 | `ModelForm`→Model, `@receiver`→Signal | `uses_model` (+ reuses `listens_to`) | 0 (no instances) — fixture-proven | NONE (we use neither) |
| P5 | `hx-swap-oob` | `oob_swaps` | 28 edges | HIGH (33 OOB templates) |

Every phase: additive · config-gated (empty config → feature off, graph byte-identical) · deterministic-when-
literal (else an ambiguity, never a guess) · a fixture + a runnable `verify_*` proof · structural edges
(`defines`/`imports`/`contains_member`) unchanged on the rebuilt portal · merged to master on its own commit.

## Determinism contract (all phases)

| Case | Action |
|------|--------|
| literal string (path / url-name / event / template) | deterministic edge to an existing node OR a by-name/logical placeholder |
| dynamic (variable, f-string, `{{ … }}`, computed) | `emit_ambiguity(…)`, never a guessed edge |

## Failsafe (all phases)

Baseline tag `pre-fullstack-roadmap`; additive only (new edges in `edges.json` + new config; existing builders/
edges/other languages untouched); config-gated (empty config → feature off, graph identical); a fixture +
`verify_*` runnable proof per phase; rebuild-and-diff (structural edges stable).

## Out of scope

Context-variable flow (view ctx → `{{ var }}` in template); Jinja2-specific tags; DRF routers/viewsets
(a separate framework slice); the same-`(type,name)` node-merger fold (the query by-name/logical join carries
every phase). Tackle only after the literal-resolvable core of each phase is proven.
