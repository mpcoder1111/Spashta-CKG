# Spashta-CKG: Micro-Scale Feature Proposals & Agent UX Blueprint (v2 - Final Architecture)
**Date**: 2026-09-01  
**Project**: [Spashta-CKG](https://github.com/mpcoder1111/Spashta-CKG)  
**Document**: Architectural & Micro-Scale Feature Specification (Post-Review Alignment)

---

## 🌟 Executive Summary

Following collaborative review with AI Coding Agents and real-world benchmarking on 260+ file repositories, this document establishes the **definitive, battle-tested specification** for the next Spashta-CKG milestone.

### Key Decisions Agreed:
1. **Universal Envelope Standard**: Strict `status ∈ {"ok", "not_found", "error"}`. Staleness is strictly orthogonal in `_meta.is_stale`.
2. **Explicit Truncation Flag**: Never under-report without an explicit `truncated: true` and `returned_items: N` signal.
3. **`can_delete` Test vs. Production Distinction**: Test-only callers result in `can_delete: true` with `requires_test_updates: [...]`. Production callers result in `can_delete: false`.
4. **Omit Docstrings by Default (Never Truncate)**: Docstrings are omitted by default (`--full` or `include_docstrings: true` to opt-in) to avoid dropping load-bearing warnings.
5. **Config File Strategy (`.spashta.json`)**: Use root `.spashta.json` for tracked reproducible configuration, keeping `.spashta/` purely for gitignored derived caches.
6. **Ambiguity Transparency**: Surface `ambiguous: true` with `alternatives: [...]` when exact-name ties differ only by type tiering.
7. **Transparent Call Graph Boundaries**: Document that on pure Python libraries, static AST coupling is largely import-driven rather than direct call-driven.

---

## 📐 Part 1: The Universal Response Envelope Standard

All CLI commands (`--json`), Python API calls, and native MCP tools will return this **strictly predictable schema**:

```json
{
  "status": "ok",                       // Strictly: "ok" | "not_found" | "error"
  "command": "impact",                  // "impact" | "locate" | "search" | "dead_code" | "dependencies" | "can_delete" | "call_graph"
  "target": {
    "query": "TopologyIndex",
    "resolved_id": "retrieval/context.py::TopologyIndex",
    "node_type": "Class",
    "file_path": "retrieval/context.py",
    "line_start": 45,
    "line_end": 120
  },
  "ambiguous": false,                   // true if exact-name collision was resolved via type weighting
  "alternatives": [],                   // Populated if ambiguous: true
  "summary": {
    "total_items": 6,
    "returned_items": 6,
    "truncated": false,                 // MANDATORY: explicit signal if items array is capped
    "discriminating": true,             // false if all callers share identical parent modules
    "breakdown": {
      "Function": 4,
      "Method": 2
    }
  },
  "items": [
    {
      "id": "retrieval/engine.py::search_pipeline",
      "name": "search_pipeline",
      "node_type": "Function",
      "file_path": "retrieval/engine.py",
      "line_start": 84,
      "relation": "calls",
      "depth": 1
    }
  ],
  "provenance": {
    "files_analyzed": 268,
    "symbols_considered": 945
  },
  "_meta": {
    "version": "3.2.6",
    "graph_built_at": "2026-09-01T07:30:00Z",
    "is_stale": false,
    "staleness_check": "mtime-manifest",
    "stale_files_count": 0,
    "stale_files": []
  }
}
```

---

## 🛡️ Part 2: High-Level Decision Tool — `spashta_can_delete(symbol)`

### The Production vs. Test Blocker Rule
A test caller does NOT block deletion; it marks that deleting the symbol is valid but requires deleting/updating the associated test.

#### Scenario A: Symbol has Production Callers
```json
{
  "status": "ok",
  "can_delete": false,
  "target": {
    "query": "UserModel",
    "resolved_id": "app/models.py::UserModel"
  },
  "blockers": {
    "production": [
      { "file": "app/views.py", "caller": "profile_view", "line": 45, "relation": "calls" }
    ],
    "tests": [
      { "file": "tests/test_models.py", "caller": "test_user_create", "line": 12, "relation": "calls" }
    ]
  },
  "requires_test_updates": []
}
```

#### Scenario B: Symbol has ONLY Test Callers (Valid Deletion with Work Attached)
```json
{
  "status": "ok",
  "can_delete": true,
  "target": {
    "query": "LegacyHelper",
    "resolved_id": "app/utils.py::LegacyHelper"
  },
  "blockers": {
    "production": [],
    "tests": [
      { "file": "tests/test_utils.py", "caller": "test_legacy_helper", "line": 42, "relation": "calls" }
    ]
  },
  "requires_test_updates": [
    "tests/test_utils.py"
  ]
}
```

---

## 🎯 Part 3: Symbol Precedence & Ambiguity Transparency

### Priority Tiering Hierarchy
1. **Tier 1 (Weight 100)**: `Function`, `Method`, `Class`, `Route`, `View`
2. **Tier 2 (Weight 80)**: `Template`, `Stylesheet`, `File`, `Package`, `Module`
3. **Tier 3 (Weight 60)**: `DataModel`, `Form`, `Signal`, `Component`
4. **Tier 4 (Weight 40)**: `Field`, `Variable`, `Parameter`, `Property`
5. **Tier 5 (Weight 20)**: `StyleClass`, `StyleID`, `Keyframes`

### Ambiguity Flagging
When 2 or more nodes match the exact name query and the winner is chosen by type weight:
```json
{
  "status": "ok",
  "ambiguous": true,
  "target": {
    "resolved_id": "retrieval/evidence.py::evidence",
    "node_type": "Function"
  },
  "alternatives": [
    {
      "id": "retrieval/models.py::EvidencePayload::evidence",
      "node_type": "Field",
      "file_path": "retrieval/models.py",
      "line_start": 14
    }
  ]
}
```

---

## 📁 Part 4: Repository Hygiene — `.spashta.json` Strategy

### Why `.spashta.json` at Root Wins Over `.spashta/profile.json`
* `.spashta/` is gitignored because it contains 20+ MB of derived, non-byte-deterministic graph caches.
* Putting `profile.json` inside `.spashta/` causes tracked exclusions to be silently gitignored.
* **Architecture**:
  - `<project_root>/.spashta.json` $\rightarrow$ **Tracked in Git** (clean, single reproducible input dotfile).
  - `<project_root>/.spashta/` $\rightarrow$ **Ignored in Git** (derived graph & mtime caches).
  - Backwards-compatible: fallback to `profile.json` or `.spashta/profile.json` if `.spashta.json` is absent.

---

## 🔬 Part 5: Static AST Reality on Pure Python Libraries

### Why Call Edge Ratios Differ Across Architectures:
1. **Web Frameworks (Django / FastAPI / HTMX)**:
   - Call edges are lower because invocations flow through URL routers, middleware, and template tags. Spashta captures these as `resolves_to`, `uses_model`, and `listens_to`.
2. **Pure Python Libraries / Compilers**:
   - In pure libraries without web layers, coupling predominantly manifests as `imports` and class inheritance (`extends`), alongside dynamic dispatch (`getattr`, plugin registries, polymorphism).
3. **Documentation Commitment**:
   - Spashta will transparently state that its call graph captures **static, deterministic symbol invocations**, while structural coupling (`imports`, `extends`, `contains_function`) provides the true blast radius for refactoring.

---

## 🚦 Part 6: Implementation Sequencing & Status

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        SEQUENCED IMPLEMENTATION ROADMAP & STATUS                       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 1: Universal Response Envelope + Truncation Flag                      [COMPLETE] │
│          • Standardize status, target, summary, items, and _meta across all tools     │
│                                                                                        │
│ Phase 2: Freshness Signal (_meta.is_stale & staleness_check)                [COMPLETE] │
│          • mtime checks over known files manifest in ~1-2ms                            │
│                                                                                        │
│ Phase 3: Composite Decision Tool (spashta_can_delete / can-delete)          [COMPLETE] │
│          • Separate production vs. test blockers + requires_test_updates               │
│                                                                                        │
│ Phase 4: Symbol Type Tiering + Ambiguity Flagging                           [COMPLETE] │
│          • Functions/Classes win tie-breaks; surface alternatives                      │
│                                                                                        │
│ Phase 5: Compact Output by Default                                          [COMPLETE] │
│          • Omit docstrings by default (never truncate); --full opt-in                  │
│                                                                                        │
│ Phase 6: Config Migration to .spashta.json                                  [COMPLETE] │
│          • Root .spashta.json tracked in git, .spashta/ ignored                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🏆 Part 7: Final Release Sign-Off & Verification (v3.2.7)

* **Release Tag**: `v3.2.7`
* **Release Commit**: `6be7c15` (`main` branch)
* **Date Released**: 2026-09-01
* **Dedicated Verification Suite**: `spashta_ckg/builders/python/verify_agent_contract_and_decision_tools.py` (7/7 Agent Contract Groups Passing, 100% Green)
* **Full Repository Regressions**: 18/18 feature & language suites Passing (100% Green)

### Verification Summary Matrix

| Feature Tested | Test Case / Validation | Result |
| :--- | :--- | :--- |
| **Symbol Type Tiering** | `resolve_symbol_node("evidence")` Function vs Field tie-break | ✅ **PASS** (Function selected, `ambiguous: true`, 2 alternatives) |
| **`can_delete` Decision Engine** | Production callers vs Test-only callers vs Zero callers | ✅ **PASS** (`can_delete: false` on prod caller; `can_delete: true` + `requires_test_updates` on test caller) |
| **Universal Response Envelope** | Schema validation across `impact`, `locate`, `search`, `dead_code` | ✅ **PASS** (`status`, `target`, `summary`, `items`, `_meta` verified) |
| **Docstring Compactness** | Omit docstrings in compact mode; retain full docstrings on `--full` | ✅ **PASS** (Docstrings omitted by default, never truncated when requested) |
| **Config Hygiene** | `.spashta.json` priority detection over `profile.json` | ✅ **PASS** (Discovered and parsed active configuration) |
| **CLI & MCP Parity** | `spashta_ckg can-delete --json` and 9 native async MCP tools | ✅ **PASS** (All 9 native MCP tools return structured dictionaries) |
| **Full Regression Suite** | 18 Language Builders, Adapters & Feature Verification Scripts | ✅ **PASS (18/18 Green)** |
