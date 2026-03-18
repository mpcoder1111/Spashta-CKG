# LLM Enrichment Procedure for Spashta-CKG

## Intent

This document describes **Level-2 LLM Semantic Enrichment** — the process of adding business meaning to the Code Knowledge Graph using an IDE Agent (LLM).

### Why Level-2 Enrichment?

| Level | Performed By | What It Answers |
|-------|--------------|-----------------|
| **Level-1** | Adapters (rule-based) | "What framework pattern is this?" |
| **Level-2** | LLM (this process) | "What is the business purpose?" |

Level-1 is deterministic and repeatable.  
Level-2 captures meaning that requires understanding context.

---

## Folder Structure

```
runtime/
├── code_knowledge_graph_ast.json               # L0: Raw structure (Builders)
├── code_knowledge_graph_enriched.json          # L1: Semantic (Adapters)
├── code_knowledge_graph_enriched_by_Agent.json # L2: LLM Enriched (Output)
│
└── enrichment_through_LLM/                     # LLM Enrichment Module
    ├── Prompt_For_LLM_Enrichment.txt           # TRIGGER: Start here
    ├── llm_enrichment_rules.json               # Rules for Agent
    ├── llm_enrichment_prompt.json              # Format Template
    ├── llm_enrich_runtime_ast.py               # Helper Script
    ├── LLM_Enrichment_Procedure.md             # This Documentation
    │
    └── LLM_working_files/                      # Intermediate files
        ├── files_to_enrich.json                # Pending files list
        └── enrichment_stats.json               # Statistics
```

---

## Files in This Module

| File | Purpose | Used By |
|------|---------|---------|
| `Prompt_For_LLM_Enrichment.txt` | **TRIGGER**: Entry point to start | User shows to Agent |
| `llm_enrichment_rules.json` | Rules, constraints, workflow | Agent reads |
| `llm_enrichment_prompt.json` | Input/Output format examples | Agent reads |
| `llm_enrich_runtime_ast.py` | Helper: list-pending, validate, stats | Agent runs |
| `LLM_working_files/` | Intermediate files folder | Script & Agent |

---

## What Gets Enriched?

| Element | Enriched? | Output Key |
|---------|-----------|------------|
| **Nodes** | ✅ Yes | `llm_enrichment` |
| **Edges** | ❌ No | Edge types are already semantic |
| **Ambiguities** | ✅ Yes | `llm_resolution` |

---

## How to Start LLM Enrichment

### Step 1: User Opens Trigger File

User opens or shows to Agent:
```
runtime/enrichment_through_LLM/Prompt_For_LLM_Enrichment.txt
```

### Step 2: Agent Runs Script to Get Pending Files

```bash
python runtime/enrichment_through_LLM/llm_enrich_runtime_ast.py --list-pending
```

This compares file hashes and outputs:
```
LLM_working_files/files_to_enrich.json
```

### Step 3: Agent Reads JSONs and Processes Files

Agent reads rules, format, and processes only pending files.

---

## Phase 1: LLM Annotation

### Approach: Incremental, File-by-File

The enrichment uses **hash comparison** to only process files that:
- Are new (not in previous enrichment)
- Have changed (hash mismatch)
- Were not enriched before

**Why incremental?**
- Token efficiency: Skip unchanged files
- Cost control: Only pay for what changed
- Preserves previous work

### Helper Script Commands

| Command | What It Does | Output |
|---------|--------------|--------|
| `--list-pending` | Compare hashes, list files needing work | `files_to_enrich.json` |
| `--stats` | Show enrichment progress | `enrichment_stats.json` |
| `--validate` | Check output is valid | Prints errors/warnings |
| `--mode full` | Force full enrichment (ignore hashes) | — |

---

### Full Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ TRIGGER                                                         │
│                                                                 │
│ User shows: Prompt_For_LLM_Enrichment.txt                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Agent runs script to get pending files                  │
│                                                                 │
│ Command: python llm_enrich_runtime_ast.py --list-pending        │
│ Output: LLM_working_files/files_to_enrich.json                  │
│                                                                 │
│ Script compares:                                                │
│   • Current hash (from L1 graph)                                │
│   • Enriched-at hash (from L2 graph, if exists)                 │
│   • Outputs list of files with reason (new/changed/not_enriched)│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Agent reads files and rules                             │
│                                                                 │
│ Files:                                                          │
│   • LLM_working_files/files_to_enrich.json (pending list)       │
│   • llm_enrichment_rules.json (constraints)                     │
│   • llm_enrichment_prompt.json (format)                         │
│   • runtime/code_knowledge_graph_enriched.json (source graph)   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ LOOP: For Each File in Pending List                             │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Step 3a: Read Source Code                                   │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Step 3b: Gather Nodes/Edges/Ambiguities for this file       │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Step 3c: Add llm_enrichment to each node                    │ │
│ │          Include: enriched_at_hash = current file hash      │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Step 3d: Add llm_resolution to ambiguities                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ [Repeat for next file in pending list]                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ FINALIZE                                                        │
│                                                                 │
│ Step 4: Write Output Graph                                      │
│         File: runtime/code_knowledge_graph_enriched_by_Agent.json│
│                                                                 │
│ Step 5: (Optional) Validate                                     │
│         Command: python llm_enrich_runtime_ast.py --validate    │
└─────────────────────────────────────────────────────────────────┘
```

---

### Important: enriched_at_hash

When adding `llm_enrichment` to a node, Agent MUST include:
```json
"llm_enrichment": {
  "intent": "...",
  "summary": "...",
  "enriched_at_hash": "<current_file_hash>",  // REQUIRED for incremental
  "enriched_at": "<timestamp>"
}
```

This enables future runs to skip unchanged files.

---

## Phase 2: Edge Promotion (Future)

### Purpose
Convert resolved ambiguities into real edges in the graph.

### Script (To Be Created)
`promote_resolved_ambiguities.py` — Programmatic, no LLM involved.

---

## Quick Reference

### How to Start
Open: `Prompt_For_LLM_Enrichment.txt`

### First Command (Agent Runs)
```bash
python runtime/enrichment_through_LLM/llm_enrich_runtime_ast.py --list-pending
```

### Files Agent Reads
1. `LLM_working_files/files_to_enrich.json` — Pending list
2. `llm_enrichment_rules.json` — Rules
3. `llm_enrichment_prompt.json` — Format

### Output File
```
runtime/code_knowledge_graph_enriched_by_Agent.json
```

---

## Summary

| Phase | Who | What | Trigger |
|-------|-----|------|---------|
| **Phase 1** | Script + Agent | List pending → Enrich | `Prompt_For_LLM_Enrichment.txt` |
| **Phase 2** | Script | Promote resolved ambiguities | Developer runs script |

---

*Last Updated: 2025-12-29*
