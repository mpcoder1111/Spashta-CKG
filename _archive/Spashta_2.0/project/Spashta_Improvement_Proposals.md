# Spashta 2.0 — Improvement Proposals
**Source:** Learnings from Plan 110 (file-storage feature, Feb 2026)
**Status:** Proposed — not yet implemented

---

## Root Cause Recap (Why These Improvements Are Needed)

During Plan 110, `save_excel_config_view` in `notebook_ai/ui_views.py` was missed
during pre-implementation analysis. It created a `TabularFile` without the new
`file_content` field → runtime crash on first live test.

**Post-mortem showed two overlapping gaps:**

| Gap | Type | Contribution |
|-----|------|-------------|
| Did not run `impact` on the model class `TabularFile` | **Usage gap** | ~40% |
| `ui_views.py` uses lazy imports inside functions — completely invisible to impact at any depth | **Spashta technical gap** | ~60% |

The lazy import issue was confirmed by code inspection:
- `ui_views.py` has zero module-level imports of `core_utils`
- All 8+ usages of `Document` and `TabularFile` are lazy imports inside function bodies
- `build_python_ast.py` emits import edges scoped to the function node, not the file node
- Impact command only surfaces file-level edges → `ui_views.py` never appears in any impact result

**Conclusion:** Even a developer who used Spashta perfectly (running impact on the
model class) would still have missed the bug. This is a Spashta gap, not just a
usage gap.

---

## Improvement Proposals (Priority Order)

---

### IMPROVEMENT 1 — Lazy Import Tracking in AST Builder
**Priority: CRITICAL**
**File to change:** `builders/python/build_python_ast.py`
**Type:** Technical fix to existing capability

**Problem:**
`visit_ImportFrom` and `visit_Import` emit edges using `self.current_scope.scope_id`.
When an import is inside a function body, `current_scope` is the function node
(`ui_views.py::save_excel_config_view`), NOT the file node. The impact command
aggregates at file level and never sees function-scoped import edges.
Result: any file that uses lazy imports for circular-import avoidance (a common
Django pattern) is completely invisible to impact analysis.

**Proposed Fix — Option A (Simpler): Bubble up to file level**
In `visit_ImportFrom` / `visit_Import`, always also emit a file-level import edge
in addition to the scope-level edge:

```python
# In visit_ImportFrom / visit_Import:
# Emit scope-level edge (existing behaviour)
self.ctx.emit_edge("import_from", self.current_scope.scope_id, module_id)

# NEW: If scope is not a File, also emit a file-level edge with a lazy flag
if self.current_scope.scope_id != self.file_id:
    self.ctx.emit_edge("import_lazy", self.file_id, module_id,
                       meta={"scope": self.current_scope.scope_id})
```

**Proposed Fix — Option B (Richer): Tag lazy imports**
Add a `"lazy": true` attribute to edges emitted from non-file scopes.
Impact output can then include a `"lazy_imports"` section alongside `"imports"`.
Agents can see: "this file imports TabularFile lazily inside a function body".

**Why this matters:**
The lazy import pattern is encouraged in Django to avoid circular imports.
Virtually every Django view file that imports from models uses lazy imports.
Fixing this restores the core promise of `impact`: "find everything affected."

---

### IMPROVEMENT 2 — New Command: `consumers`
**Priority: HIGH**
**File to change:** `runtime/query_spashta.py`
**Type:** New command (hybrid graph + grep)

**Problem:**
Graph-based impact tracks import edges. But the real question for model field
changes is: "where does the ORM CREATE or MODIFY instances of this model?"
An import edge does not mean the file creates instances. And a lazy import
means no edge at all.

**Proposed Command:**
```
python query_spashta.py consumers "ModelName" --json
```

**What it does:**
1. Graph step: Run impact on the model class, collect all files that import it
2. Grep step: Search ALL Python files for ORM patterns on the model name:
   - `ModelName.objects.create(`
   - `ModelName.objects.get_or_create(`
   - `ModelName.objects.update(`
   - `ModelName.objects.bulk_create(`
   - `ModelName.objects.get_or_create(`
3. Merge results — union of graph finds + grep finds
4. Classify each result as: View / Service / Admin / Serializer / Test / Command / Other

**Proposed Output:**
```json
{
  "model": "TabularFile",
  "consumers": {
    "views":    ["notebook_ai/ui_views.py::save_excel_config_view (get_or_create, line 601)"],
    "services": ["core_utils/services/tabular_service.py::TabularService::upload_file (create, line 359)"],
    "admin":    ["core_utils/admin.py::TabularFileAdmin"],
    "serializers": ["core_utils/serializers.py::TabularFileSerializer"],
    "tests":    ["core_utils/tests/test_services.py", "..."],
    "other":    []
  },
  "lazy_import_files": ["notebook_ai/ui_views.py"],
  "graph_only_files":  ["core_utils/api_views.py"]
}
```

**Why grep AND graph:**
- Graph catches: structured relationships, transitive imports
- Grep catches: lazy imports, dynamic construction, string-based model usage
- Neither alone is sufficient; union of both is reliable

---

### IMPROVEMENT 3 — Layer Categorization in `impact` Output
**Priority: HIGH**
**File to change:** `runtime/query_spashta.py` (impact command output)
**Type:** Output enhancement

**Problem:**
Current impact output is a flat list of files with depth and relation.
Agent must manually figure out which are views, services, admin, tests.
This costs reasoning tokens and risks human error in categorization.

**Proposed Change:**
After collecting impact results, classify each file by naming pattern:

```python
def classify_file_layer(file_path: str) -> str:
    p = file_path.lower()
    if "test_" in p or "/tests/" in p:        return "test"
    if "admin.py" in p:                        return "admin"
    if "serializer" in p:                      return "serializer"
    if "views.py" in p or "_views" in p:       return "view"
    if "services/" in p or "service.py" in p:  return "service"
    if "management/commands" in p:             return "management_command"
    if "migrations/" in p:                     return "migration"
    if "models.py" in p:                       return "model"
    return "other"
```

**Proposed Output (enhanced impact):**
```json
{
  "File:notebook_ai/ui_views.py": {
    "relation": "imports", "depth": 2, "node_type": "File",
    "layer": "view"
  },
  "File:core_utils/services/tabular_service.py": {
    "relation": "imports", "depth": 2, "node_type": "File",
    "layer": "service"
  }
}
```

**Why it matters:**
An agent scanning impact results can immediately focus on views and services
(high risk for field changes) and deprioritize tests (lower risk).
Reduces cognitive load and scan time by ~40%.

---

### IMPROVEMENT 4 — New Command: `field-impact`
**Priority: HIGH**
**File to change:** `runtime/query_spashta.py`
**Type:** New composite command (orchestrates existing commands)

**Problem:**
"I'm adding a field to a model" is the highest-risk operation in Django development.
Currently requires an agent to manually: run impact on model class, run `consumers`,
check serializers, check migrations. No single command does this.

**Proposed Command:**
```
python query_spashta.py field-impact "models.py::MyModel" --new-field "file_content" --json
```

**What it does (automated pipeline):**
1. Run `impact "models.py::MyModel" --depth 2` → file-level consumers
2. Run `consumers "MyModel"` → ORM create/update call sites (with grep)
3. Search for `MyModel` in `serializers.py` → check field exposure risk
4. Check `migrations/` directory → report next available migration number
5. Combine into a single structured report

**Proposed Output:**
```json
{
  "model": "core_utils/models.py::TabularFile",
  "new_field": "file_content",
  "create_sites": [
    {"file": "notebook_ai/ui_views.py", "method": "save_excel_config_view",
     "line": 601, "call": "get_or_create", "has_field_in_defaults": false,
     "risk": "HIGH — field missing from defaults"},
    {"file": "core_utils/services/tabular_service.py", "method": "upload_file",
     "line": 359, "call": "create", "has_field_in_defaults": true,
     "risk": "OK"}
  ],
  "serializer_exposure": {
    "file": "core_utils/serializers.py",
    "class": "TabularFileSerializer",
    "uses_all": false,
    "field_in_explicit_list": false,
    "risk": "OK — explicit fields list, new field absent"
  },
  "next_migration_number": "0004",
  "layer_coverage": {
    "model": true, "service": true, "view": false,
    "admin": false, "serializer": true, "test": false
  },
  "unchecked_layers": ["view", "admin", "test"]
}
```

**Why it matters:**
This is the single command that would have caught the Plan 110 bug.
`has_field_in_defaults: false` at `save_excel_config_view` is the exact signal needed.

---

### IMPROVEMENT 5 — New Command: `scope-check`
**Priority: MEDIUM**
**File to change:** `runtime/query_spashta.py`
**Type:** New command (self-audit)

**Problem:**
After analysis, an agent has no way to ask: "I analyzed files A, B, C —
what files from my impact results did I NOT examine?"
This is the "what did I miss?" exit check that Spashta currently has no answer for.

**Proposed Command:**
```
python query_spashta.py scope-check "models.py::MyModel" \
    --analyzed "tabular_service.py,document_service.py,ui_views.py" --json
```

**What it does:**
1. Runs impact on the target node
2. Takes the `--analyzed` list
3. Returns: files in impact results NOT in analyzed list (production files only)

**Proposed Output:**
```json
{
  "target": "core_utils/models.py::TabularFile",
  "analyzed": ["core_utils/services/tabular_service.py", "core_utils/services/document_service.py"],
  "unanalyzed_production": [
    "core_utils/admin.py",
    "core_utils/serializers.py",
    "core_utils/api_views.py",
    "notebook_ai/ui_views.py"
  ],
  "coverage_percent": 33,
  "verdict": "INCOMPLETE — 4 production files not analyzed"
}
```

**Why it matters:**
Forces the agent to explicitly handle every consumer before declaring
"ready to implement". Makes coverage gaps visible and measurable, not assumed.

---

### IMPROVEMENT 6 — Stack Coverage Indicator in `impact`
**Priority: MEDIUM**
**File to change:** `runtime/query_spashta.py`
**Type:** Output enhancement (add summary block to impact output)

**Problem:**
An agent running impact sees individual files but no summary of which
architectural layers are represented. It's easy to miss an entire layer
(e.g., all views) without realizing it.

**Proposed Addition:**
Append a `"layer_coverage"` summary to every impact result:

```json
{
  "results": { ... existing impact output ... },
  "layer_coverage": {
    "model":              true,
    "service":            true,
    "view":               false,
    "admin":              true,
    "serializer":         true,
    "management_command": false,
    "test":               true
  },
  "missing_layers": ["view", "management_command"],
  "warning": "No VIEW files in impact results. If this model is used in views via lazy imports, they will not appear here. Run `consumers` command for complete coverage."
}
```

**The warning about lazy imports is key** — it teaches the agent why a layer
might be absent and what to do about it.

---

### IMPROVEMENT 7 — README Close-the-Loop Command
**Priority: LOW**
**File to change:** New script `runtime/close_loop.py`
**Type:** New utility script

**Problem:**
Pre-implementation READMEs declare "READY TO IMPLEMENT" and become stale
the moment the first line of code is written. Post-implementation deviations
(bugs found, scope changes) are added manually. There is no Spashta-native
way to mark an analysis as "implemented with deviations."

**Proposed Command:**
```
python close_loop.py \
    --readme "Spashta_Retrieved_Info/Readme_Feature.md" \
    --status "complete_with_deviation" \
    --deviation "save_excel_config_view: file_content not in defaults (missed, fixed post-impl)"
```

**What it does:**
1. Appends a standardized "IMPLEMENTATION OUTCOME" block to the README
2. Stamps it with date and status
3. Lists predicted vs. actual scope (what was expected, what was actually found)

**Why it matters:**
Institutional memory. Over multiple features, the deviation log becomes a
training set showing which analysis steps most often miss things.
Pattern: "lazy imports in views missed 3 times → Improvement 1 is critical."

---

## Summary Table

| # | Improvement | Type | Where | Priority | Catches Plan 110 Bug? |
|---|------------|------|--------|----------|----------------------|
| 1 | Lazy import tracking | AST builder fix | `build_python_ast.py` | CRITICAL | YES — ui_views.py would appear in impact |
| 2 | `consumers` command | New command | `query_spashta.py` | HIGH | YES — grep finds get_or_create in ui_views.py |
| 3 | Layer classification in `impact` | Output enhancement | `query_spashta.py` | HIGH | PARTIAL — no views in results is visible |
| 4 | `field-impact` command | New composite command | `query_spashta.py` | HIGH | YES — `has_field_in_defaults: false` flagged |
| 5 | `scope-check` command | New command | `query_spashta.py` | MEDIUM | YES — ui_views.py in unanalyzed list |
| 6 | Stack coverage indicator | Output enhancement | `query_spashta.py` | MEDIUM | PARTIAL — warns "view layer absent" |
| 7 | README close-the-loop | New utility | `close_loop.py` | LOW | NO — post-implementation only |

**Minimum viable fix (catches the bug with least effort):** Improvement 2 (grep-based
`consumers` command). No graph changes needed. Pure text search is robust against
lazy imports, dynamic construction, and any future import pattern.

**Complete fix:** Improvement 1 + 2 together. Graph accuracy restored (lazy imports
tracked) AND grep fallback for any remaining dynamic patterns.

---

## Recommended Implementation Order

```
Phase 1 (Quick wins, no graph rebuild needed):
  → Improvement 2: consumers command (grep-based, ~1 day)
  → Improvement 3: layer classification in impact output (~2 hours)
  → Improvement 6: stack coverage indicator + lazy import warning (~2 hours)

Phase 2 (Deeper, requires graph rebuild):
  → Improvement 1: lazy import tracking in AST builder (~1 day + rebuild)
  → Improvement 5: scope-check command (~3 hours)

Phase 3 (Polish):
  → Improvement 4: field-impact composite command (~1 day)
  → Improvement 7: README close-the-loop (~half day)
```

---

## IMPROVEMENT 8 — Spashta MCP Server
**Priority: HIGH (delivers all improvements above in a better interface)**

---

### What "MCP Server" Means Here

The project already runs a **Project Management MCP server** (port 8001, FastAPI,
Bearer auth). Agents call it via bash/curl to create tasks, update status, mark done.
It is an HTTP REST API server — stateful, write operations, stores data in a DB.

Spashta MCP is the **same kind of infrastructure** but opposite in purpose:

| | Project Management MCP | Spashta MCP |
|--|------------------------|-------------|
| Port | 8001 | 8002 |
| Purpose | **WRITE** — create/update tasks | **READ** — query codebase knowledge |
| State | YES — database | NO — in-memory graph |
| Agent access | bash → curl / PowerShell | tool calls (see options below) |
| Auth | Bearer `my-secret-key` | Bearer `spashta-key` |
| Framework | FastAPI | FastAPI |

---

### Two Options for How Agents Access It

#### Option A — HTTP REST (Same Pattern as Project Management MCP)

Agent calls Spashta via bash, same as it calls the project management server today:

```bash
curl http://127.0.0.1:8002/search?q=TabularFile
curl http://127.0.0.1:8002/consumers/TabularFile
curl http://127.0.0.1:8002/field-impact/core_utils%2Fmodels.py::TabularFile
```

**Pros:** Simple to build. Infrastructure pattern already proven in this project.
**Cons:** Agent still needs bash. Still needs to parse JSON. Still needs to remember
endpoints. The 476-line prompt file shrinks but does not disappear.

---

#### Option B — True MCP Protocol Server (Native Tools) ← RECOMMENDED

A **Model Context Protocol** server integrates directly into Claude Code via
`.claude/mcp.json`. Tools appear natively alongside `Read`, `Grep`, `Glob` —
no bash, no curl, no JSON parsing by the agent.

```json
// .claude/mcp.json
{
  "mcpServers": {
    "spashta": {
      "command": "python",
      "args": ["Spashta-CKG/Spashta_2.0/mcp/spashta_mcp_server.py"],
      "env": { "SPASHTA_KEY": "spashta-key" }
    }
  }
}
```

Agent calls look like:
```
spashta_search("TabularFile")
spashta_field_impact("core_utils/models.py::TabularFile", new_field="file_content")
spashta_scope_check("core_utils/models.py::TabularFile", analyzed=["tabular_service.py"])
```

No subprocess. No directory management. No `--json` flag. No output parsing.
Graph loaded once at server start — 24 MB read once instead of on every CLI call.

**Pros:** Agent uses Spashta instinctively like Read/Grep. 476-line prompt file
shrinks to an 80-line cheatsheet. Parallel tool calls possible (search + impact
simultaneously). Compound tools (`consumers`, `field_impact`, `scope_check`) are
first-class and clean.
**Cons:** Slightly more build effort than Option A (MCP protocol vs plain REST).

---

### What Disappears from the Current Prompt File With Option B

| Current 476-line section | With MCP Option B |
|--------------------------|-------------------|
| CLI syntax for every command | Gone — tools have typed parameters |
| `--json` flag reminders | Gone — MCP always returns structured data |
| `cd Spashta-CKG` instructions | Gone — server manages its own path |
| Windows Unicode workaround (10 lines) | Gone — runs server-side |
| TRAP 1: wrong `locate` prefix | Gone — server normalises automatically |
| TRAP 2: dependencies as list of dicts | Gone — named object return |
| TRAP 3: impact output as list not dict | Gone — typed return |
| TRAP 4: Unicode on Windows | Gone |
| TRAP 5: old_code_reference filtering | Gone — always filtered by server |
| TRAP 7: file_path on method nodes | Gone — server auto-populates |
| Section 2 output format table | Gone — tool schemas define this |
| Section 9 gate checklist (manual) | Replaced by `scope_check` tool |
| Working directory instructions | Gone |

**Result: 476 lines → ~80 lines.** Only workflow decisions remain — which tool
for which situation, and the 3 critical rules.

---

### 9 Tools the MCP Server Exposes

| Tool | Purpose | Type |
|------|---------|------|
| `spashta_stats()` | Health check — mandatory first call | Existing (wrapped) |
| `spashta_search(query, type?)` | Discover nodes by keyword | Existing (wrapped) |
| `spashta_locate(node_id)` | Confirm node + line numbers | Existing (wrapped) |
| `spashta_read(node_id)` | Get source code of a node | Existing (wrapped) |
| `spashta_dependencies(node_id)` | List children of a node | Existing (wrapped) |
| `spashta_impact(node_id, depth?)` | Who uses this node — with layer labels | Enhanced |
| `spashta_consumers(model_name)` | ALL ORM create/query sites (graph + grep) | **NEW** |
| `spashta_field_impact(model_node_id)` | Full pre-impl report for field changes | **NEW** |
| `spashta_scope_check(target, analyzed[])` | Coverage self-audit | **NEW** |

The three NEW tools encode the exact workflows that would have caught the Plan 110
bug. `spashta_field_impact` returns `ready_to_implement: false` and
`blocker: "save_excel_config_view: has_field_in_defaults=false"` — the exact
pre-implementation signal that was missing.

---

### Cross-IDE and Cross-Agent Compatibility

A key question: **can the Spashta MCP server be used by agents other than Claude Code
— including custom agents, other IDEs, or future frameworks?**

The answer depends on which option is built.

#### Option A (HTTP REST) — Universal, Works Everywhere

```
Compatible with: EVERYTHING that can make an HTTP request
```

| Agent / Framework | Can use Option A? | How |
|------------------|-------------------|-----|
| Claude Code | Yes | bash → curl / PowerShell |
| Cursor AI | Yes | bash → curl |
| Windsurf (Codeium) | Yes | bash → curl |
| GitHub Copilot Agent | Yes | bash → curl |
| LangChain agent | Yes | `requests.get()` in Python |
| AutoGen agent | Yes | `requests.get()` in Python |
| Google Gemini agent | Yes | `requests.get()` in Python |
| Any custom Python agent | Yes | `requests.get()` in Python |

Option A is framework-agnostic by design. If an agent can run code, it can call
a REST API. No MCP protocol support required.

#### Option B (True MCP Protocol) — Native in MCP-Capable IDEs

MCP is Anthropic's **open protocol** — released publicly, not proprietary.
Adoption is growing fast across the industry.

| IDE / Tool | MCP Support | Status |
|-----------|-------------|--------|
| Claude Code | Native | Full support today |
| Cursor | Native | Full support today |
| Windsurf (Codeium) | Native | Full support today |
| Continue.dev | Native | Full support today |
| Zed | Native | Full support today |
| VS Code (Copilot) | Partial | Growing |
| Google Gemini CLI | Unknown | Not confirmed |
| LangChain / AutoGen | Via adapter | Community wrappers exist |

For IDEs that do not support MCP natively, Option A (the REST layer) serves as
the universal fallback — the same server handles both.

---

### Recommendation — Build Both Layers in One Server

Do not choose between Option A and Option B. Build both in the same server:

```
┌─────────────────────────────────────────────────────┐
│                Spashta MCP Server                   │
│                                                     │
│  Option B layer:  MCP Protocol (stdio / SSE)        │
│  → Claude Code, Cursor, Windsurf, Zed, Continue     │
│    get native tools: spashta_search(), etc.         │
│                                                     │
│  Option A layer:  HTTP REST API (FastAPI, port 8002)│
│  → Any agent / any language / any framework         │
│    calls: GET /search, GET /consumers, etc.         │
│                                                     │
│  Both layers hit the SAME in-memory graph           │
│  Graph loaded ONCE at server start (24 MB)          │
└─────────────────────────────────────────────────────┘
```

One server. Two access layers. MCP-capable IDEs get native tools.
Everything else — custom agents, Google Gemini, LangChain, AutoGen — calls
the REST layer. The compound tools (`consumers`, `field_impact`, `scope_check`)
work identically through both.

**Build order:**
1. Option A first (1–2 days) — universal access, copy project management pattern
2. Add Option B (1–2 days more) — native tools for Claude Code / Cursor / Windsurf

The compound tools are the real value regardless of which layer is used.
Implement `consumers`, `field_impact`, `scope_check` before worrying about
Option A vs B.

**Together with the existing MCP:**
```
Agent workflow (any IDE, any framework):
  1. spashta_field_impact()       → understand full impact before coding
  2. Implement the changes
  3. project_management/tasks     → create/update tasks for tracking
  4. spashta_scope_check()        → verify nothing missed before closing
```

The two MCP servers are complementary: Spashta gives codebase understanding,
project management gives work tracking. Neither alone is sufficient.
Together, any agent — in any IDE — gets both situational awareness and
structured work tracking from the same local infrastructure.
