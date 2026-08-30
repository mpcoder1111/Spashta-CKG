# Spec — Named-callback-reference call resolution for Spashta-CKG (2.1)

**Status:** DONE — merged to Spashta `master` · **Type:** Contribution spec (JS `calls` accuracy — a single
targeted fix) · **Baseline:** git tag `pre-js-callback-refs` · **Author:** Forms Portal team (found running a
JS dead-code audit — every "0 inbound calls" candidate turned out to be a false positive of this exact shape).

## Problem (grounded)

`addEventListener('evt', handler)` only had its FIRST argument (the event name) inspected by the JS builder;
the SECOND argument (the handler) was ignored entirely. When the handler is passed **by reference**
(`addEventListener('click', init)` — a bare identifier or a dotted name, not an inline `function(){}`), that
IS a real call relationship: the enclosing scope hands the browser a function it later invokes. Without
resolving it, `init` has zero inbound `calls` edges and looks dead — purely because it's never written as
`init()`. On the Forms Portal, this was the root cause of **15 of 15** false "dead function" candidates
surfaced during a JS audit (`init`, `_fpPickerEls`, `schedule`, …).

## The fix (additive, deterministic-when-literal)

`_handle_event` (`build_js_ast.py`), for a `listen` call, now also inspects the SECOND argument. If it is a
literal `identifier` or `member_expression` (a named reference — never an inline `function()`/arrow, which
has nothing to resolve), it is resolved **the exact same way** a direct `name(...)` call already is: the
resolve-and-emit logic was extracted from `_handle_call`'s tail into a shared `_resolve_and_emit_call(name,
scope_id, line)`, reused by both call sites. A single match → a deterministic `calls` edge; zero or multiple
matches → the same `unresolved_call` ambiguity a direct call would produce — **never a guessed edge**. No new
node or edge type (reuses `calls`); the existing `registers_event_handler` edge is untouched (still emitted
for every `addEventListener`, named or anonymous handler alike).

## Determinism contract

| Handler argument | Action |
|---|---|
| a bare identifier (`init`) or dotted name (`fp.showToast`) | resolved via the SAME registry/fallback `_handle_call` uses → a deterministic `calls` edge |
| an inline `function(){}` / arrow function | unchanged — nothing to resolve, no new edge, no ambiguity |
| an unresolved / ambiguous (multi-match) name | `unresolved_call` ambiguity, never a guess |

## Proof

Fixture `builders/tests/data/callback_ref_dummy.js` + `verify_callback_refs.py` (**6/6 PASS**): a bare-id
handler ref, a dotted/trailing-property-fallback ref, an inline handler (unaffected), an unresolved name
(ambiguity, not a guess), and `registers_event_handler` staying unchanged. `verify_classlist.py` (the prior JS
contribution) stays green — no regression.

**Proof on Forms Portal:** all 15 of the false "dead function" candidates found in the JS audit now resolve
to a real inbound `calls` edge (from the scope that registers them as a listener) — see the ledger note in
CLAUDE.md for the exact before/after count.

## Failsafe

Baseline `pre-js-callback-refs`; purely additive (one new call site into the existing `_resolve_and_emit_call`
path; no schema/config change — the fix is structural code, not a toggle, matching how `_is_classlist_callee`
was added without a config flag). Existing call/event edges for every other pattern are byte-identical.

## Out of scope

Resolving an INLINE anonymous handler as a "used" function (there's no separate Function node for it to
attribute the edge to — by design, matching the rest of the JS builder's node model); a handler passed via
`.bind()`/a computed expression (dynamic, correctly stays unmodeled); non-`addEventListener` callback-taking
APIs (`setTimeout(fn, …)`, `.forEach(fn)`, promise `.then(fn)`) — a natural, larger follow-up if ever needed,
deliberately not bundled here to keep this a single, focused, provable fix.
