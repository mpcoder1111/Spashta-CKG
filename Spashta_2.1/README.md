# Spashta-CKG 2.1 — Deeper Awareness, Fewer Blind Spots
## Targeted improvements to enrichment, edge resolution, and framework coverage

**Last updated:** 2026-03-18
**Base:** Copy of Spashta 2.0 (architecture unchanged — improvements are additive)

---

## Index

| # | Section | Summary |
|---|---------|---------|
| 0 | [What Changed from 2.0](#what-changed-from-20) | **Start here** — summary of all 2.1 improvements |
| 1 | [Current State Audit](#-current-state-audit) | Hard numbers: orphans, roles, edges, blind spots |
| 2 | [Problem Analysis](#-problem-analysis) | Why 2.0 has orphans and sparse enrichment |
| 3 | [Improvement Plan](#-improvement-plan) | Prioritized fixes with expected impact |
| 4 | [Django Adapter Expansion](#-django-adapter-expansion) | New semantic roles to detect |
| 5 | [Python Builder Improvements](#-python-builder-improvements) | Better call resolution, migration parsing |
| 6 | [New Builders](#-new-builders) | SQL/migration awareness, JS builder |
| 7 | [Enrichment Pipeline Fixes](#-enrichment-pipeline-fixes) | Why only 100/17K nodes got roles |
| 8 | [Orphan Reduction Strategy](#-orphan-reduction-strategy) | Connect the 2,058 disconnected nodes |
| 9 | [New Query Commands](#-new-query-commands-from-future_improvements_planned) | `consumers`, `field-impact`, `scope-check`, layer labels, error messages |
| 10 | [Lazy Import Tracking](#-lazy-import-tracking-critical-builder-fix) | Django lazy imports invisible to impact — critical fix |
| 11 | [MCP Server Architecture](#-mcp-server-architecture-future-infrastructure) | Replace CLI with native MCP tools |
| 12 | [Windows Unicode Handling](#-windows-unicode-handling) | Server-side encoding fix |
| 13 | [Implementation Order](#-implementation-order) | 12-phase plan with effort estimates |
| 14 | [Version History](#-version-history) | Changelog |

---

## What Changed from 2.0

> **Spashta 2.1 does NOT change the architecture.** Same 5 layers (Core → Builders → Adapters → Runtime → Project). All improvements are within existing layers — better rules, more edge types, smarter resolution.

### Summary

| Area | 2.0 State | 2.1 Target |
|---|---|---|
| Semantic roles applied | 100/17,432 nodes (0.6%) | 3,000+ nodes (~17%) |
| Orphan nodes (no edges) | 2,058 (11.8%) | <500 (<3%) |
| Django adapter rules | 9 mappings | 25+ mappings |
| `calls` edges | 702 (4% of edges) | 2,000+ with better resolution |
| Migration/DB awareness | None | Field types, FK relationships parsed |
| Python `self.method()` resolution | Unresolved (logged as ambiguity) | Resolved within same class |
| Lazy imports (function-scoped) | Invisible to `impact` | Tracked via `import_lazy` edge type |
| Management commands | Not detected | Detected as `ManagementCommand` role |
| Template tags / filters | Not detected | Detected as `TemplateTag` role |
| New query commands | 0 | 3 (`consumers`, `field-impact`, `scope-check`) |
| Layer labels in `impact` | Not present | Auto-classified (view/service/admin/model/test) |
| Error messages | Generic "not found" | Suggestions + metadata + query help |
| MCP Server | CLI only | Optional MCP server (graph loaded once) |

---

## 📊 Current State Audit

### Spashta 2.0 — Hard Numbers

```
Total nodes:       17,432
Total edges:       17,034
Connected nodes:   15,374 (88.2%)
Orphan nodes:       2,058 (11.8%) — no edges at all
Semantic roles:       100 (0.6%) — all just "Component"
```

### Node Types

| Type | Count | % of total |
|---|---|---|
| Variable | 12,017 | 68.9% |
| Method | 1,871 | 10.7% |
| Function | 1,070 | 6.1% |
| Class | 785 | 4.5% |
| File | 538 | 3.1% |
| StyleClass | 426 | 2.4% |
| StyleElement | 356 | 2.0% |
| Route | 153 | 0.9% |
| Template | 100 | 0.6% |
| StaticAsset | 64 | 0.4% |
| Others | 52 | 0.3% |

### Edge Types

| Type | Count | What it captures |
|---|---|---|
| `writes_to` | 8,192 | Variable assignments |
| `contains_member` | 3,694 | Class → method/attribute |
| `defines` | 2,590 | File → function/class |
| `imports` | 1,500 | File → file imports |
| `calls` | 702 | Function → function calls |
| `calls_api` | 138 | HTMX/API endpoint calls |
| `links_static_asset` | 64 | Template → CSS/JS |
| `decorates` | 52 | Decorator → function |
| `extends` | 50 | Class inheritance |
| `targets_element` | 30 | CSS → HTML element |
| `submits_form` | 19 | Form → endpoint |
| `triggers_event` | 3 | Event triggers |

### Orphan Breakdown

| Type | Orphan count | Reason |
|---|---|---|
| Variable | 1,958 | Variables without assignment or usage edges |
| File | 61 | Empty `__init__.py`, config files, `.gitkeep` |
| Template | 36 | Unreferenced HTML templates |
| Class | 3 | Unused/test classes |

### Django Adapter — Currently Detects

| Role | Core Node | Count matched | Note |
|---|---|---|---|
| DataModel | Class | ~50 | Only matches `models.Model` inheritance |
| View | Function/Class | ~30 | Matches by arg `request` + file path `views` |
| Route | Call | ~20 | Matches `path()`, `re_path()` |
| Form | Class | ~5 | Matches `forms.Form` inheritance |
| Serializer | Class | ~10 | Matches DRF serializers |
| Admin | Class | ~5 | Matches `admin.ModelAdmin` |
| Middleware | Class | 0 | Rule exists but no matches |
| Signal | Function | 0 | Rule exists but no matches |
| **Total** | | **~100** | **Only "Component" role actually applied** |

**Root cause:** The enrichment script applies "Component" as a catch-all. The specific roles (DataModel, View, etc.) are defined in the mapping but the enrichment engine's detection logic doesn't fully implement all detection rule types (`inheritance_includes`, `used_in_calls`, `file_path_contains` combinations).

---

## 🔍 Problem Analysis

### Why only 100/17K nodes got semantic roles

The enrichment pipeline (`enrich_runtime_ast.py`) supports detection rules but:

1. **`inheritance_includes` requires `extends` edges** — only 50 `extends` edges exist. Many Django classes inherit from framework bases but the builder doesn't always capture the full MRO chain.

2. **`used_in_calls` requires `calls` edges** — only 702 `calls` edges. Most function-to-function calls go unresolved because:
   - `self.method()` calls not resolved (Python builder doesn't trace `self` to class)
   - `service.do_something()` calls not resolved (variable type unknown)
   - String-based references (`'notebook_ai:chat'`) not resolved

3. **`file_path_contains` is too strict** — matches exact substring. `"views"` matches `views.py` but not `ui_views.py` or `api_views.py`.

4. **`arg_names_include` not implemented** — the Python builder extracts `signature.args` but the enrichment engine doesn't check arg names.

### Why 2,058 orphan nodes

| Orphan type | Root cause |
|---|---|
| Variables (1,958) | Builder creates Variable nodes for every assignment but doesn't always create edges to where they're used |
| Files (61) | Empty files, `__init__.py` with no imports, config files that aren't imported by anything |
| Templates (36) | HTML files loaded dynamically via string (`render(request, 'app/template.html')`) — builder doesn't resolve string-based template references |
| Classes (3) | Unused or test-only classes |

### What's completely invisible

| Blind spot | Why | Impact |
|---|---|---|
| **Database schema** | No SQL/migration parser | Can't answer "what fields does this model have?" or "what FKs exist?" |
| **Django ORM queries** | `Model.objects.filter()` not captured as edges | Can't answer "which views query this model?" |
| **Management commands** | Not detected as a semantic role | Can't answer "what management commands exist?" |
| **Template tags** | Custom `@register.filter` not detected | Can't answer "what template tags are available?" |
| **Celery tasks** | `@shared_task` not detected | Can't answer "what async tasks exist?" |
| **Signals** | `@receiver` connections not captured | Can't answer "what signals trigger what?" |
| **Admin classes** | Detected but actions/inlines invisible | Can't answer "what admin customizations exist?" |
| **Fixtures/factories** | Not distinguished from regular code | Test fixtures mixed with production code |
| **Settings constants** | `settings.py` variables not typed | Can't answer "what settings affect this feature?" |

---

## 🛠️ Improvement Plan

### Priority 1 — Fix Enrichment Engine (biggest ROI, no builder changes)

| # | Fix | Expected impact | Files to change |
|---|---|---|---|
| 1.1 | Implement `file_path_contains` with glob patterns (not just substring) | Views in `ui_views.py`, `api_views.py` detected | `enrich_runtime_ast.py` |
| 1.2 | Implement `arg_names_include` detection (read `signature.args` from nodes) | Function-based views detected by `request` arg | `enrich_runtime_ast.py` |
| 1.3 | Fix "Component" catch-all — apply specific roles (DataModel, View, etc.) instead | 100 "Component" → proper roles | `enrich_runtime_ast.py` |
| 1.4 | Add class name pattern matching (`*Admin`, `*Serializer`, `*Form`) as fallback | Detect by naming convention when inheritance unknown | `enrich_runtime_ast.py` |

### Priority 2 — Expand Django Adapter (new roles)

| # | New role | Detection rule | Expected matches |
|---|---|---|---|
| 2.1 | `ManagementCommand` | Class extends `BaseCommand` OR file in `management/commands/` | ~10 |
| 2.2 | `TemplateTag` | Function decorated with `@register.filter` / `@register.simple_tag` | ~5 |
| 2.3 | `TestCase` | Class extends `TestCase` / `TransactionTestCase` OR file in `tests/` | ~50 |
| 2.4 | `Migration` | File in `migrations/` directory | ~40 files |
| 2.5 | `AppConfig` | Class extends `AppConfig` | ~8 |
| 2.6 | `URLConf` | File named `urls.py` or `ui_urls.py` | ~10 |
| 2.7 | `Service` | Class/function in `services/` directory | ~30 |
| 2.8 | `Adapter` | File in `adapters/` directory | ~10 |
| 2.9 | `CeleryTask` | Function decorated with `@shared_task` / `@app.task` | ~0 (future) |
| 2.10 | `ContextProcessor` | Function in file matching `context_processors` | ~2 |
| 2.11 | `Singleton` | Class with `load()` classmethod pattern (Django solo-style) | ~5 |
| 2.12 | `APIEndpoint` | Function/class in file matching `api_views` / `api.py` | ~15 |
| 2.13 | `Fixture` | File in `fixtures/` directory | ~0 (future) |
| 2.14 | `Mixin` | Class name ending with `Mixin` | ~5 |
| 2.15 | `Manager` | Class extending `models.Manager` or name ending `Manager` | ~3 |
| 2.16 | `Permission` | Class/function dealing with permission logic | ~5 |

### Priority 3 — Python Builder Improvements (better edges)

| # | Improvement | Expected new edges | Files to change |
|---|---|---|---|
| 3.1 | Resolve `self.method()` calls within same class | +500 `calls` edges | `builders/python/build_ast.py` |
| 3.2 | Resolve `super().method()` calls to parent class | +50 `calls` edges | `builders/python/build_ast.py` |
| 3.3 | Resolve string-based template references in `render()` | +100 `renders` edges | `builders/python/build_ast.py` |
| 3.4 | Extract Django model field definitions as edges | +300 `has_field` edges | `builders/python/build_ast.py` |
| 3.5 | Extract ForeignKey/OneToOne relationships | +50 `fk_to` edges | `builders/python/build_ast.py` |
| 3.6 | Extract `@receiver(signal)` connections | +10 `listens_to` edges | `builders/python/build_ast.py` |

### Priority 4 — New Edge Types (Core schema extension)

| Edge type | Source | Target | Purpose |
|---|---|---|---|
| `has_field` | Class (Model) | Variable (field) | "User model has email field" |
| `fk_to` | Class (Model) | Class (Model) | "Order FK → User" |
| `renders` | Function (View) | Template | "login_view renders login.html" |
| `listens_to` | Function | Signal | "on_user_save listens to post_save" |
| `configures` | Class (Admin) | Class (Model) | "UserAdmin configures User model" |

### Priority 5 — Orphan Reduction

| Strategy | Target orphans | Expected reduction |
|---|---|---|
| Connect Variables to their defining File via `defined_in` edge | 1,958 Variable orphans | -1,500 (variables in files that have File nodes) |
| Connect Template orphans via string-based `render()` resolution | 36 Template orphans | -30 |
| Remove empty `__init__.py` nodes that add no value | 61 File orphans | -40 |
| Connect Classes to their File via `defines` edge (backfill) | 3 Class orphans | -3 |

---

## 🏗️ Django Adapter Expansion

### Current 9 Roles → Target 25+ Roles

```
2.0 (current):                      2.1 (target):
├── DataModel                       ├── DataModel
├── View (function)                 ├── View (function)
├── View (class)                    ├── View (class)
├── Route                           ├── Route
├── Form                            ├── Form
├── Serializer                      ├── Serializer
├── Admin                           ├── Admin
├── Middleware                       ├── Middleware
└── Signal                          ├── Signal
                                    ├── ManagementCommand      ← NEW
                                    ├── TemplateTag            ← NEW
                                    ├── TestCase               ← NEW
                                    ├── Migration              ← NEW
                                    ├── AppConfig              ← NEW
                                    ├── URLConf                ← NEW
                                    ├── Service                ← NEW
                                    ├── Adapter                ← NEW
                                    ├── Singleton              ← NEW
                                    ├── APIEndpoint            ← NEW
                                    ├── Mixin                  ← NEW
                                    ├── Manager                ← NEW
                                    └── Permission             ← NEW
```

### Detection Strategy

For each new role, detection uses a **waterfall** (first match wins):

```
1. Inheritance check   → extends known base class? (strongest signal)
2. Decorator check     → has known decorator? (strong signal)
3. File path check     → in expected directory? (medium signal)
4. Name pattern check  → name matches *Admin, *Service, etc.? (weak signal, fallback only)
```

This is the same pattern 2.0 uses, but 2.1 adds steps 3 and 4 which are currently not implemented in the enrichment engine.

---

## 🔧 Python Builder Improvements

### Self-method Resolution (Priority 3.1)

Current state: `self.save()` inside a method creates NO edge — the builder doesn't know what class `self` refers to.

Fix: When inside a class method, resolve `self.X()` to `ClassName.X`:

```
Before:  Method "save_config" calls "self.validate()" → ambiguity logged, no edge
After:   Method "save_config" calls "WorkspaceConfig.validate()" → calls edge created
```

### String-based Template Resolution (Priority 3.3)

Current state: `render(request, 'notebook_ai/notebook_detail.html')` creates NO edge to the template.

Fix: Extract string literals in `render()` calls, match to Template nodes:

```
Before:  View function → (nothing) → Template exists as orphan
After:   View function → renders → Template node
```

### Django Model Field Extraction (Priority 3.4)

Current state: `name = models.CharField(max_length=100)` is just a Variable node.

Fix: Detect `models.*Field()` patterns, create typed edges:

```
Before:  Class "User" contains_member Variable "name"
After:   Class "User" has_field Variable "name" (type: CharField, max_length: 100)
         Class "User" fk_to Class "Group" (via: ForeignKey)
```

---

## 📉 Orphan Reduction Strategy

### Phase 1: Variable Orphans (1,958 → ~400)

Most Variable orphans are module-level constants (`logger = logging.getLogger(...)`) or config values. They exist in files that ARE in the graph — the `defines` edge just wasn't created for them.

**Fix:** In Python builder, emit `defines` edge for ALL top-level assignments, not just functions/classes.

### Phase 2: Template Orphans (36 → ~5)

Templates are loaded via string `render(request, 'path/to/template.html')`. The string isn't resolved.

**Fix:** In Python builder, extract string arguments from `render()`, `get_template()`, `template_name =` assignments. Match to Template nodes.

### Phase 3: File Orphans (61 → ~10)

Empty `__init__.py` files and config files with no imports.

**Fix:** Option A: Remove them from graph (they add noise). Option B: Create `part_of` edge to parent package.

---

## 🔎 New Query Commands (from Future_Improvements_Planned)

These were proposed in `IMPROVEMENT_ROADMAP.md`, `Spashta_Improvement_Proposals.md`, and `Spashta_MCP_improvement_details.md`. Prioritized by impact.

### Critical — Pre-Implementation Safety Gates

#### `consumers` command (graph + grep hybrid)

The `impact` command only follows edges in the graph. But Django uses **lazy imports** (imports inside function bodies) which the Python builder doesn't capture as file-level edges. The `consumers` command fills this gap:

```bash
python query_spashta.py consumers "TabularFile" --json
```

**How it works:**
1. Graph step — run `impact` on the node, collect all importing files
2. Grep step — search all `.py` files for ORM patterns: `.objects.create(`, `.filter(`, `.get(`, `get_or_create(`
3. Merge + classify by layer (view/service/admin/serializer/test/management)
4. Return files found by graph_only, grep_only, or both

**Why critical:** Catches lazy imports that `impact` misses entirely. In a real Django project, 35%+ of model consumers use lazy imports in views.

#### `field-impact` command (composite pre-implementation gate)

One command replaces an entire manual analysis session:

```bash
python query_spashta.py field-impact "models.py::TabularFile" --new-field "file_content" --json
```

**What it does:**
1. Run `impact` on model class
2. Run `consumers` (catches lazy imports)
3. Scan serializers for model reference + field exposure risk
4. Check migrations for next available number
5. Return `ready_to_implement: true/false` with blockers listed

#### `scope-check` command (coverage self-audit)

```bash
python query_spashta.py scope-check "models.py::TabularFile" \
    --analyzed "tabular_service.py,document_service.py" --json
```

**Returns:** Files in impact results NOT in the `--analyzed` list. Coverage percentage and verdict: `COMPLETE` or `INCOMPLETE`.

### High — Enriched Output

#### Layer categorization in `impact` output

Every impact result gets a `"layer"` field:

```json
{
  "file": "notebook_ai/ui_views.py",
  "layer": "view",
  "depth": 1
}
```

Plus summary: `"layer_coverage": {"view": true, "service": true, "admin": false}` with `"missing_layers"` warning.

#### Better error messages with suggestions

```json
{
  "error": "Node not found",
  "searched_for": "rag_toolkit/extractors/markdown.py",
  "suggestion": "Try: search 'MarkdownExtractor'"
}
```

#### Query help system

```bash
python query_spashta.py query-help search
# Returns: syntax, supported patterns, examples, flags
```

#### Result metadata on every query

```json
{
  "results": [...],
  "metadata": {
    "total_matches": 47,
    "query_time_ms": 234,
    "searched_in": 14874
  }
}
```

---

## 🖥️ Lazy Import Tracking (Critical Builder Fix)

Django projects heavily use **lazy imports** to avoid circular dependencies:

```python
def save_excel_config_view(request, notebook_id):
    from core_utils.models import TabularFile  # ← LAZY IMPORT (inside function body)
    tf = TabularFile.objects.get_or_create(...)
```

Current Python builder only emits `imports` edges for **file-level** imports. Function-scoped imports are invisible → `impact` command never finds `ui_views.py` when analyzing `TabularFile`.

**Fix options:**
- **Option A (simpler):** Bubble lazy imports to file level with `import_lazy` edge type
- **Option B (richer):** Tag lazy imports with `"lazy": true` attribute in edge metadata

**Impact:** +200 import edges, dramatically improves `impact` accuracy for Django projects.

---

## 🖥️ MCP Server Architecture (Future Infrastructure)

Instead of CLI `subprocess.run()` for every query, expose Spashta as a native MCP server:

```json
// .claude/mcp.json
{
  "spashta": {
    "command": "python",
    "args": ["-m", "uvicorn", "spashta_mcp:app", "--port", "8001"]
  }
}
```

**Benefits:**
- 24 MB graph loaded ONCE at server start (not re-parsed per CLI call)
- Agents call `spashta_search()`, `spashta_consumers()` as native tools
- No bash, no `--json` parsing, no encoding issues
- Compound commands (`field-impact`) become first-class tools
- Windows Unicode issues eliminated (server handles encoding internally)

**9 proposed tools:** `stats`, `search`, `locate`, `read`, `dependencies`, `impact`, `consumers`, `field_impact`, `scope_check`

---

## 🖥️ Windows Unicode Handling

Current state: `query_spashta.py` outputs Unicode characters (checkmarks, arrows) that crash on Windows `cp1252` encoding. Every agent must wrap calls in `subprocess.run(capture_output=True)` with manual encoding.

**Fix:** Handle all encoding server-side — either:
- Replace Unicode symbols with ASCII equivalents in CLI output
- Or use MCP server (eliminates CLI encoding entirely)

---

## 📋 Implementation Order

| Phase | What | Effort | Impact |
|---|---|---|---|
| **Phase 1** | Fix enrichment engine (Priority 1.1–1.4) | 1 day | Semantic roles jump from 100 → 1,000+ |
| **Phase 2** | Expand Django adapter (Priority 2.1–2.16) | 1 day | 16 new roles, ~200 more nodes labeled |
| **Phase 3** | Lazy import tracking in Python builder | 1 day | +200 import edges, impact accuracy fixed |
| **Phase 4** | `consumers` command (graph + grep hybrid) | 2 days | Catches all lazy import consumers |
| **Phase 5** | Layer categorization in `impact` output | 4 hours | Layer labels + missing_layers warning |
| **Phase 6** | Self-method resolution (Priority 3.1) | Half day | +500 `calls` edges |
| **Phase 7** | String template resolution (Priority 3.3) | Half day | -30 orphan templates, +100 `renders` edges |
| **Phase 8** | Model field extraction (Priority 3.4–3.5) | 1 day | +350 `has_field`/`fk_to` edges |
| **Phase 9** | `field-impact` + `scope-check` commands | 3 days | Pre-implementation safety gates |
| **Phase 10** | Better error messages + query help + metadata | 1 day | UX quality improvements |
| **Phase 11** | Variable orphan reduction | Half day | -1,500 orphans |
| **Phase 12** | MCP Server (optional, replaces CLI) | 1 week | Infrastructure — enables all above as native tools |

**Total estimated effort:** ~4.5 days

**Expected outcome after all phases:**

```
                        2.0 (current)    2.1 (target)
Semantic roles:         100              3,000+
Orphan nodes:           2,058            <500
calls edges:            702              1,200+
New edge types:         0                4 (has_field, fk_to, renders, listens_to)
Django roles:           9                25+
```

---

## 📈 Version History

| Version | Date | Description |
|---|---|---|
| 2.1.1 | 2026-03-18 | Merged improvements from `Future_Improvements_Planned/` (7 files reviewed). Added: lazy import tracking (critical builder fix), 3 new query commands (`consumers`, `field-impact`, `scope-check`), layer categorization in impact output, better error messages with suggestions, query help system, result metadata, MCP Server architecture, Windows Unicode handling. Implementation plan expanded from 6 phases to 12 phases. |
| 2.1.0 | 2026-03-18 | Initial 2.1 branch from 2.0. Full audit: 17,432 nodes, 2,058 orphans (11.8%), 100 semantic roles. Identified: enrichment engine fixes, Django adapter expansion (9→25+ roles), Python builder improvements, new edge types, orphan reduction. |
| 2.0.0 | — | Base version. Python/HTML/CSS builders, Django/FastAPI/HTMX adapters, query tool. |
