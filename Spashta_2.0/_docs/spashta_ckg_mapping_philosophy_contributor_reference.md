# Spashta-CKG — Mapping Philosophy (Contributor Reference)

> **Audience**: Core contributors, builder authors, reviewers, test writers
> 
> **Purpose**: This document is the **authoritative, language-agnostic reference** for how `language_mapping.json` files are designed, interpreted, enforced, and tested in Spashta-CKG.

This document applies to:
- ✅ Python (implemented)
- ✅ HTML (implemented)
- ✅ CSS (implemented)
- 🔜 JavaScript, Go, Java, etc. (future)

---

## 1. Mental Model (Universal)

A **Language Mapping** is a **dictionary of meanings**, not an execution engine.

- A dictionary answers: *"When I see this syntax, what concept does it represent?"*
- A program answers: *"If this fails, what should I do next?"*

👉 **Mappings describe meaning. Builders enforce reality. Tests verify discipline.**

This separation is what keeps Spashta deterministic, auditable, and scalable.

---

## 2. Two Types of Mappings

Spashta has two distinct mapping types:

| Type | Location | Purpose | Used By |
|------|----------|---------|---------|
| **Language Mapping** | `builders/*/language_mapping.json` | Maps syntax → Core nodes/edges | Builders |
| **Framework Mapping** | `adapters/*/framework_mapping.json` | Maps patterns → Semantic roles | Enrichment |

This document focuses on **Language Mappings** (builder layer).
For framework mappings, see `adapter_Readme.md`.

---

## 3. Core Principle: **Positive Facts Only**

All mapping files follow one invariant rule:

> **Mappings may only declare positive structural intent.**

They answer:
- *If this syntactic pattern exists, what Core node or edge does it represent?*

They never answer:
- Whether the fact is valid
- Whether the target exists
- What to do if the fact cannot be proven

---

## 4. What Belongs in a Mapping File (ALLOWED)

### ✅ Declarative Content Only

A mapping file **may contain**:

1. **Syntax Patterns**
   - Regex patterns (CSS)
   - AST selectors (Python)
   - Tag/attribute patterns (HTML)

2. **Positive Assertions**
   - `Pattern → Node`
   - `Pattern → Edge`

3. **Extraction Rules**
   - Name capture groups
   - Attribute keys

4. **Core Vocabulary Only**
   - Node types defined in `core/software_schema/nodes.json`
   - Edge types defined in `core/software_schema/edges.json`

---

## 5. What MUST NOT Be in a Mapping File (FORBIDDEN)

Mappings must **never** include:

- Failure handling
- Fallback logic
- Conditional flows
- Builder decisions
- Ambiguity policies

### ❌ Forbidden Examples

```json
{
  "emit_edge": "imports",
  "fallback": "import_target_unresolved"
}
```

```json
{
  "emit_node": "Function",
  "if_not_found": "skip"
}
```

If you feel tempted to write logic like this → **you are in the wrong layer**.

---

## 6. Separation of Concerns (Explicit & Enforced)

Spashta uses **three explicit layers**, each implemented in **different artifacts**:

| Layer | Artifact Type | Responsibility |
|-------|---------------|----------------|
| **Mapping** | JSON | Declare *what syntax represents* |
| **Builder** | Python Script | Enforce proof, schema, strictness |
| **Tests** | Python Script | Verify builder honored contract |

> **JSON declares. Python code enforces. Tests validate.**

This distinction is intentional and non-negotiable.

---

## 7. Builder Enforcement (Language-Agnostic)

Builders are the **only place** where enforcement logic is allowed.

### Builders are responsible for:
- Verifying node existence
- Verifying edge legality against Core schema
- Preventing speculative node creation
- Emitting ambiguities when proof fails

### Builders must follow this rule:

> **Never emit a node or edge simply to satisfy a mapping declaration.**

Mappings declare *intent*. Builders decide *truth*.

---

## 8. Language Mapping Examples

### 🐍 Python Example

**Mapping says**:
```json
{
  "syntax": "import",
  "emit_edge": "imports"
}
```

**Builder behavior**:
- If imported module exists → emit `imports` edge
- If not → emit `import_module_unknown` ambiguity

**Mapping never changes.**

---

### 🌐 HTML Example

**Mapping says**:
```json
{
  "tag": "img",
  "attribute": "src",
  "emit_edge": "links_static_asset"
}
```

**Builder behavior**:
- If static asset path is local & static → emit edge
- If dynamic or external → emit ambiguity

---

### 🎨 CSS Example

**Mapping says**:
```json
{
  "regex": "@import\\s+['\"](.+?)['\"]",
  "emit_edge": "imports"
}
```

**Builder behavior**:
- If stylesheet exists → emit `imports`
- If not → emit `import_target_unresolved`

---

## 9. Ambiguities: Why They Live Outside Mappings

Ambiguities represent **uncertainty**, not structure.

| Concept | Layer |
|---------|-------|
| Structure | Mapping |
| Proof | Builder |
| Uncertainty | Ambiguity (emitted by Builder) |

Putting ambiguities in mappings would:
- Make mappings procedural
- Blur responsibility boundaries
- Break determinism

Therefore:
- Ambiguity *kinds* are documented in **builder instructions**
- Ambiguity *emission* happens in **builder code**
- Ambiguity *expectation* is verified in **tests**

---

## 10. Testing Philosophy: Contract Expectations

Tests must assert **contract behavior**, not brittle outcomes.

### Correct pattern

> For each mapping rule, the builder must produce:
> - the declared structural edge **OR**
> - the documented strict ambiguity

This pattern is called **Contract Expectation Testing**.

It applies equally to:
- Python imports
- CSS imports
- HTML asset links

---

## 11. Contributor Checklist (Before Modifying a Mapping)

1. ❓ Is this a **positive structural fact**?
2. ❓ Does this rely only on **syntax**, not runtime behavior?
3. ❓ Am I trying to encode **fallback logic**?
4. ❓ Does this introduce a **new Core node or edge**?

If the answer to (3) or (4) is **yes** → stop and escalate.

---

## 12. The Golden Rule (Memorize This)

> **Mappings describe what code *means* when it exists — builders decide whether it is true.**

---

## Summary

- ✅ Language-agnostic philosophy
- ✅ Applies to all current and future builders
- ✅ Violations are architectural bugs
- ✅ Clear separation: Mapping → Builder → Test

---

*Spashta-CKG favors clarity over cleverness, structure over speculation, and contracts over guesswork.*

*Last Updated: 2025-12-30*
