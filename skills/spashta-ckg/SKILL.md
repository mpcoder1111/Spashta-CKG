---
name: "spashta-ckg"
description: "Consult the Spashta Code Knowledge Graph (CKG) for full-stack blast-radius impact analysis, dead-code detection, route mappings, and dependency tracing across Python, JavaScript, HTML, and CSS."
argument-hint: "[command] (scan | impact <symbol> [--depth N] | dependencies <symbol> | routes | dead-code [lang] | locate <symbol> | read <symbol> | consumers <model> | scope-check <symbol> | stats)"
user-invocable: true
disable-model-invocation: false
---

# Spashta-CKG Agent Skill: Closed-Loop Development Guide

> **Spashta** (स्पष्ट) = *Clarity*. Deterministic architectural memory for developers and AI agents.
> **GitHub Repository**: https://github.com/mpcoder1111/Spashta-CKG

This skill provides AI coding agents and developers with **deterministic situational awareness** across Python, JavaScript, HTML templates, and CSS stylesheets.

---

## 🔄 The 4-Phase Closed-Loop Development Protocol

To maintain architectural integrity and eliminate hallucinations/breakages, follow this closed loop for every coding task:

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. PRE-FLIGHT (Impact & Blast Radius)                                  │
│    • CLI: spashta_ckg impact <TargetSymbol> --depth 2 --json           │
│    • Or Native MCP Tool: spashta_impact(symbol="TargetSymbol")         │
│    • Find all callers across Python, JS, HTML templates, and CSS       │
│    • Check dependencies: spashta_ckg dependencies <TargetSymbol>      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. PINPOINT & READ (Zero Context Bloat)                                │
│    • Pinpoint exact file & lines: spashta_ckg locate <TargetSymbol>    │
│    • Read node source code: spashta_ckg read <TargetSymbol>            │
│    • For ORM models: spashta_ckg consumers <ModelName>                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. EXECUTE MODIFICATION                                                │
│    • Modify the target code with full awareness of all consumers       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. POST-EDIT RESCAN & VERIFICATION (Close the Loop)                    │
│    • Refresh graph: spashta_ckg scan                                   │
│    • Verify full-stack routes: spashta_ckg routes                      │
│    • Check for orphaned code: spashta_ckg dead-code <lang>             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ Complete CLI Command Reference

All commands run from the project root (or with `-p <project_root>`):

### 1. Project Setup & Directory Exclusions
```bash
# (Optional) Initialize a profile.json with custom directory exclusions
spashta_ckg init --exclude "misc,reference,legacy"

# View active configuration and excluded directories
spashta_ckg config
spashta_ckg config --json

# Append or update directory exclusions
spashta_ckg config --add-exclude "misc,docs,reference"

# Scan project and build CKG cache (all languages/frameworks auto-detected)
spashta_ckg scan
spashta_ckg scan --exclude "misc,legacy"
```

### 2. Pre-Refactoring & Impact Analysis
```bash
# Calculate blast-radius: who calls or depends on this symbol?
spashta_ckg impact "MyFunctionOrClass"
spashta_ckg impact "MyFunctionOrClass" --depth 3 --json

# What does this symbol depend on? (Outgoing calls, imports, models)
spashta_ckg dependencies "MyFunctionOrClass"

# Pre-edit safety check: compare your planned edits vs actual blast radius
spashta_ckg scope-check "TargetSymbol" --analyzed "app/views.py,app/models.py"
```

### 2. Precise Code Navigation (Without Context Bloat)
```bash
# Pinpoint exact file path, start line, and end line
spashta_ckg locate "calculate_total"

# Read source code of a node directly from disk
spashta_ckg read "calculate_total"

# Search nodes by name, ID, or semantic role
spashta_ckg search "Order" --type Model
spashta_ckg search "api" --app "billing"

# Find all ORM usage sites for a Django/FastAPI model (Graph + Grep hybrid)
spashta_ckg consumers "Order"
```

### 3. Full-Stack Routing & Cross-Language Couplings
```bash
# Map URL routes to backend views, template tags, and HTMX triggers
spashta_ckg routes

# Check where a CSS class is defined and used (HTML attributes + JS classList)
spashta_ckg class-usage "btn-primary"

# Find duplicate CSS definitions and duplicate @keyframes blocks
spashta_ckg dup-styles
```

### 4. Dead Code & Quality Auditing
```bash
# Audit dead code across CSS, JS, or Python (dynamic-syntax safe)
spashta_ckg dead-code css
spashta_ckg dead-code js
spashta_ckg dead-code py

# Display overall graph statistics and node/edge breakdowns
spashta_ckg stats
```

---

## 🤖 Native MCP Server Tools Reference (Zero-Click Execution)

When `spashta_ckg_mcp` is registered in your IDE's `mcp_config.json`, use these native tools directly with **zero permission clicks**:

| Native MCP Tool | Parameters | Purpose / Returned Subgraph |
| :--- | :--- | :--- |
| `spashta_impact` | `symbol: str`, `depth: int = 3`, `project_dir: str = "."` | Upstream blast radius: who calls or depends on this symbol before editing |
| `spashta_routes` | `project_dir: str = "."` | Full-stack routes connecting backend views, templates, and HTMX triggers |
| `spashta_search` | `query: str`, `node_type: str = None`, `project_dir: str = "."` | Searches CKG for symbols, classes, styles, or endpoints |
| `spashta_dead_code` | `language: str = "css"|"js"|"py"`, `project_dir: str = "."` | Dynamic-safe dead code detection with zero false-positives |
| `spashta_scan` | `project_dir: str = "."` | Scans codebase and rebuilds `.spashta/` CKG cache |

### MCP IDE Configuration (`mcp_config.json`):
```json
{
  "mcpServers": {
    "spashta_ckg": {
      "command": "spashta_ckg_mcp",
      "args": []
    }
  }
}
```
*(If installed in project virtualenv, set `"command": ".venv/Scripts/spashta_ckg_mcp.exe"` on Windows or `".venv/bin/spashta_ckg_mcp"` on Linux/macOS).*

---

## 📌 CRITICAL: Add to Your `AGENTS.md` / `CLAUDE.md`

Because AI agents start every conversation with zero memory of previous sessions, **you must include Spashta rules in your project's `AGENTS.md` or `CLAUDE.md`** (or `.cursorrules` / `.windsurfrules`).

### Paste this into your `AGENTS.md` / `CLAUDE.md`:

```markdown
<!-- SPASHTA-CKG AGENT GOVERNANCE RULE -->
## 🧠 Code Knowledge Graph & Impact Governance (Spashta-CKG)

This project uses **Spashta-CKG** (https://github.com/mpcoder1111/Spashta-CKG) for deterministic architectural memory and blast-radius tracking.

**Mandatory Rules for AI Coding Agents:**
1. **Query First (Closed-Loop Pre-Flight)**:
   - Before modifying, renaming, or deleting any function, class, model, route, or CSS class:
     - **If MCP tools are active**: Call `spashta_impact(symbol="<SymbolName>")`.
     - **If CLI only**: Run `spashta_ckg impact <SymbolName> --depth 2 --json`.
   - Inspect all returned callers across Python, JavaScript, HTML templates, and CSS stylesheets.
2. **Pinpoint, Don't Guess**:
   - Use `spashta_ckg locate <SymbolName>` (or `spashta_search`) to find exact file paths and line ranges instead of reading entire directories.
   - For database models, use `spashta_ckg consumers <ModelName>` to verify all query and update sites.
3. **Verify Routing & Couplings**:
   - When altering URLs or views, call `spashta_routes()` (or run `spashta_ckg routes`) to ensure template `{% url %}` tags and HTMX event listeners remain intact.
4. **Rescan Before Commit & Periodically**:
   - **Always run `spashta_ckg scan` (or call `spashta_scan()`) before creating a git commit** to ensure `.spashta/` graph memory is synchronized with active changes.
   - Audit with `spashta_dead_code()` to ensure no broken or orphaned code is committed.
```

---

## 📚 Deep Reference & Catalog

For detailed documentation on:
- All 39 node types and 32 edge types
- Cross-language couplings (`resolves_to`, `includes_urlconf`, `dispatches_event`, `oob_swaps`, `uses_animation`, `queries_dom`)
- Safe SOP for dead-code cleanup

Read the exhaustive guide in [`reference/spashta-query-guide.md`](reference/spashta-query-guide.md).
