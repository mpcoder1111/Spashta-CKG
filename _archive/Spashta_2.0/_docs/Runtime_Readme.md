# Spashta-CKG Runtime - Complete Reference

This document consolidates all runtime documentation including execution flow, enrichment, and design rationale.

*Last Updated: 2025-12-30*

---

## Table of Contents

1. [Overview](#1-overview)
2. [Key Architectural Principles](#2-key-architectural-principles)
3. [Enrichment Levels](#3-enrichment-levels)
4. [Execution Flow](#4-execution-flow)
5. [Runtime Scripts](#5-runtime-scripts)
6. [Query Tool](#6-query-tool)
7. [Incremental Processing](#7-incremental-processing)
8. [Error Handling & Semantic Gaps](#8-error-handling--semantic-gaps)
9. [Output Files](#9-output-files)
10. [Freeze Rules](#10-freeze-rules)

---

## 1. Overview

The Spashta runtime is responsible for:
- Orchestrating language builders (Python, HTML, CSS)
- Merging builder outputs into a unified AST
- Applying framework-specific semantic enrichment (L1 - Adapters)
- Supporting LLM-based enrichment (L2 - AI Agent)
- Providing query tools for AI agents
- Validating structural integrity

**Output Artifacts:**

| File | Description |
|------|-------------|
| `code_knowledge_graph_ast.json` | Raw structural graph |
| `code_knowledge_graph_enriched.json` | L1 enriched (adapter semantics) |
| `code_knowledge_graph_enriched_by_Agent.json` | L2 enriched (LLM business intent) |

---

## 2. Key Architectural Principles

> **Runtime must be deterministic, programmatic, and schema-bound.**

Spashta runtime exists to generate a trusted Code Knowledge Graph (CKG). Agents consume and enrich it.

### Core Rules
- ❌ No step may be skipped
- ❌ No step may auto-fix downstream failures
- ❌ Agents never modify L1 runtime files (`code_knowledge_graph_ast.json`, `code_knowledge_graph_enriched.json`)
- ❌ Agents never bypass validation
- ✅ Agents MAY write to L2 enriched file (`code_knowledge_graph_enriched_by_Agent.json`)

---

## 3. Enrichment Levels

### Level 1: Adapter Enrichment (Rule-Based)

| Aspect | Details |
|--------|---------|
| **Implemented By** | Adapters (`framework_mapping.json`) |
| **Characteristics** | Rule-based, cheap, deterministic, schema-validated |
| **Script** | `runtime/enrich_runtime_ast.py` |
| **Output** | `runtime/code_knowledge_graph_enriched.json` |

**Examples:**

| Pattern | Semantic Role |
|---------|---------------|
| Django `models.Model` | DataModel |
| Django `render()` + `request` arg | View |
| FastAPI `@app.get` | View |
| HTMX `hx-get` | HTMXInteraction |

---

### Level 2: LLM Enrichment (AI Agent)

| Aspect | Details |
|--------|---------|
| **Implemented By** | AI Agent (not scripts) |
| **Characteristics** | Context-aware, expensive, requires file reading |
| **Trigger** | `runtime/enrichment_through_LLM/Prompt_For_LLM_Enrichment.txt` |
| **Output** | `runtime/code_knowledge_graph_enriched_by_Agent.json` |

**What L2 Adds:**

| Field | Description |
|-------|-------------|
| `business_intent` | What the code does in business terms |
| `domain_tags` | Domain categories (#payments, #auth, #user-management) |
| `reasoning_notes` | Why the code is structured this way |
| `resolved_ambiguities` | Dynamic calls that static analysis couldn't resolve |

**L2 Workflow:**
1. Run `llm_enrich_runtime_ast.py --list-pending` to see pending files
2. AI Agent reads each file and adds semantic understanding
3. Agent writes enriched nodes back to the L2 CKG file

---

## 4. Execution Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. validate_project_profile.py    │  ← Validate profile.json       │
├─────────────────────────────────────────────────────────────────────┤
│  2. context_loader.py              │  ← Load languages, frameworks  │
├─────────────────────────────────────────────────────────────────────┤
│  3. build_runtime_ast.py           │  ← Run all builders            │
├─────────────────────────────────────────────────────────────────────┤
│  4. enrich_runtime_ast.py          │  ← Apply L1 adapter enrichment │
├─────────────────────────────────────────────────────────────────────┤
│  5. validate_ast_equivalence.py    │  ← Verify structure preserved  │
├─────────────────────────────────────────────────────────────────────┤
│  6. [Optional] diff_runtime_ast.py │  ← Detect changes for L2       │
├─────────────────────────────────────────────────────────────────────┤
│  7. [Optional] LLM Enrichment      │  ← AI Agent adds L2 semantics  │
└─────────────────────────────────────────────────────────────────────┘
```

### Quick Execution (from project root)

```bash
# L1: Build and enrich (adapters)
python Spashta-CKG/Spashta_2.0/runtime/build_runtime_ast.py
python Spashta-CKG/Spashta_2.0/runtime/enrich_runtime_ast.py
python Spashta-CKG/Spashta_2.0/runtime/validate_ast_equivalence.py

# L2: LLM enrichment (AI Agent)
# Provide prompt: runtime/enrichment_through_LLM/Prompt_For_LLM_Enrichment.txt
```

### Automated Execution

For fully automated execution, provide this to your AI Agent:
```
Read and follow: Spashta-CKG/Spashta_2.0/runtime/execution_protocol.json
```

---

## 5. Runtime Scripts

### `build_runtime_ast.py`
**Purpose:** Execute all enabled builders, merge outputs into canonical AST

| Aspect | Details |
|--------|---------|
| **Input** | `profile.json` (languages to run) |
| **Output** | `code_knowledge_graph_ast.json` |
| **Constraints** | ❌ No enrichment, ❌ No adapters |

**What It Does:**
- Runs Python, HTML, CSS builders based on profile
- Normalizes node schema: `id`, `type`, `name`
- Normalizes edge schema: `source`, `target`, `type`
- Emits `file_hash` on File nodes for incremental updates

---

### `enrich_runtime_ast.py`
**Purpose:** Apply Level-1 enrichment using adapters

| Aspect | Details |
|--------|---------|
| **Input** | `code_knowledge_graph_ast.json`, adapter `framework_mapping.json` files |
| **Output** | `code_knowledge_graph_enriched.json` |
| **Constraints** | ❌ No LLM, ❌ No free inference, ❌ No structural mutation |

**What It Does:**
- Reads adapter mappings for each framework in profile
- Applies semantic roles based on detection rules
- Preserves all structural data from AST

---

### `validate_ast_equivalence.py`
**Purpose:** Ensure enrichment did NOT change structure

| Aspect | Details |
|--------|---------|
| **Checks** | Node IDs preserved, Edge topology preserved, Only metadata added |
| **Failure Behavior** | Report and HALT execution |

🛡️ **This is a safety check.** If validation fails, enrichment may have corrupted the graph.

---

### `diff_runtime_ast.py`
**Purpose:** Detect changes between executions (for incremental L2 enrichment)

| Aspect | Details |
|--------|---------|
| **Output** | `diff_report.json` |
| **Used For** | Identifying which files need L2 re-enrichment |

```json
{
  "added": ["file1.py"],
  "modified": ["file2.py"],
  "unchanged": ["file3.py"],
  "removed": ["file4.py"]
}
```

---

## 6. Query Tool

### `query_spashta.py`
**Purpose:** CLI tool for AI agents to query the CKG

**Usage:**
```bash
python Spashta-CKG/Spashta_2.0/runtime/query_spashta.py --help
```

**Available Commands:**

| Command | Description |
|---------|-------------|
| `--list-files` | List all files in the CKG |
| `--list-functions` | List all functions |
| `--list-classes` | List all classes |
| `--find "keyword"` | Search nodes by name |
| `--deps "file.py"` | Show dependencies of a file |
| `--callers "function"` | Show what calls a function |
| `--callees "function"` | Show what a function calls |

**Example:**
```bash
python query_spashta.py --find "UserView" --format json
```

---

## 7. Incremental Processing

### Why Incremental Processing Matters

Incremental logic ensures:
- ⚡ **Performance** - Only re-process changed files
- 🔒 **Stability** - Unchanged files keep their semantic tags
- 🎯 **L2 Efficiency** - Only re-enrich modified files with LLM
- 🤝 **Trust** - Agent decisions are preserved across runs

**How It Works:**
1. Each File node has a `file_hash` (content hash)
2. `diff_runtime_ast.py` compares hashes between runs
3. L2 enrichment only targets `added` or `modified` files

---

## 8. Error Handling & Semantic Gaps

### What The System Handles Safely ✅
| Scenario | Behavior |
|----------|----------|
| File has syntax errors | Builder fails → runtime stops |
| Builder crashes | Runtime halts with error message |
| Adapter rules invalid | Adapter validation fails |
| AST/enriched mismatch | `validate_ast_equivalence.py` catches it |

### Semantic Gaps (Not Errors, But Limitations)

These are valid code patterns that may not be fully captured:

**1. Dynamic Calls**
```python
getattr(self, method_name)()  # Cannot statically resolve
```
→ Logged as ambiguity, not an error

**2. Callback Patterns**
```python
button.on_click(handler)  # handler call not directly visible
```
→ Relationship may be missing from graph

**Principle:**
> Coverage ≠ Correctness ≠ Completeness

Ambiguities are logged and can be resolved by L2 enrichment.

---

## 9. Output Files

| File | Location | Description | Modifiable By |
|------|----------|-------------|---------------|
| `code_knowledge_graph_ast.json` | `runtime/` | Raw structural AST | 🔒 Runtime only |
| `code_knowledge_graph_enriched.json` | `runtime/` | L1 enriched (adapters) | 🔒 Runtime only |
| `code_knowledge_graph_enriched_by_Agent.json` | `runtime/` | L2 enriched (LLM) | ✅ AI Agent |
| `diff_report.json` | `runtime/` | Change detection | 🔒 Runtime only |
| `fragment_*.json` | `runtime/builders_generated_fragments/` | Intermediate outputs | 🔒 Builders only |

---

## 10. Freeze Rules

### 🔒 NEVER TOUCH (Frozen)
- `core/software_schema/*` - Universal laws
- `runtime/code_knowledge_graph_ast.json` - Generated
- `runtime/code_knowledge_graph_enriched.json` - Generated

### ✅ Agent May Modify
- `runtime/code_knowledge_graph_enriched_by_Agent.json` - L2 output
- `runtime/enrichment_through_LLM/LLM_working_files/*` - Temporary files
- `project/profile.json` - With user confirmation

### ⚠️ Modify With Caution
- `builders/*` - Affects all future builds
- `adapters/*` - Affects semantic mapping

---

## Summary

Spashta Runtime provides:
- ✅ Deterministic AST generation
- ✅ Rule-based L1 enrichment (cheap, fast)
- ✅ LLM-based L2 enrichment (deep, optional)
- ✅ Incremental processing for efficiency
- ✅ Query tools for AI agent access
- ✅ Clear boundaries between runtime and agent

**This is developer-grade cognitive infrastructure for AI-assisted coding.**
