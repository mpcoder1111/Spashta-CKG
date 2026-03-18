# Spashta-CKG Development Notes

## Coverage Analysis Scope (`check_python_mapping_coverage.py`)

The validation script `builders/python/tests/check_python_mapping_coverage.py` is designed with a specific, limited scope. It verifies the **Vocabulary Coverage** of the builder, not its Behavioral Policies.

### What is Included?
*   **Target**: `builders/python/python_language_mapping.json`
*   **Goal**: To ensure that every Node Type (e.g., `Class`, `Function`) and Edge Type (e.g., `calls`, `inherits_from`) defined in the Python Mapping is actually capable of being produced by the builder when running against `dummy_python_code.py`.
*   **Reasoning**: This proves that the builder syntax translation layer is complete.

### What is Excluded?
*   **`core/software_schema/nodes.json` & `edges.json`**: These define the *universal* set of all possible types across all languages. The coverage analyzer does not validate against these because a Python builder is not expected to produce non-Python types (like C++ Pointers or Java Interfaces), so "missing" them is not an error.
*   **`builders/builder_rules.json`**: This defines *runtime policies* (e.g., Max Recursion Depth, Error Logging behavior). Validating these requires behavioral/stress testing (e.g., forcing a crash), which is outside the scope of a static schema coverage check.

## Schema Refinement Log
*   **Removal of `Decorator` Node Mapping**:
    *   **Action**: Removed `"Decorator": "Decorator"` from `builders/python/python_language_mapping.json`.
    *   **Reason**: In the Python AST, a decorator is not a distinct node definition (like `ClassDef` or `FunctionDef`). It is represented in the AST as a reference within decorator_list (or callable) applied to another node. The builder correctly models this as a `decorates` **Edge** between two Function nodes (or Function and Class). Expecting a distinct "Decorator" **Node** type was ensuring a schema mismatch with reality.
    *   **Result**: The Coverage Analyzer now correctly reports 100% vocabulary coverage without expecting a non-existent node type.

### Builder Behavior Verification
*   **Enforcement of `builder_rules.json`**:
    *   **Action**: Updated `build_python_ast.py` to actively enforce `recursion_depth_policy` and `heuristic_policy`.
    *   **Verification**: Added a stress test to `dummy_python_code.py` with nesting level > 10.
    *   **Result**: The builder correctly triggered the limit, prevented further descent, and logged `[RECURSION_LIMIT] Max depth 10 exceeded`, confirming that runtime safety policies are active and effective.

### Architectural Decisions
*   **Role of `builder_rules.json`**:
    *   **Decision**: MUST be enforced by the Builder.
    *   **Implementation**: Enforced recursion limits and heuristic policies in `build_python_ast.py`.
*   **Role of `contracts.json`**:
    *   **Decision**: Loaded but NOT enforced during AST extraction.
    *   **Reasoning**: Contract validation requires a complete graph context and is computationally expensive during parsing. The Builder acts as a neutral "Camera", capturing what exists. Validation of whether those relationships are "legal" is a post-processing step (Adapter/Validator layer).

### Naming Conventions
*   **Language Specificity**:
    *   **Rule**: All language-specific executables and test utilities MUST include the language name in the filename.
    *   **Examples**: `build_python_ast.py` (not `build_ast.py`), `check_python_mapping_coverage.py`.
    *   **Reason**: Prevents ambiguity and collision when supporting multiple languages (e.g., JS, Java).

## Governance & Bootstrap Architecture (Future Formalization)
*   **Task**: Formalize the role of `follow_spashta_rules.json` in the Core Architecture.
*   **Current Status**: Experimental / Governance Helper.
*   **Concept**: A declarative "Governance Map" that serves as the single source of truth for Agents to bootstrap their behavior, permissions, and validation sequences.
*   **Philosophy**: "Spashta explains itself explicitly to both humans and agents."

## Adapter Testing Philosophy

**One-sentence mental model:**
> Dummy adapter code is written to stress-test semantic inference on top of a correct raw AST — not to test application logic.

### Why the adapter “dummy code” looks like normal Python (not AST)
Because adapters are NOT tested on AST input directly. They are tested on code that will **PRODUCE** a specific AST shape.

👉 The real input to adapters is the Builder AST.
👉 But the test fixture is source code, because:

```
Source code
   ↓ (Builder)
Raw AST
   ↓ (Adapter rules)
Adapter-enriched AST
```

So the dummy FastAPI file is a **signal generator**, not the adapter input itself.

### What the dummy code is actually testing (Mapping → AST Signals)
Each line exists to create a structural AST pattern that adapters later interpret.

| Code you wrote                | What the Builder emits | What Adapter infers |
| ----------------------------- | ---------------------- | ------------------- |
| `class Hero(SQLModel)`        | Class + inherits_from  | DataModel           |
| `class HeroCreate(BaseModel)` | Class + inherits_from  | APIContract         |
| `@app.post("/heroes/")`       | Decorator + Call       | Route + View        |
| `Depends(get_session)`        | Call                   | Dependency          |
| `router = APIRouter()`        | Assign + Call          | Router context      |

The adapter never sees this code.
It only sees the AST nodes & edges created by the builder.

### Why we don’t hand-write AST JSON for adapter tests

Because that would be:
*   brittle
*   unreadable
*   disconnected from real frameworks

Using real framework code ensures:
*   builders extract realistic ASTs
*   adapters are forced to work with real patterns
*   no cheating via handcrafted ASTs

This is the same philosophy used in compiler tests.

**One-line mental model (keep this):**
Dummy adapter code is written for humans; adapters consume only the AST it produces.

### Final confirmation
✔ The dummy FastAPI code is correct
✔ It is not adapter input, but adapter test stimulus
✔ Your testing approach is architecturally sound

### Python Builder Finalization (Dec 2025)
*   **Intentional Coverage Gap (`uses_async`)**:
    *   **Observation**: The edge `uses_async` is listed in `python_language_mapping.json` but is not emitted by the builder in the final frozen state.
    *   **Reason**: The Core Schema (`edges.json`) does not yet formally support `uses_async`. Collapsing it to `calls` was rejected to preserve semantic precision.
    *   **Decision**: The builder detects `await` expressions (logic present in `visit_Await`) but suppresses edge emission. This results in 11/12 edge coverage. This gap is intentional and approved.
    *   **Status**: Builder Frozen.

### HTML Builder Verification (Dec 2025)
*   **Status**: **PASS**
*   **Coverage**: 100% Node Types, 100% Edge Types.
*   **Validation**: 0 Violations.
*   **Notes**: Validation logic was updated to rigorously check `attribute_interactions` (HTMX), confirming complete coverage.

### JavaScript Builder Verification (Dec 2025)
*   **Status**: **PASS**
*   **Coverage**: Nodes 7/7, Edges 5/5.
*   **Correction**: `Hook` node usage was removed from mapping (`js_language_mapping.json`) to comply with frozen Core Schema (replaced with `Function`).
*   **Logic Patch**: `build_javascript_ast.py` updated to emit an implicit "Script Function" to allow `calls` and `calls_api` to originate from a valid Logic Node (instead of `File`), resolving schema violations.
*   **Core Integrity**: **Zero Core Changes** were made. Validation failures were resolved strictly by adapting the Builder logic and Mapping to the frozen Core schema.

⚠️ **WARNING**: JavaScript Builder uses an implicit "script function" to model top-level execution because regex parsing cannot track scope.
*   **Prevention**: This prevents validation failures where `File` tries to be the source of `calls` or `calls_api`.
*   **Constraint**: Do NOT optimize this away unless implementing a full AST parser with scope awareness.
*   **Governance**: Do NOT relax the Core Schema to allow `File -> calls` just to accommodate this builder's limitations. The Builder must adapt (as it has), not the Core.

### CSS Builder Verification (Dec 2025)
*   **Status**: **PASS**
*   **Coverage**: Nodes 4/4, Edges 2/2.
*   **Validation**: 0 Violations.
*   **Notes**: Simple regex-based builder. Coverage confirmed for `StyleClass`, `StyleID`, `StyleElement`, and `@import`. No schema conflicts found.

### Core Integrity Statement
No, I have strictly avoided modifying the Core Schema (`nodes.json`, `edges.json`) during the JavaScript builder validation process.

When I encountered a validation failure (`calls` -> `Hook` and `File` -> `calls_api`), I resolved it by:
1.  Updating the Builder Logic (`build_javascript_ast.py`) to emit an implicit "Script Function", ensuring calls originate from a valid `Function` node instead of `File`.
### GOVERNANCE: CORE FROZEN
**Status**: Core Schema (`nodes.json`, `edges.json`, `contracts.json`) is **FROZEN**.

*   **Rule**: Any future mismatch MUST be resolved in:
    *   Builder Logic
    *   Language Mapping
    *   Adapter Rules
*   **Prohibition**: ❌ Never relax Core edges/nodes without explicit architectural design review.
*   **(Documentation)**: Intentional omissions (e.g., `uses_async` detected but suppressed) are documented in this file to prevent regression.

### Django Adapter Verification (Dec 2025)
*   **Status**: **PASS**
*   **Detection**: `DataModel` and `View` roles correctly inferred from `dummy_models.py` and `dummy_views.py`.
*   **Validation**: `validate_adapter_rules.py` passes (JSON Schema compliance).
*   **Detection**: `DataModel` and `View` roles correctly inferred from `dummy_models.py` and `dummy_views.py`.
*   **Validation**: `validate_adapter_rules.py` passes (JSON Schema compliance).
*   **Limitation**: `Route` role is currently **NOT detected** because the Python Builder does not emit `Call` nodes (only `calls` edges). The mapping rule for `path()` calls is preserved for future v2 builder upgrades but is currently inert.

### FastAPI Adapter Verification (Dec 2025)
*   **Status**: **PASS**
*   **Detection**: `DataModel`, `APIContract`, `View`, `Route`, `Dependency` roles detected from `dummy_fastapi_app.py`.
*   **Note**: `Route` detection works (unlike Django) because FastAPI uses Decorators (`@app.get`), which are handled by the Python Builder's `decorates` edge logic.

### HTMX Adapter Verification (Dec 2025)
*   **Status**: **PASS**
*   **Detection**: `Dependency` and `HTMXInteraction` detected from `dummy_htmx.html`.

### React Adapter Status
*   **Status**: **Missing / To-Be-Implemented**
*   **Note**: Folder `adapters/react` does not exist. Hook semantics currently reside in logical limbo (Js Builder emits Functions; no Adapter claims them). This is a known v1 state.

***

# 🛑 AUTHORITATIVE FREEZE INSTRUCTION (Dec 2025)

**The following paths are FROZEN — DO NOT TOUCH:**

1.  `core/software_schema/` (`nodes.json`, `edges.json`, `contracts.json`)
2.  `builders/*` (Python, HTML, JS, CSS logic, mappings, tests)
3.  `builders/validation/` (`validate_builder_output.py`)
4.  `adapters/*` (Django, FastAPI, HTMX JSONs, tests)
5.  `adapters/validation/` (`validate_adapter_rules.py`)

**These are final, validated, and locked.**
Any changes require a new Governance Directive.

### 🛑 What must NEVER be done now (Architectural Red Line)
*   ❌ **No Core schema changes** to “fix” runtime issues.
*   ❌ **No builder logic changes** for semantic reasons.
*   ❌ **No adapter JSON key changes** (only values, if explicitly requested).

**Resolution Rule**: If something fails → **Runtime usage logic** must adapt. The Data Structure (CKG) is immutable.

### Project Profile Verification (Dec 2025)
*   **Script**: `project/validation/validate_project_profile.py`
*   **Status**: **PASS**
*   **Configuration**:
    *   **Languages**: Python, HTML, CSS, JavaScript (All Validated).
    *   **Frameworks**: Django, HTMX (All Validated).
    *   **Excluded**: FastAPI (Logic Validated, but inactive in profile).

### Runtime & Execution Protocol (Dec 2025)
execution_loop.json is the constitution of Spashta execution.
Agents must read it first, follow it strictly, use the virtual environment, request user confirmation at each irreversible step, and never modify files on failure.
Any error results in report-only + halt behavior. Runtime scripts must obey this protocol without exception.

---

## Future Enhancements (Planned)

### Level-1 Enrichment Scope (Design Decision)

**What Level-1 Enriches:**
- ✅ **Nodes Only** — Adds `semantic_roles` array (e.g., `["DataModel", "View"]`)

**What Level-1 Does NOT Enrich:**
- ❌ **Edges** — Edge types (e.g., `calls`, `imports`, `extends`) already carry semantic meaning. The type IS the meaning.
- ❌ **Ambiguities** — These represent structural uncertainties during graph building, not data quality issues.

**Rationale:**
| Element | Structural | Semantic (L1) | Why |
|---------|------------|---------------|-----|
| Nodes | `node_type: Class` | `semantic_roles: [DataModel]` | Node type is generic; role is framework-specific |
| Edges | `type: calls` | (not needed) | Edge type already describes the relationship |
| Ambiguities | Unresolved references | (not applicable at L1) | Requires reasoning, not rules |

### Understanding "Ambiguities" in CKG

**What Ambiguity Means:**
Ambiguities are **graph-building uncertainties**, NOT data quality issues. They occur when the builder cannot resolve a reference during static analysis.

**Examples of Ambiguities:**
| Type | Description | Example |
|------|-------------|---------|
| `UNRESOLVED_CALL` | Function call target cannot be determined | `get_user()` — which file? |
| `DYNAMIC_IMPORT` | Import path computed at runtime | `importlib.import_module(name)` |
| `SYMBOLIC_REFERENCE` | Target exists but ID unknown | `config.get(key)` |

**Why Ambiguities Are Valuable:**
- They are honest admissions of "I don't know"
- They preserve builder integrity (no guessing)
- They are candidates for LLM-based resolution in Level-2

### Level-2 Ambiguity Resolution via LLM

**Current State**: 
- The `ambiguities` array in CKG JSON is copied as-is during Level-1 enrichment
- No semantic enrichment is applied to ambiguities


**Future Enhancement**:
Introduce LLM-based ambiguity resolution as part of Level-2 enrichment:

```json
"ambiguities": [
  {
    "source": "app/views.py::login",
    "unresolved_target": "get_user",
    "type": "UNRESOLVED_CALL",
    "llm_resolution": {
      "status": "llm_resolved",
      "probable_target": "app/utils.py::get_user",
      "confidence": 0.85,
      "reasoning": "Based on import context and function signature"
    }
  },
  {
    "source": "app/utils.py::fetch_data",
    "unresolved_target": "dynamic_import",
    "type": "DYNAMIC_IMPORT",
    "llm_resolution": {
      "status": "unresolved",
      "reason": "Dynamic import with runtime-computed path"
    }
  }
]
```

**Status Categories**:
- `llm_resolved`: LLM found probable resolution
- `unresolved`: Cannot determine even with LLM reasoning

**Implementation Notes**:
- Should be part of `llm_enrich_runtime_ast.py`
- Never modify structural data, only add `llm_resolution` metadata
- Confidence threshold configurable (default: 0.7)

---

## Project Root Configuration (`profile.json`)

The `project_root` in `Spashta_2.0/project/profile.json` determines which folder Spashta analyzes.

### Path Resolution
All relative paths are resolved from `SPASHTA_ROOT` (`Spashta_2.0` folder).

### Configuration Values

| Scenario | `project_root` Value | Explanation |
|----------|---------------------|-------------|
| **Production** (Spashta-CKG copied into user's project) | `"../.."` | Goes: `Spashta_2.0` → `Spashta-CKG` → `UserProject` |
| **Testing** (analyzing `_demo` folder) | `"../_demo"` | Goes: `Spashta_2.0` → `Spashta-CKG/_demo` |

### Folder Structure Reference

**Production (user's project):**
```
UserProject/                  ← "../.." from Spashta_2.0
├── manage.py
├── src/
└── Spashta-CKG/
    └── Spashta_2.0/          ← SPASHTA_ROOT
        └── project/
            └── profile.json
```

**Testing (Spashta-CKG standalone):**
```
Spashta-CKG/
├── _demo/                    ← "../_demo" from Spashta_2.0
│   └── app/
│       ├── models.py
│       └── views.py
└── Spashta_2.0/              ← SPASHTA_ROOT
    └── project/
        └── profile.json
```

### Default Value
The default `profile.json` ships with `"../.."` for production use.
For testing `_demo`, manually change to `"../_demo"`.

*Last Updated: 2025-12-29*
