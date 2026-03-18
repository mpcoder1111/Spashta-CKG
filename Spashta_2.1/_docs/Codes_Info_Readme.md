# Spashta-CKG Code Files Reference

This document defines the Python scripts in the Spashta Architecture - their purpose, location, and usage.

*Last Updated: 2025-12-30*

---

## Core Builders

| File | Location | Purpose | Status |
|------|----------|---------|--------|
| `build_python_ast.py` | `builders/python/` | Extracts AST from Python source files | ✅ ACTIVE |
| `build_html_ast.py` | `builders/html/` | Extracts templates, assets, and HTMX attributes from HTML | ✅ ACTIVE |
| `build_css_ast.py` | `builders/css/` | Extracts selectors (class, id, element) from CSS | ✅ ACTIVE |

**Key Dependencies:**
- `language_mapping.json` (per builder) - Defines how syntax maps to Core schema
- `builder_rules.json` - Global scan exclusions and policies

---

## Runtime Scripts

| File | Location | Purpose | Status |
|------|----------|---------|--------|
| `build_runtime_ast.py` | `runtime/` | Orchestrates all builders, merges outputs | ✅ ACTIVE |
| `enrich_runtime_ast.py` | `runtime/` | Applies L1 semantic enrichment via adapters | ✅ ACTIVE |
| `validate_ast_equivalence.py` | `runtime/` | Ensures enrichment preserves AST structure | ✅ ACTIVE |
| `diff_runtime_ast.py` | `runtime/` | Detects changes between AST versions (for incremental updates) | ✅ ACTIVE |
| `query_spashta.py` | `runtime/` | CLI tool for AI agents to query CKG | ✅ ACTIVE |
| `execution_protocol.json` | `runtime/` | Defines the complete execution workflow for AI agents | ✅ ACTIVE |

---

## LLM Enrichment (Level 2)

| File | Location | Purpose | Status |
|------|----------|---------|--------|
| `llm_enrich_runtime_ast.py` | `runtime/enrichment_through_LLM/` | Helper script for L2 enrichment workflow | ✅ ACTIVE |
| `llm_enrichment_rules.json` | `runtime/enrichment_through_LLM/` | Rules for AI agent enrichment | ✅ ACTIVE |
| `llm_enrichment_prompt.json` | `runtime/enrichment_through_LLM/` | Format and workflow for L2 enrichment | ✅ ACTIVE |
| `Prompt_For_LLM_Enrichment.txt` | `runtime/enrichment_through_LLM/` | Simple prompt to trigger L2 enrichment | ✅ ACTIVE |

**Output:**
- `code_knowledge_graph_enriched_by_Agent.json` - CKG with LLM-added semantic understanding

---

## Validation Scripts

| File | Location | Purpose | Status |
|------|----------|---------|--------|
| `validate_builder_output.py` | `builders/validation/` | Validates builder AST against Core schema | ✅ ACTIVE |
| `validate_adapter_rules.py` | `adapters/validation/` | Validates adapter framework_mapping.json | ✅ ACTIVE |
| `validate_project_profile.py` | `project/validation/` | Validates profile.json configuration | ✅ ACTIVE |

---

## Project Configuration

| File | Location | Purpose | Status |
|------|----------|---------|--------|
| `profile.json` | `project/` | Defines project root, languages, frameworks | ✅ ACTIVE |
| `context_loader.py` | `project/` | Loads active profile context into Python dict | ✅ ACTIVE |

---

## Test Infrastructure

### Builder Tests

| File | Location | Purpose |
|------|----------|---------|
| `run_tests.py` | `builders/tests/` | Unified test runner for all builders |
| `python_dummy.py` | `builders/tests/data/` | Python test fixtures |
| `dummy.html` | `builders/tests/data/` | HTML test fixtures |
| `dummy.css` | `builders/tests/data/` | CSS test fixtures |

### Adapter Tests

| File | Location | Purpose |
|------|----------|---------|
| `run_tests.py` | `adapters/tests/` | Unified test runner for all adapters |
| `adapters/tests/data/django/` | - | Test fixtures for Django patterns |
| `adapters/tests/data/fastapi/` | - | Test fixtures for FastAPI patterns |
| `adapters/tests/data/htmx/` | - | Test fixtures for HTMX patterns |

---

## Execution Flow

```
1. build_runtime_ast.py
   ├── build_python_ast.py
   ├── build_html_ast.py
   └── build_css_ast.py
        ↓
   validate_builder_output.py (validates each fragment)
        ↓
   code_knowledge_graph_ast.json

2. enrich_runtime_ast.py (L1 - Adapters)
   ├── adapters/django/framework_mapping.json
   ├── adapters/fastapi/framework_mapping.json
   └── adapters/htmx/framework_mapping.json
        ↓
   code_knowledge_graph_enriched.json

3. validate_ast_equivalence.py
   └── Confirms structure preserved

4. [Optional] LLM Enrichment (L2 - AI Agent)
   ├── llm_enrich_runtime_ast.py --list-pending
   └── AI Agent reads files and adds business intent
        ↓
   code_knowledge_graph_enriched_by_Agent.json

5. query_spashta.py
   └── AI Agent queries the enriched graph
```

---

## Output Files

| File | Location | Description |
|------|----------|-------------|
| `code_knowledge_graph_ast.json` | `runtime/` | Raw structural AST (no semantics) |
| `code_knowledge_graph_enriched.json` | `runtime/` | L1 enriched (adapter semantics) |
| `code_knowledge_graph_enriched_by_Agent.json` | `runtime/` | L2 enriched (LLM business intent) |
| `diff_report.json` | `runtime/` | Change detection report |

---

## Key Principles

### 1. Builders Are Cameras
> Builders observe and record structure.
> They do NOT interpret meaning or apply semantic rules.

### 2. Adapters Add Meaning
> Adapters apply `framework_mapping.json` to add semantic roles.
> They do NOT modify structure, only add metadata.

### 3. Validators Are Gatekeepers
> Validators ensure schema compliance.
> They do NOT modify data, only report violations.

### 4. Separation of Concerns
```
Builders        → Extract structure (AST)
L1 Enrichment   → Add framework semantics (Adapters)
L2 Enrichment   → Add business intent (LLM)
Validation      → Ensure correctness
Query Tool      → Enable access
```

---

## Usage Rules

1. **Test Isolation**: Test utilities in `tests/` must NEVER be imported by production code.
2. **Schema First**: All builders must reference `nodes.json` and `edges.json` for vocabulary.
3. **No Auto-Fix**: On validation failure, report and halt. Never auto-fix.
4. **Incremental Updates**: Use `diff_runtime_ast.py` to only re-process changed files.
