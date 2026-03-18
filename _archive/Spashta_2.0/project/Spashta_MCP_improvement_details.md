# Spashta MCP Server — Detailed Improvement Specification
**Author:** Agent (Claude Sonnet 4.6) — learning from Plan 110 (Feb 2026)
**Purpose:** Specification for converting Spashta CLI into an MCP server with
             compound tools that close the gaps found in live usage.

---

## PART 1: Why MCP Over CLI — The Case

### Current State (CLI)

Every Spashta query today looks like this from an agent's perspective:

```bash
cd Spashta-CKG
python Spashta_2.0/runtime/query_spashta.py impact "core_utils/models.py::TabularFile" --depth 2 --json \
  | python -c "
import json,sys
data=json.load(sys.stdin)
for k,v in data.items():
    if 'old_code' not in k:
        print(f'[depth {v[\"depth\"]}] {v[\"relation\"]:12s} {k}')
"
```

This is 6 lines for one query. The agent must:
- Remember to `cd Spashta-CKG` first
- Remember `--json` flag
- Handle Windows Unicode encoding manually
- Parse the output correctly (impact = dict, dependencies = list of strings, etc.)
- Filter `old_code_reference` nodes manually

And the 24 MB enriched graph is **loaded fresh from disk on every single call**.

### Problems This Creates

| Problem | Real Cost |
|---------|-----------|
| 24 MB re-read from disk per query | Slow. A 10-query analysis session reads 240 MB total |
| Agent must know output format per command | 476-line prompt file exists just for this |
| Sequential CLI calls only | Cannot search + impact in parallel |
| No compound operations | `consumers` = impact + grep = two separate bash scripts |
| Syntax errors fail silently or crash | Wrong `locate` prefix = empty result, not an error |
| Lazy imports invisible to impact | This single gap caused the Plan 110 runtime bug |

### MCP Server — What Changes

```
Agent calls: spashta_impact("core_utils/models.py::TabularFile", depth=2)
Server returns: structured dict with layer labels, lazy import warning, missing_layers list
Graph read: 0 times (already in memory since server start)
```

The agent gets richer output with less effort. The 476-line prompt file shrinks to an
80-line cheatsheet. Compound tools become first-class citizens.

---

## PART 2: Critical Technical Finding (Why Compound Tools Are Not Optional)

### The Plan 110 Bug — Root Cause

During Plan 110 (file-storage feature), `save_excel_config_view` in
`notebook_ai/ui_views.py` was missed during pre-implementation analysis.
It created a `TabularFile` without the new `file_content` field → runtime crash.

**Post-mortem impact query result:**

```bash
python query_spashta.py impact "core_utils/models.py::TabularFile" --depth 2 --json
```

**Production files returned (depth 2, no tests):**
```
[depth 2] imports      File:core_utils/admin.py
[depth 2] imports      File:core_utils/api_views.py
[depth 2] imports      File:core_utils/serializers.py
[depth 2] imports      File:core_utils/services/document_service.py
[depth 2] imports      File:core_utils/services/tabular_service.py
```

`notebook_ai/ui_views.py` — **never appears. At any depth.**

### Why

```python
# notebook_ai/ui_views.py — module-level imports (lines 68-101)
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, HttpResponse
# ... notebook_ai imports only ...
# NO core_utils import at module level

# Inside save_excel_config_view() — line 596-610
from core_utils.models import TabularFile          # LAZY import inside function
from core_utils.services.tabular_service import TabularService
```

`build_python_ast.py` emits import edges scoped to `current_scope`. When inside a
function, `current_scope` is the function node, not the file node. The `impact`
command aggregates at file level → function-scoped edges are invisible.

This is the **Django circular-import avoidance pattern** — common across all
`ui_views.py` files. All 8+ usages of `Document` and `TabularFile` in `ui_views.py`
are lazy imports. The file is structurally invisible to impact analysis.

**Root cause split:**
- 40%: Usage gap — impact was not run on the model class (only on services)
- 60%: Spashta technical gap — lazy imports not surfaced in file-level impact

**Conclusion:** Even perfect Spashta usage would not have caught this.
The `consumers` tool (which uses grep as a fallback) is the fix. It is not optional.

---

## PART 3: MCP Server Architecture

### Overview

```
┌─────────────────────────────────────────────────────┐
│                 Spashta MCP Server                  │
│                                                     │
│  Startup: load 24MB graph once into memory          │
│                                                     │
│  ┌─────────────┐   ┌──────────────────────────┐    │
│  │ Graph Layer  │   │    Grep/Text Layer        │    │
│  │ (in-memory  │   │ (scans raw .py files for  │    │
│  │  CKG JSON)  │   │  ORM patterns at runtime) │    │
│  └─────────────┘   └──────────────────────────┘    │
│                                                     │
│  9 Tools exposed as MCP tool calls                  │
└─────────────────────────────────────────────────────┘
         │
         │  MCP protocol
         ▼
    Agent (Claude / any MCP client)
    calls tools like native functions
    receives structured typed objects
```

### Server Setup (Suggested)

```
File:    Spashta_2.0/mcp/spashta_mcp_server.py
Port:    8002  (8001 = project management MCP, 8002 = Spashta MCP)
Auth:    Bearer token (same pattern as project management server)
Start:   python Spashta_2.0/mcp/spashta_mcp_server.py
Reload:  POST /rebuild  (triggers build_runtime_ast + enrich_runtime_ast + graph reload)
```

### Graph Loading Strategy

```python
class SpashtaMCPServer:
    def __init__(self):
        self.graph = None
        self.graph_loaded_at = None

    def startup(self):
        self.graph = load_enriched_graph()        # 24 MB, loaded ONCE
        self.graph_loaded_at = datetime.now()
        # All 9 tools operate on self.graph in memory
        # No disk reads during query serving
```

---

## PART 4: Tool Specifications (All 9 Tools)

---

### TOOL 1: `spashta_stats`

**Purpose:** Verify the CKG is healthy before any analysis session.
**Mandatory:** YES — must be called first every session.

**Input:** None

**Output:**
```json
{
  "nodes": 15367,
  "edges": 14817,
  "graph_type": "enriched",
  "loaded_at": "2026-02-21T10:30:00Z",
  "health": "OK",
  "warning": null
}
```

**Health logic:**
- `nodes < 1000` → `health: "STALE"`, `warning: "CKG may need rebuild. Run /rebuild endpoint."`
- `nodes >= 1000` → `health: "OK"`

**MCP improvement over CLI:**
CLI returns raw dict. MCP adds `health` and `warning` so agent can act immediately
without computing the threshold itself.

---

### TOOL 2: `spashta_search`

**Purpose:** Discover nodes by keyword. Starting point for any analysis.

**Input:**
```
query:       string  — keyword, filename, class name, method name
type_filter: string? — "File" | "Class" | "Method" | "Function" | null (all)
```

**Output:** List of node objects, old_code already filtered out:
```json
[
  {
    "node_type": "Class",
    "name": "TabularFile",
    "id": "core_utils/models.py::TabularFile",
    "file_path": null,
    "line_start": 140,
    "docstring": "Model representing an uploaded Excel file..."
  }
]
```

**MCP improvement over CLI:**
- `old_code_reference` nodes always filtered — agent never sees stale nodes
- `file_path` auto-populated for Method/Class nodes by parsing `id` (CLI returns null)
- Result capped at 20 nodes with a `truncated: true` flag if more exist

---

### TOOL 3: `spashta_locate`

**Purpose:** Confirm a node exists and get its exact line range and docstring.

**Input:**
```
node_id: string — "File:path/file.py"  OR  "path/file.py::Class::method"
```

**Output:**
```json
{
  "id": "core_utils/models.py::TabularFile",
  "file": "core_utils/models.py",
  "line_start": 140,
  "line_end": 195,
  "docstring": "Model representing an uploaded Excel file...",
  "found": true
}
```

**MCP improvement over CLI:**
- `found: false` (with explanation) instead of empty result on wrong node_id
- No "File:" prefix required — server normalises automatically
- Error message tells you what's wrong: "Did you mean File:path/... ?"

---

### TOOL 4: `spashta_read`

**Purpose:** Get the actual source code of a specific node.

**Input:**
```
node_id: string — "path/file.py::Class::method"  (most specific preferred)
```

**Output:**
```json
{
  "node_id": "core_utils/services/tabular_service.py::TabularService::upload_file",
  "content": "def upload_file(self, uploaded_file, user, description=''):\n    ...",
  "lines": "269-368",
  "mode": "snippet",
  "warning": null
}
```

**MCP improvement over CLI:**
- If node_id points to a full file (24 MB hit), server warns:
  `"warning": "Reading full file (826 lines). Consider using spashta_dependencies first to find the specific method."`
- Windows Unicode handled server-side — no `encode('ascii','replace')` needed

---

### TOOL 5: `spashta_dependencies`

**Purpose:** List all nodes INSIDE a given node (classes in a file, methods in a class).

**Input:**
```
node_id: string — "File:path/file.py"  OR  "path/file.py::ClassName"
```

**Output:** (Always a list of strings — consistent, no dict/list ambiguity)
```json
{
  "node_id": "File:core_utils/models.py",
  "children": [
    "core_utils/models.py::TabularFile",
    "core_utils/models.py::TabularSheet",
    "core_utils/models.py::Document"
  ],
  "count": 3
}
```

**MCP improvement over CLI:**
CLI returns a raw list of strings — agents frequently treat it as list of dicts
(TRAP 2 in the current prompt file). MCP wraps it in a named object with a `children`
key, eliminating the ambiguity entirely. The 476-line prompt file has an entire TRAP
section for this. With MCP: irrelevant.

---

### TOOL 6: `spashta_impact`

**Purpose:** Find all files that depend on (import/use) a given node.
**Mandatory:** Before editing any class or method.

**Input:**
```
node_id: string — "path/file.py::ClassName"  or  "path/file.py::Class::method"
depth:   int?   — default 2, max 4
```

**Output:** (Enhanced — includes layer classification and lazy import warning)
```json
{
  "target": "core_utils/models.py::TabularFile",
  "depth": 2,
  "consumers": {
    "File:core_utils/admin.py":             {"relation": "imports", "depth": 2, "layer": "admin"},
    "File:core_utils/serializers.py":       {"relation": "imports", "depth": 2, "layer": "serializer"},
    "File:core_utils/services/tabular_service.py": {"relation": "imports", "depth": 2, "layer": "service"},
    "File:core_utils/services/document_service.py":{"relation": "imports", "depth": 2, "layer": "service"},
    "File:core_utils/api_views.py":         {"relation": "imports", "depth": 2, "layer": "view"}
  },
  "layer_coverage": {
    "model":              true,
    "service":            true,
    "view":               true,
    "admin":              true,
    "serializer":         true,
    "management_command": false,
    "test":               true
  },
  "missing_layers": ["management_command"],
  "lazy_import_warning": "Impact uses graph edges only. Files that import this node INSIDE function bodies (lazy imports) will NOT appear above. For model changes, also run spashta_consumers() to catch lazy-import consumers.",
  "tests_excluded": true,
  "tests_count": 12
}
```

**MCP improvement over CLI:**
- Layer labels auto-applied (no manual file-name parsing by agent)
- `missing_layers` tells agent which architectural layers have NO results
- `lazy_import_warning` proactively tells agent to run `consumers` if node is a model
- Tests excluded by default (shown as count, retrievable if needed)
- `old_code_reference` always filtered

---

### TOOL 7: `spashta_consumers` ⭐ NEW
**Priority: CRITICAL**

**Purpose:** Find EVERY place in the codebase that creates, queries, or updates
instances of a Django model. Combines graph edges AND grep-based text search.
This is the tool that catches lazy-import consumers that `impact` misses.

**Input:**
```
model_name: string — "TabularFile"  (class name, not node_id)
```

**Internal Logic:**
```
Step 1 — Graph edges:
    Run impact on "*/models.py::ModelName" at depth 3
    Collect all file-level consumers

Step 2 — Grep search (catches lazy imports):
    Search all .py files for:
        "ModelName.objects.create("
        "ModelName.objects.get_or_create("
        "ModelName.objects.update("
        "ModelName.objects.bulk_create("
        "ModelName.objects.filter("
        "ModelName.objects.get("
    Record file path, method name, line number, call type for each match

Step 3 — Merge + classify:
    Union of Step 1 and Step 2 results
    Classify each file by layer (view/service/admin/serializer/test/other)
    For each grep match: flag whether it's in graph edges too (graph_covered)
```

**Output:**
```json
{
  "model": "TabularFile",
  "consumers_by_layer": {
    "view": [
      {
        "file": "notebook_ai/ui_views.py",
        "method": "save_excel_config_view",
        "line": 601,
        "call_type": "get_or_create",
        "graph_covered": false,
        "lazy_import": true,
        "note": "Found via grep only — lazy import inside function body"
      }
    ],
    "service": [
      {
        "file": "core_utils/services/tabular_service.py",
        "method": "upload_file",
        "line": 359,
        "call_type": "create",
        "graph_covered": true,
        "lazy_import": false
      }
    ],
    "admin": [...],
    "serializer": [...],
    "test": [...],
    "other": []
  },
  "total_consumers": 7,
  "lazy_import_consumers": 1,
  "graph_only_files": ["core_utils/api_views.py"],
  "grep_only_files":  ["notebook_ai/ui_views.py"]
}
```

**Why this is the most important tool:**
The Plan 110 bug: `save_excel_config_view` appears in `grep_only_files` with
`lazy_import: true`. The agent sees it immediately. No runtime crash.

---

### TOOL 8: `spashta_field_impact` ⭐ NEW
**Priority: HIGH**

**Purpose:** Complete pre-implementation analysis for adding or removing a field
from a Django model. One tool call replaces a full manual analysis session.

**Input:**
```
model_node_id: string  — "core_utils/models.py::TabularFile"
new_field:     string? — "file_content"  (optional, used for serializer check)
```

**Internal Logic:**
```
1. Run spashta_consumers(model_name)           → all create/update sites
2. For each create site: read the method code,
   check if new_field is in the arguments      → has_field: true/false
3. Search serializers.py for model reference,
   check if new_field in explicit fields list  → exposure_risk check
4. Scan migrations/ for latest number          → next migration number
5. Assemble layer coverage map
```

**Output:**
```json
{
  "model": "core_utils/models.py::TabularFile",
  "new_field": "file_content",
  "create_sites": [
    {
      "file": "notebook_ai/ui_views.py",
      "method": "save_excel_config_view",
      "line": 601,
      "call_type": "get_or_create",
      "has_field_in_defaults": false,
      "risk": "HIGH",
      "action_required": "Add file_content to defaults dict or sync after create"
    },
    {
      "file": "core_utils/services/tabular_service.py",
      "method": "upload_file",
      "line": 359,
      "call_type": "create",
      "has_field_in_defaults": true,
      "risk": "OK",
      "action_required": null
    }
  ],
  "serializer_check": {
    "file": "core_utils/serializers.py",
    "class": "TabularFileSerializer",
    "uses_all_fields": false,
    "field_in_explicit_list": false,
    "risk": "OK — field absent from API serializer"
  },
  "migration": {
    "app": "core_utils",
    "latest_number": "0003",
    "next_number": "0004",
    "suggested_name": "0004_add_file_content_binary_field"
  },
  "layer_coverage": {
    "all_layers_checked": ["view", "service", "admin", "serializer", "test"],
    "layers_with_create_sites": ["view", "service"],
    "layers_with_high_risk": ["view"]
  },
  "summary": {
    "total_create_sites": 2,
    "high_risk_sites": 1,
    "action_required": true,
    "ready_to_implement": false,
    "blocker": "save_excel_config_view: has_field_in_defaults=false"
  }
}
```

**Why `ready_to_implement: false` is the key output:**
This is the exact signal a pre-implementation gate needs. The agent cannot
proceed until all `has_field_in_defaults` are `true` or explicitly documented
as intentional omissions.

---

### TOOL 9: `spashta_scope_check` ⭐ NEW
**Priority: MEDIUM**

**Purpose:** Self-audit coverage. "I analyzed these files — what did I miss?"
Ensures no consumer file is silently skipped before implementation begins.

**Input:**
```
target_node_id: string   — "core_utils/models.py::TabularFile"
analyzed:       string[] — list of files already read/analyzed by the agent
                           e.g. ["core_utils/services/tabular_service.py",
                                 "core_utils/services/document_service.py"]
```

**Internal Logic:**
```
1. Run spashta_consumers(model_name) → all consumers (graph + grep)
2. Filter to production-only (exclude tests, old_code)
3. Compare against analyzed[] list
4. Return: files in consumers but NOT in analyzed[]
5. Coverage = analyzed_count / total_production_consumers * 100
```

**Output:**
```json
{
  "target": "core_utils/models.py::TabularFile",
  "analyzed_count": 2,
  "total_production_consumers": 6,
  "coverage_percent": 33,
  "unanalyzed_production": [
    {"file": "notebook_ai/ui_views.py", "layer": "view",
     "note": "lazy import consumer — grep found, graph missed"},
    {"file": "core_utils/admin.py",     "layer": "admin"},
    {"file": "core_utils/serializers.py","layer": "serializer"},
    {"file": "core_utils/api_views.py", "layer": "view"}
  ],
  "verdict": "INCOMPLETE",
  "gate": "DO NOT IMPLEMENT — 4 production files not analyzed",
  "action": "Analyze or explicitly document each unanalyzed file before proceeding"
}
```

**When `verdict: COMPLETE`:**
```json
{
  "coverage_percent": 100,
  "unanalyzed_production": [],
  "verdict": "COMPLETE",
  "gate": "CLEAR TO IMPLEMENT"
}
```

---

## PART 5: Cheatsheet (Full 1-Page Version)

This replaces the current 476-line `Prompt_to_use_Spashta-CKG.txt`.
With MCP, the syntax/output-format sections are unnecessary.
Only the workflow decisions remain.

```
================================================================================
SPASHTA MCP — AGENT CHEATSHEET  (v1)
================================================================================

SERVER: http://127.0.0.1:8002
Auth:   Bearer <spashta-key>
Graph:  Loaded once at server start (24 MB). No cd, no --json, no parsing.

================================================================================
TOOL QUICK REFERENCE
================================================================================

  TOOL                    PURPOSE                              WHEN TO USE
  ----                    -------                              -----------
  spashta_stats()         Health check                         FIRST. Every session.
  spashta_search()        Find nodes by keyword                Any discovery
  spashta_locate()        Confirm node + get line numbers      After search
  spashta_dependencies()  List children of a node              Before read
  spashta_read()          Get source code of a node            After dependencies
  spashta_impact()        Who uses this node (file level)      Before ANY edit
  spashta_consumers()     All ORM create/query sites [NEW]     Model field changes
  spashta_field_impact()  Full pre-impl report for field [NEW] Adding/removing model fields
  spashta_scope_check()   Coverage self-audit [NEW]            Before implementing

================================================================================
DECISION TREE
================================================================================

  Every session starts with:
      spashta_stats()    [abort if health != OK]

  Finding something?
      spashta_search(keyword)
      → spashta_locate(node_id)           confirm it
      → spashta_dependencies(node_id)     map structure
      → spashta_read(class::method)       read only what you need

  Before editing a class or method?
      spashta_impact(node_id, depth=2)    mandatory, no exceptions
      → for each non-test file: read the relevant method

  Adding / removing a Django model field?
  ┌─────────────────────────────────────────────────────────────────────┐
  │  spashta_field_impact(model_node_id, new_field)                     │
  │                                                                     │
  │  Check output:                                                      │
  │    summary.ready_to_implement == false  → FIX blockers first        │
  │    has_field_in_defaults == false       → that site WILL crash      │
  │    lazy_import_consumers > 0            → grep caught what graph    │
  │                                           missed                    │
  └─────────────────────────────────────────────────────────────────────┘

  Before writing any code?
      spashta_scope_check(target, analyzed_files)
      → gate == "CLEAR TO IMPLEMENT"       → proceed
      → gate == "DO NOT IMPLEMENT"         → read unanalyzed_production first

================================================================================
LAYER LABELS (used in impact, consumers, field_impact output)
================================================================================

  view               ui_views.py, api_views.py, any *_views.py
  service            services/*.py, *_service.py
  admin              admin.py
  serializer         serializers.py
  management_command management/commands/*.py
  test               test_*.py, tests/*.py
  other              anything else

================================================================================
CRITICAL RULES (3 only)
================================================================================

  1. spashta_stats() first. Always. No exceptions.

  2. Model field change → use spashta_field_impact(), NOT spashta_impact() alone.
     impact() misses lazy imports (files that import inside function bodies).
     field_impact() uses grep as fallback — catches what the graph misses.

  3. spashta_scope_check() before implementing.
     gate must be "CLEAR TO IMPLEMENT" or you have blind spots.

================================================================================
LAZY IMPORT WARNING
================================================================================

  Django circular-import avoidance = lazy imports inside function bodies.
  These are NOT in the graph's import edges.
  spashta_impact() WILL NOT return these files.

  Example: notebook_ai/ui_views.py imports TabularFile at line 610
  inside save_excel_config_view(). Impact at any depth returns nothing.
  spashta_consumers() grep step finds it. spashta_field_impact() flags it.

  Rule: For model-level analysis, always use consumers() or field_impact().
        Never rely on impact() alone.

================================================================================
REBUILD GRAPH (after adding new files, classes, or model fields)
================================================================================

  POST http://127.0.0.1:8002/rebuild   (triggers AST build + enrich + graph reload)
  OR manually:
      python Spashta_2.0/runtime/build_runtime_ast.py
      python Spashta_2.0/runtime/enrich_runtime_ast.py
      (then restart server or call /rebuild)

================================================================================
```

---

## PART 6: What Disappears from the Current Prompt File

The current `Prompt_to_use_Spashta-CKG.txt` is 476 lines. With MCP, the following
sections become **completely unnecessary**:

| Current section | Lines | Why removed with MCP |
|----------------|-------|----------------------|
| CLI syntax for every command | ~80 | Tools have typed parameters |
| `--json` flag reminders (everywhere) | ~15 | MCP always returns structured data |
| `cd Spashta-CKG` instructions | ~5 | Server manages its own path |
| Windows Unicode workaround | ~15 | Handled server-side |
| Output format table (Section 2) | ~15 | Tool return schemas define this |
| TRAP 1: wrong locate prefix | ~5 | Server normalises automatically |
| TRAP 2: dependencies as list of dicts | ~8 | MCP wraps in named object |
| TRAP 3: impact as list not dict | ~5 | Eliminated by typed return |
| TRAP 4: Unicode on Windows | ~5 | Gone (server-side) |
| TRAP 5: old_code_reference | ~5 | Always filtered by server |
| TRAP 6: read before dependencies | ~4 | Kept as rule (still valid) |
| TRAP 7: file_path on method nodes | ~6 | Server auto-populates file_path |
| Section 9 gate checklist (manual) | ~30 | Replaced by scope_check tool |
| WORKING DIRECTORY instructions | ~5 | Gone |
| **Total removable** | **~203 lines** | |

**Remaining (still needed):** ~80 lines covering:
- Decision tree (which tool for which situation)
- The 3 critical rules
- Lazy import warning (conceptual, not syntax)
- Rebuild procedure

**Net result:** 476 lines → ~80 lines. An agent reading 80 lines makes no syntax
errors and follows the right workflow by default.

---

## PART 7: Implementation Phases

### Phase 1 — Quick Wins (No graph rebuild needed)
**Estimated effort: 2-3 days**

Build the MCP server wrapping the existing CLI as-is, plus:
- Tool 6 enhanced (layer labels + lazy import warning + missing_layers)
- Tool 5 fix (wrap in named object, eliminate list-of-dicts TRAP 2)
- Tool 3 fix (auto-normalise node_id prefix, `found: false` on miss)
- Tool 7: `spashta_consumers` (grep-only first, graph integration later)

**Value unlocked:** Catches lazy-import consumers via grep. Plan 110 bug preventable.

### Phase 2 — Compound Tools
**Estimated effort: 2-3 days**

- Tool 8: `spashta_field_impact` (orchestrates consumers + serializer check + migration scan)
- Tool 9: `spashta_scope_check` (coverage self-audit)
- POST `/rebuild` endpoint

**Value unlocked:** Full pre-implementation gate automated. Agent can answer
"am I done analyzing?" with a single tool call.

### Phase 3 — Graph Accuracy Fix
**Estimated effort: 1-2 days + graph rebuild**

- Fix `build_python_ast.py` to bubble lazy import edges up to file level
  (Option A: emit additional file-level `import_lazy` edge alongside function-level edge)
- After rebuild: `spashta_impact` itself becomes accurate for lazy imports
- `spashta_consumers` retains grep fallback (belt and braces)

**Value unlocked:** Impact accuracy restored for all Django projects that use
the lazy import pattern (which is most of them).

### Phase 4 — Polish
**Estimated effort: 1 day**

- `spashta_rebuild()` tool (triggers rebuild + hot-reload graph without server restart)
- README close-the-loop: `POST /close-loop` stamps analysis README with outcome

---

## PART 8: Connection to Existing MCP Server

The project already runs a project management MCP server at port 8001.
The Spashta MCP server should follow the **same pattern**:

| Aspect | Project Management MCP | Spashta MCP |
|--------|----------------------|-------------|
| Port | 8001 | 8002 |
| Auth | Bearer `my-secret-key` | Bearer `spashta-key` |
| Framework | FastAPI | FastAPI |
| Start command | `uvicorn ...` | `uvicorn ...` |
| Audit log | `mcp_audit.log` | `spashta_audit.log` |

**Workflow together:**
```
1. Agent calls spashta_field_impact()     → finds all impact sites
2. Agent implements changes
3. Agent calls project_management/tasks   → creates/updates tasks
4. Agent calls spashta_scope_check()      → verifies coverage before PR
```

The two MCP servers together give an agent: codebase understanding (Spashta) +
work tracking (project management). Neither is sufficient alone.

---

## Summary

| Improvement | Type | Phase | Catches Plan 110 bug? |
|-------------|------|-------|----------------------|
| MCP server wrapper (all 9 tools) | Infrastructure | 1 | Partially (better UX) |
| `spashta_consumers` (grep fallback) | New tool | 1 | YES — grep finds ui_views.py |
| Layer labels in impact output | Output enhancement | 1 | Partially |
| `spashta_field_impact` | New compound tool | 2 | YES — flags has_field=false |
| `spashta_scope_check` | New compound tool | 2 | YES — ui_views in unanalyzed |
| Lazy import AST fix | Graph builder fix | 3 | YES — impact now finds ui_views |
| /rebuild endpoint | Operations | 2 | No (operational) |
| README close-the-loop | New utility | 4 | No (post-implementation) |

**Minimum to implement to prevent this class of bug:** Phase 1 + `spashta_consumers`.
**Complete solution:** All 4 phases.
