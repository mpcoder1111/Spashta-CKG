# Spashta-CKG — Builder Script Philosophy (Contributor Reference)

> **Audience**: Builder authors, core contributors, reviewers, test writers
>
> **Purpose**: This document is the **authoritative reference** for how *builder scripts* (`build_*.py`) must be written, reviewed, and tested in Spashta-CKG.

This philosophy applies to all language builders:
- ✅ Python (implemented)
- ✅ HTML (implemented)
- ✅ CSS (implemented)
- 🔜 JavaScript, Go, Java, etc. (future)

---

## 1. Mental Model (Read This First)

A **Builder** is a **strict observer**, not a creator.

- It does **not invent structure**.
- It does **not guess intent**.
- It does **not repair missing facts**.

👉 **Builders observe and record truth. They never improve code.**

Mappings describe *what syntax means*. Builders decide *whether that meaning can be proven*.

---

## 2. Builder's Core Mission

A builder has exactly one responsibility:

> **Convert provable source-code facts into Core-schema-compliant graph structure — and record everything else as explicit ambiguity.**

This mission has **non-negotiable properties**:

- Builders must be **deterministic**
- Builders must be **schema-governed**
- Builders must be **strict, never helpful**

Anything outside this mission is a violation.

---

## 3. Determinism Is a First-Class Requirement

> **Given identical inputs, a builder must always produce identical outputs.**

This includes:
- Node IDs
- Edge ordering (or stable sorting)
- Ambiguity content

Builders must not depend on:
- File traversal order
- Runtime timing
- Environment-specific behavior

Non-determinism is a **builder bug**, not an acceptable limitation.

---

## 4. What a Builder IS Allowed to Do (MANDATORY)

Builders **must**:

1. **Load authoritative inputs**
   - `language_mapping.json` (per language)
   - Core schema (`core/software_schema/nodes.json`, `core/software_schema/edges.json`)
   - Builder rules JSON

2. **Verify proof**
   - Node existence
   - Edge legality
   - Source–target compatibility

3. **Enforce strict rules**
   - No speculative nodes
   - No speculative edges
   - No schema violations

4. **Emit ambiguities**
   - When proof is missing
   - When structure cannot be asserted safely

5. **Be deterministic**
   - Same input → same output
   - Order-independent scanning

---

## 5. What a Builder MUST NOT Do (FORBIDDEN)

Builders must **never**:

- Guess runtime behavior
- Infer framework semantics (that's the adapter's job)
- Fabricate nodes to satisfy mappings
- Repair invalid code
- Collapse ambiguity into structure

### ❌ Forbidden Examples

```python
# WRONG: speculative node creation
emit_node("Function", name)  # just to allow a calls edge
```

```python
# WRONG: silent failure
try_emit_edge()
except:
    pass
```

```python
# WRONG: framework assumption (belongs in adapter, not builder)
if function_name.startswith("get_"):
    emit_node("View")
```

---

## 6. Separation of Artifacts (Non-Negotiable)

| Artifact | File Type | Role |
|----------|-----------|------|
| Language Mapping | JSON | Declares *what syntax means* |
| Builder Script | Python | Enforces *proof & schema* |
| Framework Mapping | JSON | Declares *semantic roles* (adapters) |
| Tests | Python | Verifies *contract compliance* |

> **If logic feels procedural, it belongs in a builder — never in JSON.**

---

## 7. Builder Enforcement Laws (Universal)

### Law 1: Never Emit a Node to Satisfy an Edge

> **Structure must be discovered, not invented.**

If an edge requires a node that cannot be proven to exist, the builder must:
- ❌ NOT emit the edge
- ❌ NOT fabricate the node
- ✅ Emit an explicit ambiguity

This rule applies across all languages and all builders.

---

### Law 2: Core Schema Is the Runtime Authority

> **The Core Schema overrides mappings, builder code, and developer intent.**

Builders must validate **every edge** against Core schema:

- Edge type exists in `edges.json`
- Source node type is allowed
- Target node type is allowed

If any check fails:
- ❌ Do NOT emit the edge
- ✅ Emit a `schema_violation` ambiguity

Schema violations are never data problems — they are **builder bugs**.

---

### Law 3: Builders Do Not Invent Semantics

Builders may only assert **structural existence**, never meaning.

Forbidden examples:
- CSS `@media` → breakpoint node ❌
- JS `fetch()` → API success ❌
- Python decorator → runtime behavior ❌

Semantic meaning is added by **adapters**, not builders.

---

### Law 4: Silence Is Forbidden

> **If structure cannot be asserted, ambiguity must be emitted.**

Builders must never:
- Fail silently
- Skip unsupported constructs
- Hide uncertainty

Ambiguity is not an error path — it is a **required output path**.

---

## 8. Builder Examples by Language

### 🐍 Python Builder

**Scenario**: `import x`

- If module `x` is found → emit `imports` edge
- If not found → emit `import_symbol_unknown` ambiguity

Never:
- Create fake Module node
- Skip silently

---

### 🌐 HTML Builder

**Scenario**: `<img src="{{ dynamic }}">`

- Static path → emit `links_static_asset` edge
- Dynamic value → emit `dynamic_value_unresolved` ambiguity

Never:
- Assume runtime resolution

---

### 🎨 CSS Builder

**Scenario**: `@import 'a.css'`

- If stylesheet exists → emit `imports` edge
- Else → emit `import_target_unresolved` ambiguity

Never:
- Create Stylesheet node for missing file

---

## 9. Ambiguities Are First-Class Citizens

Ambiguities are **not errors**.

They represent:
- Missing proof
- Intentional strictness
- Deferred resolution (for L2 enrichment)

Builders must:
- Emit them explicitly
- Never hide them
- Never downgrade them silently

> **Ambiguity is honesty. Silence is failure.**

---

## 10. Builder + Tests = Contract

A builder is considered **correct** if and only if:

> For every mapping declaration, the builder produces either:
> - the declared structural fact, **or**
> - the documented explicit ambiguity

This is called **Contract Expectation Compliance**.

Tests must validate this contract — **not specific node counts or edge counts**.

A missing edge without a corresponding ambiguity is a **builder failure**.

---

## 11. Contributor Checklist (Before Modifying a Builder)

1. ❓ Am I enforcing proof, or inventing meaning?
2. ❓ Could this logic belong in mapping instead? (If yes → rethink)
3. ❓ Am I hiding uncertainty?
4. ❓ Am I respecting Core schema at every edge?

**If unsure → emit ambiguity, not structure.**

---

## 12. The Golden Rule (Memorize This)

> **Builders do not guess. Builders do not assume. Builders only assert what they can prove.**

---

## 13. Structural Violations = Builder Bugs

Any of the following are considered **builder bugs**:

- Emitting a node not defined in Core schema
- Emitting an edge not allowed by Core schema
- Fabricating nodes to satisfy edges
- Suppressing ambiguity when proof is missing

These are not acceptable trade-offs or limitations.

---

## Summary

- ✅ Language-agnostic philosophy
- ✅ Applies to all current and future builders
- ✅ Violations are architectural bugs
- ✅ Ambiguity is required output, not error handling

---

*In Spashta-CKG, builders are strict by design. Silence is failure. Ambiguity is honesty.*

*Last Updated: 2025-12-30*
