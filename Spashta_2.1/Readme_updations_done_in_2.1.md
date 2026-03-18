# Spashta 2.1 — All Changes Done (with Rationale)
## Every modification made in 2.1, why it was needed, and what it fixes

**Last updated:** 2026-03-18

---

## Index

| # | Section | Summary |
|---|---------|---------|
| 1 | [Core Schema — nodes.json](#1-core-schema--nodesjson-v13--v14) | 3 new node types, 2 language expansions |
| 2 | [Core Schema — edges.json](#2-core-schema--edgesjson-v13--v14) | 3 new edge types, 2 existing edge expansions |
| 3 | [What Was NOT Changed (and Why)](#3-what-was-not-changed-and-why) | Items deliberately kept for adapter layer |
| 4 | [Builders — No Changes Yet](#4-builders--no-changes-yet) | Planned but not implemented |
| 5 | [Adapters — No Changes Yet](#5-adapters--no-changes-yet) | Planned but not implemented |
| 6 | [Runtime — No Changes Yet](#6-runtime--no-changes-yet) | Planned but not implemented |
| 7 | [Validation Checklist](#7-validation-checklist) | How to verify changes are correct |

---

## 1. Core Schema — nodes.json (v1.3 → v1.4)

### 1.1 NEW: `Field` node type

```json
"Field": {
    "description": "Typed attribute in a data model (ORM field, schema field, column definition)",
    "languages": ["python", "java", "php", "js"]
}
```

**Why needed:**

Before 2.1, a Django model field like `name = models.CharField(max_length=100)` was stored as a `Variable` node. This made it impossible to distinguish a database column from a local variable or a config setting. The graph had no concept of "this class has these typed fields" — the entire database schema was invisible.

**What was broken without it:**
- "What fields does the User model have?" → unanswerable
- "Show me all CharFields in the project" → impossible (all mixed with Variables)
- ForeignKey relationships between models → invisible (just Variable assignments)
- DB schema impact analysis → blind ("if I remove this field, what breaks?")

**Why it's universal (not framework-specific):**

| Framework | Field equivalent |
|---|---|
| Django | `models.CharField`, `models.ForeignKey` |
| SQLAlchemy | `Column(String)`, `relationship()` |
| Hibernate (Java) | `@Column`, `@ManyToOne` |
| TypeORM (JS/TS) | `@Column()`, `@ManyToOne()` |
| Eloquent (PHP) | `$fillable`, `$casts`, migration `$table->string()` |

Every ORM in every language has the concept of a typed, declarative field. This is a universal software construct, not a framework pattern.

**Companion edge:** `has_field` (Class → Field) — see edges section below.

---

### 1.2 NEW: `Constant` node type

```json
"Constant": {
    "description": "Immutable named value (module-level, class-level, or global)",
    "languages": ["python", "java", "js", "php"]
}
```

**Why needed:**

Before 2.1, `MAX_UPLOAD_SIZE = 10485760` and `temp_file = open(...)` were both `Variable` nodes. There was no way to distinguish a configuration constant from a throwaway local variable. This caused two problems:

1. **12,017 Variable nodes** (69% of all nodes) — most are noise. Constants are the meaningful ones.
2. **1,958 orphan Variable nodes** — many are module-level constants that should be connected via `defines` edges but weren't, because the schema didn't have a separate type for them.

**What was broken without it:**
- "What are the configuration constants in settings.py?" → mixed with all other variables
- "What's the default value of MAX_BATCH_TOKENS?" → have to search 12K Variable nodes
- Impact analysis on a constant change → impossible to scope (constant vs local variable)

**Why it's universal:**

| Language | Constant convention |
|---|---|
| Python | `UPPER_CASE = value` (convention), `Final[int]` (typing) |
| Java | `static final`, `enum` values |
| JavaScript | `const`, `Object.freeze()` |
| PHP | `define()`, `const` |

Every language distinguishes immutable named values from mutable state. This is a universal concept.

---

### 1.3 NEW: `TestCase` node type

```json
"TestCase": {
    "description": "Test container — a class or function that validates behavior",
    "languages": ["python", "java", "js", "php"]
}
```

**Why needed:**

Before 2.1, test classes were stored as regular `Class` nodes. Test functions were regular `Function` nodes. There was no way to:

1. **Separate production code from test code** in the graph
2. **Count test coverage** per module ("how many tests cover ChatService?")
3. **Filter tests out** of architecture diagrams (tests add ~2,100 nodes of noise)

The dev_portal graph viewer had to implement its own test detection via file path patterns (`tests/`, `test_`) because the schema had no concept of test containers.

**What was broken without it:**
- Architecture graph showed 4,482 nodes — 2,159 were tests (48% noise)
- "How many tests does this project have?" → manual file counting
- "Which modules have no tests?" → unanswerable from graph alone

**Why it's universal:**

| Framework | TestCase equivalent |
|---|---|
| Python pytest | `def test_*()`, `class Test*` |
| Python unittest | `class MyTest(TestCase)` |
| JUnit (Java) | `@Test`, `class MyTest extends TestCase` |
| Jest (JS) | `describe()`, `it()`, `test()` |
| PHPUnit | `class MyTest extends TestCase` |

Every language has a standard test container pattern. This is fundamental to software engineering.

---

### 1.4 EXPANDED: `Enum.languages`

```
Before: ["java", "python"]
After:  ["python", "java", "js", "php"]
```

**Why:** TypeScript/JavaScript has had enums since TypeScript 0.9 (2013). PHP added native enums in PHP 8.1 (2021). Excluding them was an oversight.

---

### 1.5 EXPANDED: `Decorator.languages`

```
Before: ["python"]
After:  ["python", "java", "js"]
```

**Why:** Java annotations (`@Override`, `@Entity`, `@RequestMapping`) are the exact equivalent of Python decorators — behavior-modifying metadata on functions/classes. JavaScript/TypeScript decorators (`@Component`, `@Injectable`) are now a TC39 Stage 3 proposal and widely used. Limiting this to Python was incorrect.

---

## 2. Core Schema — edges.json (v1.3 → v1.4)

### 2.1 NEW: `has_field` edge (direct_structural)

```json
"has_field": {
    "from": ["Class"],
    "to": ["Field"],
    "meaning": "Data model declares a typed, persistent field (ORM column, schema attribute)"
}
```

**Why needed:**

The existing `contains_member` edge connects Class → Method/Variable, but it treats `name = models.CharField()` the same as `name = "default"`. The `has_field` edge explicitly marks a Class-to-Field relationship with the understanding that this is a **declarative, typed, persistent** attribute — not a runtime assignment.

**What was broken without it:**
- "What columns does the User table have?" → unanswerable
- "Draw the ER diagram" → impossible (no typed field relationships)
- "Which models have a created_at field?" → requires reading every model file

**Why separate from `contains_member`:**

`contains_member` is a structural fact: "this class contains this name." It doesn't imply persistence, type, or schema meaning. `has_field` adds semantic intent: "this class **declares** this as a persistent, typed attribute." The distinction matters for:
- ER diagram generation (only `has_field` edges, not all `contains_member`)
- Migration impact analysis (field changes affect DB schema)
- API serialization analysis (which fields are exposed?)

---

### 2.2 NEW: `references` edge (reference_symbolic)

```json
"references": {
    "from": ["Class", "Field"],
    "to": ["Class"],
    "meaning": "Relational reference between data models (ForeignKey, OneToOne, ManyToMany, @ManyToOne, belongsTo)"
}
```

**Why needed:**

Before 2.1, a `ForeignKey` relationship like `user = models.ForeignKey(User)` was just a Variable assignment. The fact that Model A **references** Model B was invisible. This is arguably the most critical missing relationship in any ORM-based project.

**What was broken without it:**
- "What models reference User?" → unanswerable
- "If I delete the Workspace model, what other models break?" → blind
- "Draw the data model relationship diagram" → impossible
- Cascade deletion analysis → guesswork

**Why it's universal:**

| ORM | Reference syntax |
|---|---|
| Django | `ForeignKey(User)`, `OneToOneField(Profile)`, `ManyToManyField(Tag)` |
| SQLAlchemy | `relationship()`, `ForeignKey()` |
| Hibernate | `@ManyToOne`, `@OneToMany`, `@JoinColumn` |
| TypeORM | `@ManyToOne(() => User)`, `@JoinColumn()` |
| Eloquent | `belongsTo()`, `hasMany()`, `belongsToMany()` |

Every ORM has explicit relational references. This is a database-universal concept.

**Why named `references` instead of `fk_to`:**

`fk_to` implies specifically ForeignKey. But the concept is broader — it covers OneToOne, ManyToMany, and even non-SQL references (document references in MongoDB, edge references in graph DBs). `references` is the correct universal term.

---

### 2.3 NEW: `listens_to` edge (reference_symbolic)

```json
"listens_to": {
    "from": ["Function", "Method"],
    "to": ["Event", "Signal"],
    "meaning": "Subscribes to or handles an event or signal"
}
```

**Why needed:**

Before 2.1, event/signal connections were invisible. A Django `@receiver(post_save, sender=User)` function had no edge to the `post_save` signal or the `User` model. This means:

- Side effects of model saves → invisible
- Event-driven workflows → untraceable
- "What happens when a User is saved?" → requires reading every file

**What was broken without it:**
- Signal handlers fire silently — if you change the User model, you don't know that `send_welcome_email()` fires on save
- Event chains in JavaScript (click → fetch → update DOM) → invisible
- Impact analysis misses all event-driven side effects

**Why it's universal:**

| Pattern | Language/Framework |
|---|---|
| `@receiver(post_save)` | Django |
| `EventEmitter.on('event', handler)` | Node.js |
| `@EventListener` | Java Spring |
| `document.addEventListener('click', fn)` | Browser JS |
| `Event::listen(OrderCreated::class, fn)` | Laravel |

Every language has an event/signal subscription pattern. This is a core software architecture concept (Observer pattern).

---

### 2.4 EXPANDED: `defines.to`

```
Before: [Class, Function, Interface, Enum, Route, Trait, Component, Hook, StyleClass, StyleID, StyleElement]
After:  [Class, Function, Interface, Enum, Route, Trait, Component, Hook, Variable, Constant, Field, TestCase, StyleClass, StyleID, StyleElement]
```

**Why:** Files define variables, constants, fields, and test cases — not just classes and functions. The 1,958 orphan Variable nodes existed because `defines` didn't include `Variable` in its `to` list. The builder could never create a `defines` edge from a File to a Variable.

**Impact on orphan count:** This single change enables ~1,500 orphan Variables to be connected to their defining File.

---

### 2.5 EXPANDED: `contains_member.to`

```
Before: [Method, Variable]
After:  [Method, Variable, Field, Constant]
```

**Why:** Classes contain fields and constants as members, not just methods and generic variables. Without this, `has_field` edges would violate the schema because `Field` wasn't in any edge's `to` list for class membership.

---

## 3. What Was NOT Changed (and Why)

These items were considered but deliberately **NOT** added to Core schema. They belong in the Adapter layer (semantic roles) because they are framework-specific patterns, not universal software constructs.

| Item | Why NOT in Core | Where it belongs |
|---|---|---|
| `Migration` node | Not every framework has migrations. Rails/Django do, but many projects use raw SQL or schema-less DBs. | Adapter: semantic_role on File node |
| `ManagementCommand` node | Django-specific CLI pattern. Other frameworks have different CLI abstractions (artisan, rake, gradle). | Adapter: semantic_role on Class node |
| `Service` node | Architectural pattern (DDD), not a language construct. A "service" is just a class with business logic. | Adapter: semantic_role on Class node |
| `Fixture` node | Test data format varies wildly (JSON, YAML, factories, builders). Not a universal construct. | Adapter: semantic_role on File node |
| `imports_lazy` edge | Function-scoped imports are a Python/Django pattern. Other languages don't have this distinction. | Metadata flag (`"lazy": true`) on existing `imports` edge |
| `configures` edge | Django admin-specific (Admin → Model). Other frameworks have different admin patterns. | Adapter: custom edge type |

**Principle:** Core schema represents **universal truths about software**. If a concept doesn't exist in at least 3 major languages/frameworks, it's an adapter concern.

---

## 4. Python Builder — Changes Done

### 4.1 Files Modified

| File | Version | What changed |
|---|---|---|
| `builders/python/python_language_mapping.json` | 1.5 → 1.6 | Added `FieldAssign→Field`, `ConstantAssign→Constant`, `TestClassDef→TestCase` node mappings. Added `has_field`, `references_model`, `listens_to_signal`, `import_lazy`, `defines_variable`, `defines_constant`, `defines_field`, `contains_field`, `contains_constant` edge mappings. Schema target: 1.3 → 1.4. |
| `builders/builder_rules.json` | 1.2 → 1.3 | Added 4 new policy sections: `node_classification_policy` (Field/Constant/TestCase detection hints), `call_resolution_policy` (self-call, super-call), `import_scope_policy` (lazy import tracking), `string_reference_policy` (template resolution). |
| `builders/python/build_python_ast.py` | — | 6 functional changes (see below) |

### 4.2 `build_python_ast.py` — Change Details

#### Change 1: Field Detection in `visit_Assign` and `visit_AnnAssign`

**Why needed:** `name = models.CharField(max_length=100)` was a `Variable` node. Now it's a `Field` node with `field_type` and `fk_target` metadata.

**How it works:**
1. Helper `_is_orm_field_call()` checks if RHS is a call to a known ORM constructor
2. Matches 40+ field types: `CharField`, `ForeignKey`, `IntegerField`, `JSONField`, `BooleanField`, etc.
3. Detects FK target from first positional arg: `ForeignKey(User)` → `fk_target = "User"`
4. Emits `has_field` edge (Class → Field) instead of `contains_variable`

**Test result (core_utils/models.py):** 98 Fields detected, 0 false positives.

#### Change 2: Constant Detection in `visit_Assign` and `visit_AnnAssign`

**Why needed:** `MAX_UPLOAD_SIZE = 10485760` was a `Variable`. Now it's a `Constant` if name is `UPPER_CASE`.

**How it works:**
1. Helper `_is_constant_name()` checks if name follows Python `UPPER_CASE` convention
2. Only applies to File-level and Class-level assignments (not inside functions)
3. Emits `Constant` node + `defines_constant` or `contains_constant` edge

**Test result (core_utils/models.py):** 6 Constants detected: `SEARCH_TYPE_CHOICES`, `FILE_TYPE_CHOICES`, `STATUS_CHOICES`, `LLM_SERVICE_TYPE_CHOICES`, `REINDEX_STATUS_CHOICES`.

#### Change 3: TestCase Detection in `visit_ClassDef` and `_handle_function`

**Why needed:** Test classes and functions were mixed with production code. Now they're `TestCase` nodes.

**How it works:**
1. `_is_test_class()` checks inheritance from known test bases (`TestCase`, `TransactionTestCase`, `APITestCase`, etc.) or name pattern (`Test*`, `*Test`)
2. `_is_test_function()` checks `test_*` name + file location (`test_*.py` or `tests/` directory)
3. Emits `TestCase` node instead of `Class` or `Function`

**Test result (notebook_ai/):** 36 TestCases detected correctly.

#### Change 4: FK `references` Edge (Post-processing Pass 3)

**Why needed:** `ForeignKey(User)` was invisible as a relationship. Now it creates a `references` edge from owning Class to target Class.

**How it works:**
1. After Pass 2, iterate all `Field` nodes with `fk_target` metadata
2. Resolve target class name to a registered Class node (same-file first, then global search)
3. Emit `references_model` edge with `via_field` and `field_type` metadata
4. If target not found → ambiguity ticket `fk_target_unresolved`

**Test result (core_utils/models.py):** 4 references: `TabularFile→Document`, `TabularSheet→TabularFile`, `TabularColumn→TabularSheet`, `TabularRow→TabularSheet`.

**Test result (notebook_ai/):** 9 references: `NotebookConfig→Notebook`, `NotebookDocument→Notebook`, `ChatSession→Notebook`, `ChatMessage→ChatSession`, etc.

#### Change 5: Self-method and Super-method Resolution

**Why needed:** `self.save()` inside a method created NO edge. Now it resolves to `EnclosingClass::save`.

**How it works:**
1. Existing `_resolve_expression` already handled `self.X` → find enclosing class → lookup `Class::X`
2. Added: `super().X()` resolution — follows `extends` edges to find parent class method
3. If unresolved, falls through to ambiguity (existing behavior)

#### Change 6: Lazy Import Tracking

**Why needed:** `from core_utils.models import TabularFile` inside a function body was treated the same as file-level imports. Now it gets `lazy=true` metadata.

**How it works:**
1. `_is_lazy_scope()` checks if current scope is Function or Method
2. If lazy: emit `import_lazy` edge type + `lazy: true` metadata
3. Language mapping maps `import_lazy` → `imports` (same Core edge type, with metadata)
4. Impact analysis can filter on `lazy=true` to flag invisible dependencies

**Note:** Lazy imports only resolve when both source AND target modules are in the scan. Single-file scans won't capture them — full project scan required.

### 4.3 Test Results Summary

| Test scan | Nodes | Edges | Fields | Constants | TestCases | FK refs |
|---|---|---|---|---|---|---|
| `core_utils/models.py` (single file) | 177 | 170 | 98 | 6 | 0 | 4 |
| `notebook_ai/` (86 files) | 1,802 | 2,001 | 245 | 15 | 36 | 9 |

---

## 4a. HTML Builder — No Changes Needed

The HTML builder (`builders/html/build_html_ast.py`, 368 lines) was reviewed and found to be complete for 2.1 scope.

**What it already handles correctly:**
- Template nodes for `.html` files
- HTMX interactions: `hx-get`, `hx-post`, `hx-put`, `hx-delete`, `hx-patch`, `hx-target`, `hx-trigger`
- Static asset links: `<link>`, `<script src>`, `<img src>`, `<video>`, `<audio>`
- Form submissions: `<form action=...>` → `submits_form` edge
- Anchor links: `<a href=...>` → `calls_api` edge

**What's NOT in scope (stays for future):**

| Not implemented | Why deferred | Where it belongs |
|---|---|---|
| Django template tags (`{% url %}`, `{% include %}`, `{% extends %}`) | Python-embedded syntax in HTML — requires framework-specific parser | Django adapter or a future `django_template` builder |
| `{% block %}` template inheritance | Framework-specific pattern | Django adapter |
| `{{ variable }}` context variable tracking | Requires knowledge of Python view context | Adapter-level, not structural |

**Verdict:** New Core 1.4 types (`Field`, `Constant`, `TestCase`) and edges (`has_field`, `references`, `listens_to`) are all Python-domain concepts. HTML builder has no interaction with them. No changes needed.

---

## 4b. CSS Builder — No Changes Needed

The CSS builder (`builders/css/build_css_ast.py`, 320 lines) was reviewed and found to be complete for 2.1 scope.

**What it already handles correctly:**
- Stylesheet nodes for `.css` files
- Class selectors (`.my-class`) → `StyleClass` nodes
- ID selectors (`#my-id`) → `StyleID` nodes
- Element selectors (`div`, `body`) → `StyleElement` nodes
- `@import` → `imports` edge to other Stylesheets
- All edges gated by `SchemaEnforcer`

**What's NOT in scope (stays for future):**

| Not implemented | Why deferred |
|---|---|
| CSS variables (`--custom-property`) | Nice-to-have, not structural |
| `@media` queries | Logged as ambiguity — correct behavior per builder rules |
| CSS-in-JS | Not applicable to this project stack |

**Verdict:** No changes needed. CSS builder correctly handles structural CSS parsing.

---

## 4c. Builder Validation — No Changes Needed

`builders/validation/validate_builder_output.py` (275 lines) was tested against the new 2.1 Python builder output. **No changes needed** — the validator dynamically loads `nodes.json` and `edges.json` at runtime, so new Core 1.4 types are automatically recognized.

**Validation results:**

| Builder output | Status | Nodes | Edges | Ambiguities | Schema errors |
|---|---|---|---|---|---|
| `core_utils/models.py` | **PASS** | 177 | 170 | 72 | 0 |
| `notebook_ai/` (86 files) | **PASS** | 1,802 | 2,001 | 2,667 | 0 |

All new node types (`Field`, `Constant`, `TestCase`) and edge types (`has_field`, `references`) pass schema validation.

---

## 5. Django Adapter — Changes Done

### 5.1 Files Modified

| File | Version | What changed |
|---|---|---|
| `adapters/django/framework_mapping.json` | 1.0 → 2.1 | Added 4 new mappings (ManagementCommand, URLConf, AppConfig, Migration). Fixed View function rule (removed overly strict `used_in_calls`). Added inline classes to Admin. Total: 9 → 13 mappings. |
| `runtime/enrich_runtime_ast.py` | — | Implemented 2 detection rules that were declared in mappings but never coded: `arg_names_include` (checks `signature.args`) and `decorators` (checks `signature.decorators`). Fixed `file_path_contains` to also check node's own `file_path` (for File nodes). |

### 5.2 Enrichment Engine Fixes

#### Fix 1: `arg_names_include` detection (was dead code)

**Bug:** The Django View function mapping declared `arg_names_include: ["request"]` but the enrichment engine had NO code to check it. The rule was silently ignored — View functions never matched.

**Fix:** Added code that reads `node.signature.args` (populated by Python builder) and checks if any required arg name is present.

**Impact:** 28 View functions now detected in `notebook_ai/` alone.

#### Fix 2: `decorators` detection (was dead code)

**Bug:** The Signal mapping declared `decorators: ["receiver"]` but the enrichment engine had no code for it. Signal handlers were never detected.

**Fix:** Added code that reads `node.signature.decorators`, normalizes them (strips `@` and `(...)`), and checks for matches.

**Impact:** `@receiver` decorated functions now correctly get the `Signal` role.

#### Fix 3: `file_path_contains` for File nodes

**Bug:** For File nodes (Migration, URLConf), the `file_path_contains` rule only checked incoming `defines` edges to find the parent file. But File nodes don't have parents — they ARE the file.

**Fix:** Added a first check on the node's own `file_path` field before falling back to the parent-via-defines-edge check.

**Impact:** Migration and URLConf mappings now work for File nodes.

### 5.3 New Django Adapter Mappings

| # | Role | Core Node | Detection Rule | Confidence | Why added |
|---|---|---|---|---|---|
| 10 | ManagementCommand | Class | `file_path_contains: management/commands/` | 100% | Universal Django convention — every Django project uses this directory structure |
| 11 | URLConf | File | `file_path_contains: *urls.py` | 100% | Universal Django convention — URL routing always in `urls.py` or `*_urls.py` |
| 12 | AppConfig | Class | `file_path_contains: apps.py` | 100% | Universal Django convention — app configuration always in `apps.py` |
| 13 | Migration | File | `file_path_contains: migrations/` | 100% | Universal Django convention — schema migrations always in `migrations/` directory |

### 5.4 Existing Mapping Fixes

| Mapping | What changed | Why |
|---|---|---|
| View (Function) | Removed `used_in_calls: [render, HttpResponse, ...]` | Too strict — many views return `JsonResponse` without calling `render()`. `request` arg + `views` file path is sufficient and non-debatable. |
| View (Class) | Added `ModelViewSet`, `FormView`, `RedirectView`, `GenericAPIView` to `inheritance_includes` | Common DRF/Django view bases that were missing. |
| Admin | Added `admin.TabularInline`, `admin.StackedInline` | Inline admin classes are part of Django admin customization. |
| Signal | Removed `used_in_calls: [receiver]` — now uses only `decorators: [receiver]` | `@receiver` is a decorator, not a call target. The old rule was semantically wrong. |

### 5.5 What Was NOT Added (and Why)

| Role | Why not added | Where it belongs |
|---|---|---|
| Service | Project convention (`services/` directory), not universal Django | Project-specific adapter or future `name_pattern` rule |
| Adapter | Project convention (`adapters/` directory) | Project-specific adapter |
| Singleton | Pattern detection (`load()` classmethod) — ambiguous | Future enhancement with confidence label |
| TestCase (adapter) | Already handled by Python builder as a Core node type | Not needed — builder emits `TestCase` directly |

### 5.6 Test Results

Enrichment of `notebook_ai/` (86 files, 1802 nodes):

| Role | Count | Detection method |
|---|---|---|
| Migration | 45 | `file_path_contains: migrations/` |
| View | 28 | `arg_names_include: [request]` + `file_path_contains: *views*` |
| URLConf | 2 | `file_path_contains: *urls.py` |
| AppConfig | 1 | `file_path_contains: apps.py` |
| ManagementCommand | 1 | `file_path_contains: management/commands/` |
| **Total** | **77** | — |

**Comparison:** Spashta 2.0 applied 100 roles total across the ENTIRE project (all just "Component"). Spashta 2.1 applies 77 meaningful roles on just ONE app (`notebook_ai/`). Full project enrichment expected to yield 300+ specific roles.

---

## 6. Runtime — Changes Done

### 6.1 Enrichment Engine (`enrich_runtime_ast.py`)

Already documented in Section 5.2 (Django Adapter). Summary of all engine changes:

| # | Change | Type |
|---|---|---|
| 1 | Implemented `arg_names_include` detection rule | Bug fix (was dead code) |
| 2 | Implemented `decorators` detection rule | Bug fix (was dead code) |
| 3 | Implemented `has_outgoing_edge` detection rule | New rule (for HTMX) |
| 4 | Fixed `file_path_contains` — checks node's own `file_path` or `name` for File/Template nodes | Bug fix |
| 5 | Fixed `file_path_contains` — falls back to parent File via `defines` edge for Class/Function nodes | Already worked in 2.0 |
| 6 | Hardcoded `Spashta_2.0` path → `Spashta_2.1` | Path fix |

### 6.2 AST Equivalence Validator (`validate_ast_equivalence.py`)

3 bugs found and fixed:

| # | Bug | Fix |
|---|---|---|
| 1 | **`node_type` vs `type` key** — validator only checked `node.get('type')` but Python builder emits `node_type`. Nodes with only `node_type` would show as "type changed from None to None". | Now checks `node.get('node_type') or node.get('type')` for both raw and enriched. |
| 2 | **Edge key format** — `get_edge_key()` hardcoded `edge['source']` / `edge['target']` but Python builder 2.1 emits `from`/`to` keys. Would crash on builder output. | Now uses `edge.get('source', edge.get('from'))` pattern — handles both formats. |
| 3 | **Hardcoded `Spashta_2.0` path** — report directory pointed to 2.0, not 2.1. | Changed to `Spashta_2.1`. |

---

## 7. Validation Checklist

After any Core schema change, verify:

- [ ] `nodes.json` is valid JSON (`python -c "import json; json.load(open('nodes.json'))"`)
- [ ] `edges.json` is valid JSON (`python -c "import json; json.load(open('edges.json'))"`)
- [ ] Every node type in `edges.json` `from`/`to` lists exists in `nodes.json`
- [ ] No existing node types were removed (additive only)
- [ ] No existing edge types were removed (additive only)
- [ ] No existing `from`/`to` constraints were narrowed (only expanded)
- [ ] `_meta.version` incremented
- [ ] `_meta.changelog_*` documents what changed and why
- [ ] All new types have `description` field
- [ ] All new types have `languages` list (or `"any"`)
- [ ] Changes are universal (not framework-specific)

### Quick validation command:

```bash
cd Spashta-CKG/Spashta_2.1/core/software_schema
python -c "
import json
n = json.load(open('nodes.json'))
e = json.load(open('edges.json'))
node_types = {k for k in n if k != '_meta'}
edge_types = set()
for section in ['direct_structural', 'reference_symbolic']:
    for ename, edef in e[section].items():
        edge_types.add(ename)
        for f in edef.get('from', []):
            assert f in node_types, f'Edge {ename}: from={f} not in nodes'
        for t in edef.get('to', []):
            assert t in node_types, f'Edge {ename}: to={t} not in nodes'
print(f'Validated: {len(node_types)} nodes, {len(edge_types)} edges. All references resolved.')
"
```

---

## Summary of All 2.1 Changes

### Core Schema (nodes.json + edges.json)

| # | File | Change | Type |
|---|---|---|---|
| 1 | `nodes.json` | Added `Field` node | New node |
| 2 | `nodes.json` | Added `Constant` node | New node |
| 3 | `nodes.json` | Added `TestCase` node | New node |
| 4 | `nodes.json` | Expanded `Enum.languages` (+js, +php) | Language expansion |
| 5 | `nodes.json` | Expanded `Decorator.languages` (+java, +js) | Language expansion |
| 6 | `edges.json` | Added `has_field` edge | New edge |
| 7 | `edges.json` | Added `references` edge | New edge |
| 8 | `edges.json` | Added `listens_to` edge | New edge |
| 9 | `edges.json` | Expanded `defines.to` (+Variable, Constant, Field, TestCase) | Constraint expansion |
| 10 | `edges.json` | Expanded `contains_member.to` (+Field, Constant) | Constraint expansion |

### Python Builder

| # | File | Change | Type |
|---|---|---|---|
| 11 | `python_language_mapping.json` | Added 8 node mappings + 9 edge mappings | Mapping expansion |
| 12 | `builder_rules.json` | Added 4 policy sections (classification, call resolution, import scope, string reference) | Policy addition |
| 13 | `build_python_ast.py` | Field detection (ORM field constructors → Field node + has_field edge) | New detection |
| 14 | `build_python_ast.py` | Constant detection (UPPER_CASE → Constant node) | New detection |
| 15 | `build_python_ast.py` | TestCase detection (test base classes + name patterns) | New detection |
| 16 | `build_python_ast.py` | FK references (ForeignKey → references edge between Classes) | New edge emission |
| 17 | `build_python_ast.py` | Self-method resolution (self.X() → Class::X calls edge) | Improved resolution |
| 18 | `build_python_ast.py` | Super-method resolution (super().X() → parent class via extends) | New resolution |
| 19 | `build_python_ast.py` | Lazy import tracking (function-scoped imports get lazy=true metadata) | New metadata |

### Django Adapter + Enrichment Engine

| # | File | Change | Type |
|---|---|---|---|
| 20 | `adapters/django/framework_mapping.json` | Added ManagementCommand, URLConf, AppConfig, Migration mappings (9 → 13) | New mappings |
| 21 | `adapters/django/framework_mapping.json` | Fixed View function (removed overly strict used_in_calls) | Rule fix |
| 22 | `adapters/django/framework_mapping.json` | Fixed Signal (decorators instead of used_in_calls) | Rule fix |
| 23 | `adapters/django/framework_mapping.json` | Added ModelViewSet, FormView, Inline to existing rules | Expansion |
| 24 | `runtime/enrich_runtime_ast.py` | Implemented `arg_names_include` detection (was dead code) | Bug fix |
| 25 | `runtime/enrich_runtime_ast.py` | Implemented `decorators` detection (was dead code) | Bug fix |
| 26 | `runtime/enrich_runtime_ast.py` | Fixed `file_path_contains` for File nodes (self-path check) | Bug fix |

### FastAPI Adapter — Changes Done

The FastAPI adapter (`adapters/fastapi/framework_mapping.json`) was updated: 5 → 7 mappings (2 new + 2 dead rules documented with `_known_limitation`).

**Working changes (use implemented detection rules):**

| # | Change | What | Why |
|---|---|---|---|
| 1 | View: `decorated_by` → `decorators` | Now reads `signature.decorators` instead of requiring decorator node in registry | More reliable — string-based match vs edge-based. Added `websocket`, `options`, `head`. |
| 2 | NEW: EventHandler | Detects `@on_event("startup")`, `@on_shutdown` | FastAPI lifecycle hooks — uses `decorators` rule (2.1) |
| 3 | NEW: Middleware | Detects `@app.middleware("http")` | FastAPI middleware — uses `decorators` rule (2.1) |
| 4 | DataModel: expanded | Added `DeclarativeBase`, `db.Model` | Common SQLAlchemy 2.0 base classes |
| 5 | APIContract: expanded | Added `BaseSettings`, `pydantic.BaseSettings` | Pydantic settings classes are API contracts |

**Dead rules (documented, kept for future):**

| # | Role | Dead rule | Root cause | `_known_limitation` added |
|---|---|---|---|---|
| 6 | Dependency | `core_node: Call` — builder doesn't emit Call nodes | Call is not a structural node | Yes |
| 7 | Router | `assigned_value` — not implemented in engine | Engine lacks assigned_value rule | Yes |

### HTMX Adapter — Changes Done

The HTMX adapter (`adapters/htmx/framework_mapping.json`) was updated: 2 mappings (both fixed).

**Changes:**

| # | Change | What | Why |
|---|---|---|---|
| 1 | Component: `contains_attributes` → `has_outgoing_edge` | Dead rule replaced with working rule. Detects Templates that have `calls_api`, `triggers_event`, or `submits_form` outgoing edges (created by HTML builder for hx-* attributes). | `contains_attributes` was never implemented in engine. `has_outgoing_edge` is new in 2.1. |
| 2 | NEW: Fragment | Detects partial templates in `partials/` directories via `file_path_contains`. | Standard Django+HTMX convention — partials are HTMX swap targets. |

**Enrichment engine changes for HTMX:**

| Change | What |
|---|---|
| `has_outgoing_edge` rule | NEW detection rule — checks if node has at least one outgoing edge of specified type. Generic and reusable (not HTMX-specific). |
| `file_path_contains` name fallback | Fix: Template nodes have path in `name` field, not `file_path`. Engine now checks `node.file_path OR node.name` before falling back to parent via defines edge. |

**Test results (full project graph, roles stripped for clean test):**

| Role | Count | Detection |
|---|---|---|
| Component | 63 | Templates with `calls_api`/`triggers_event`/`submits_form` edges |
| Fragment | 50 | Templates in `partials/` directories |
| **Total** | **113** | — |

**Comparison to 2.0:** All 100 templates got "Component" blindly. Now: 63 get Component (actually interactive), 50 get Fragment (HTMX swap targets), 37 templates have no HTMX role (static templates — correct).

---

## Summary of All 2.1 Changes

### Core Schema (nodes.json + edges.json)

| # | Change | Type |
|---|---|---|
| 1-3 | Added `Field`, `Constant`, `TestCase` nodes | New nodes |
| 4-5 | Expanded `Enum`, `Decorator` languages | Language expansion |
| 6-8 | Added `has_field`, `references`, `listens_to` edges | New edges |
| 9-10 | Expanded `defines.to`, `contains_member.to` | Constraint expansion |

### Python Builder

| # | Change | Type |
|---|---|---|
| 11 | Language mapping: +8 node mappings, +9 edge mappings | Mapping expansion |
| 12 | Builder rules: +4 policy sections | Policy addition |
| 13-15 | Field, Constant, TestCase detection | New detection |
| 16 | FK references edges (ForeignKey → Class → Class) | New edge emission |
| 17-18 | Self-method + super-method resolution | Improved resolution |
| 19 | Lazy import tracking (lazy=true metadata) | New metadata |

### Django Adapter + Enrichment Engine

| # | Change | Type |
|---|---|---|
| 20 | 4 new mappings: ManagementCommand, URLConf, AppConfig, Migration | New mappings |
| 21-23 | Fixed View, Signal, Admin rules | Rule fixes |
| 24-25 | Implemented `arg_names_include`, `decorators` detection (was dead code) | Bug fixes |
| 26 | Fixed `file_path_contains` for File + Template nodes | Bug fix |

### FastAPI Adapter

| # | Change | Type |
|---|---|---|
| 27 | View: `decorated_by` → `decorators` (string-based) | Rule fix |
| 28-29 | NEW: EventHandler, Middleware mappings | New mappings |
| 30 | Expanded DataModel + APIContract inheritance | Expansion |
| 31 | Documented 2 dead rules (`_known_limitation`) | Documentation |

### HTMX Adapter

| # | Change | Type |
|---|---|---|
| 32 | Component: dead `contains_attributes` → working `has_outgoing_edge` | Rule fix |
| 33 | NEW: Fragment (`file_path_contains: partials/`) | New mapping |
| 34 | NEW: `has_outgoing_edge` detection rule in engine | New rule |
| 35 | Fixed `file_path_contains` name fallback for Templates | Bug fix |

### Adapter Validator

| # | File | Change | Type |
|---|---|---|---|
| 36 | `adapters/validation/validate_adapter_rules.py` | Separated warnings from violations — custom semantic roles are WARNINGS not errors | Bug fix |
| 37 | `adapters/validation/validate_adapter_rules.py` | Missing `core/agent_rules/` files are WARNINGS not errors | Bug fix |
| 38 | `adapters/validation/validate_adapter_rules.py` | NEW: Detection rule key validation — catches typos (e.g. `inhertance_includes` → ERROR with suggestion) | New validation |
| 39 | `adapters/validation/validate_adapter_rules.py` | NEW: Unimplemented rule detection — flags rules not in engine (e.g. `context`, `assigned_value`) as WARNING unless `_known_limitation` acknowledged | New validation |

**Validator now checks 3 levels:**
- **ERROR** — unknown detection rule key (typo or genuinely invalid) → blocks
- **WARNING (unimplemented)** — rule exists but engine doesn't support it yet → informs
- **WARNING (custom role)** — semantic role not in Core nodes.json → expected for framework-specific roles

All 3 adapters PASS validation (0 violations, warnings correctly categorized).

### HTML + CSS Builders + Builder Validator

No changes needed — reviewed, documented as complete for 2.1 scope.

### Runtime

| # | File | Change | Type |
|---|---|---|---|
| 40 | `runtime/validate_ast_equivalence.py` | Fixed `node_type` vs `type` key mismatch — checks both | Bug fix |
| 41 | `runtime/validate_ast_equivalence.py` | Fixed edge key format — handles `from`/`to` and `source`/`target` | Bug fix |
| 42-47 | ALL runtime `.py` files | Fixed hardcoded `Spashta_2.0` → `Spashta_2.1` path in 6 files: `build_runtime_ast.py`, `enrich_runtime_ast.py`, `validate_ast_equivalence.py`, `diff_runtime_ast.py`, `query_spashta.py`, `enrichment_through_LLM/apply_demo_agent_enrichment.py` | Path fix |
| 48 | `runtime/diff_runtime_ast.py` | Added `has_field`, `contains_field`, `contains_constant` to ownership edges — Field/Constant nodes now inherit parent file's diff status | Bug fix |
| 49 | `runtime/diff_runtime_ast.py` | Fixed edge key format — handles both `source`/`target`/`type` and `from`/`to`/`edge` | Bug fix |
| 50 | `runtime/enrich_runtime_ast.py` | Updated docstring — lists all 9 detection rules (was only 4) | Documentation fix |
| 51 | `runtime/enrichment_through_LLM/llm_enrich_runtime_ast.py` | Version string 2.0 → 2.1 | Version fix |
| 52 | `runtime/enrichment_through_LLM/llm_enrichment_rules.json` | Updated node types list to include Field, Constant, TestCase (Core 1.4). Version 1.0 → 1.1. | Documentation fix |
| 53 | `runtime/Integrity_Check_Spashta2.1.txt` | NEW file replacing `Integrity_Check_Spashta2.0.txt`. Updated all paths to 2.1, added 7-step check sequence with exact commands, fixed typo `Spashta_2.0_Devlopment`. | New file |
| 54 | `runtime/query_spashta.py` | `stats` command now returns node_type counts, edge_type counts, semantic_roles counts, and ambiguity count (was just total nodes/edges) | Enhancement |
| 55 | `runtime/query_spashta.py` | `locate` command now resolves file path from node ID or name when `file_path` field is missing (same logic as `read` command) | Bug fix |
| 56 | `runtime/query_spashta.py` | Windows encoding safety — forces UTF-8 stdout/stderr on Windows to prevent cp1252 crashes on Unicode characters | Bug fix |
| 57 | `runtime/query_spashta.py` | "Node not found" now returns suggestions — searches for similar nodes by name substring | Enhancement |
| 58 | `runtime/query_spashta.py` | `search --app` filter — filter results by app/directory prefix (e.g. `--app core_utils`) | Enhancement |
| 59 | `runtime/query_spashta.py` | `list-files --app` filter + grouped JSON output by app | Enhancement |
| 65 | `runtime/query_spashta.py` | `impact` output now includes `layer` field on each result (view/service/admin/model/test/other) + `layer_coverage` summary + `missing_layers` list + warning if view/service absent | Enhancement (#3 + #6 from Improvement Proposals) |
| 66 | `runtime/query_spashta.py` | NEW: `scope-check` command — compares analyzed files against impact results, returns unanalyzed production files with coverage percentage and COMPLETE/INCOMPLETE verdict | New command (#5 from Improvement Proposals) |
| 67 | `runtime/query_spashta.py` | `get_node()` auto-detects file paths — if `locate "models.py"` fails, auto-tries `File:models.py`. Eliminates TRAP 1. | Enhancement (#2 from Quick Wins) |
| 68 | `runtime/query_spashta.py` | `search --json` now returns `metadata` block: `total_matches`, `total_searched`, `query`, filters applied | Enhancement (#4 from Quick Wins) |
| 69 | `project/Prompt_to_use_Spashta-CKG.txt` | Updated Section 2 output format table — added signature, semantic_roles, field_type, fk_target metadata docs. Added details/scope-check to table. Updated Quick Reference Card with all 2.1 commands + output types. | Documentation |
| 70 | `runtime/execution_protocol.json` | Fixed 3 `Spashta_2.0` path references → `Spashta_2.1`. Fixed **wrong command names** in `post_completion.query_tool.key_commands` (listed nonexistent commands like `list-functions`, `search-callers`, `impact-analysis` — replaced with actual commands: search, locate, read, details, impact, etc.). Added scope-check to agent guidelines. Updated completion message examples. | Bug fix + documentation |
| 71 | `_docs/` (7 files) | Bulk replaced all `Spashta_2.0` → `Spashta_2.1` across: `Runtime_Readme.md`, `frozen_artifacts.json`, `Notes.md`, `coder_style.json`, `Testimony_on_Spashta2.md`, `Json_Info_Readme.md`, `project_governance.json` | Path fix |
| 72 | `_docs/Runtime_Readme.md` | Replaced wrong command table (old 1.x syntax: `--list-functions`, `--find`, `--deps`, `--callers`) with actual 2.1 commands (search, locate, read, details, impact, scope-check, etc.) | Bug fix |
| 73 | `_docs/Query_Tool_Readme.md` | Added "New in 2.1" section: scope-check command, --app filter, Field/Constant/TestCase types, enhanced impact with layers, enhanced search with metadata, auto File: prefix, Windows Unicode safety, node-not-found suggestions | Documentation |
| 74 | `core/software_schema/edges.json` | Added `Function`, `Method` to `imports.from` — **fixes lazy import tracking**. Schema enforcer was rejecting function-scoped imports because only File/Module/Stylesheet were allowed as import sources. This was THE root cause of invisible lazy imports. +311 edges recovered. | Critical bug fix |
| 75 | `runtime/query_spashta.py` | NEW: `consumers` command — grep+graph hybrid. Finds ALL files that use a model via ORM patterns (.objects.create, .filter, get_or_create, etc.) + graph impact. Returns files classified by layer, with `grep_only` list showing blind spots not in graph. | New command (#2 from Improvement Proposals) |
| 76 | `runtime/query_spashta.py` | Contextual `[Spashta]` hints on stderr after every JSON command — guides agents on what to do next (e.g. "run impact before editing", "check grep_only_files"). 11 command-specific hints. | Enhancement |
| 60 | `project/profile.json` | `project_root` changed from hardcoded absolute path to relative `".."` — portable across machines | Bug fix |
| 61 | `project/profile.json` | Added `_meta.version` (2.1) and `_meta.core_schema_version` (1.4) for compatibility tracking | Enhancement |
| 62 | `project/profile.json` | Removed project-specific helper comments and notes | Cleanup |
| 63 | `project/runtime_logs/session_log.schema.json` | Added `diff_runtime_ast` step (was missing from pipeline schema). Added `skipped` as valid status. Updated example. | Schema fix |
| 64 | `project/Prompt_to_use_Spashta-CKG.txt` | All 14 path references `Spashta_2.0` → `Spashta_2.1`. Version v3 → v4. Simplified TRAP 4 (Windows Unicode auto-fixed). Added `--app` filter examples, new node types (Field, Constant, TestCase), enhanced stats output, node-not-found suggestions. | Major update |
| — | `project/context_loader.py` | Reviewed — no changes needed. Uses relative paths, no stale references. | No change |
| — | `project/validation/validate_project_profile.py` | Not reviewed (validation logic — separate concern) | Not in scope |

**Grand total: 76 changes (across Core, Builder, 3 Adapters, Enrichment Engine, 2 Validators, 6 Runtime scripts). 3 new Core nodes, 3 new Core edges, 2 expanded edges, 2 language expansions, 9 builder changes, 7 new adapter mappings, 5 enrichment engine fixes, 4 adapter rule fixes, 4 validator fixes, 3 runtime fixes. Zero removals. Zero breaking changes. All 3 adapters PASS validation.**
