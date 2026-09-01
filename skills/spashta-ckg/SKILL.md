---
name: "spashta-ckg"
description: "Consult the Spashta Code Knowledge Graph (CKG) for full-stack blast-radius impact analysis, safe deletion verdicts, outgoing dependency tracing, dead-code detection, and route mappings across Python, JavaScript, HTML, and CSS."
argument-hint: "[command] (scan | impact <symbol> | can-delete <symbol> | dependencies <symbol> | routes | dead-code [lang] | locate <symbol> | search <query> | read <symbol> | consumers <model> | stats)"
user-invocable: true
disable-model-invocation: false
---

# Spashta-CKG Agent Skill: Deterministic Architectural Memory

> **Spashta** (स्पष्ट) = *Clarity*. Closed-loop architectural intelligence across Python, JavaScript, HTML templates, and CSS.
> **GitHub**: https://github.com/mpcoder1111/Spashta-CKG | **Version**: 3.2.8
> **Dual Delivery**: Operates interchangeably via **Native MCP Tools** (for zero-click agent reasoning in IDEs) and **CLI Interface** (for terminal workflows & scripts). Both return identical universal envelopes.

---

## 🔄 4-Phase Closed-Loop Development Protocol

1. **Pre-Flight (Task-Based)**:
   - *Delete*: `spashta_can_delete(sym)` / `can-delete <sym> --json`. If `true`, delete symbol and test files in `requires_test_updates`. If `false`, inspect production blockers.
   - *Refactor / Move*: `spashta_dependencies(sym)` / `dependencies <sym> --json` to discover outgoing helpers, models, and imports.
   - *Modify / Rename*: `spashta_impact(sym)` / `impact <sym> --depth 2 --json` to inspect all upstream callers across Python, JS, templates, and styles.
2. **Pinpoint & Inspect**:
   - `spashta_locate(sym)` / `locate <sym>` for exact `file_path`, `line_start`, `line_end` (no whole-directory scanning).
   - `spashta_search(query)` / `search <query>` (compact by default; `--full` for complete docstrings).
   - `spashta_ckg consumers <Model>` for ORM query/update sites; `spashta_ckg read <sym>` for source text.
3. **Execute Modification**: Modify target code with full awareness of all consumers and couplings.
4. **Post-Edit Sync & Audit**:
   - `spashta_refresh(files="<path>")` / `refresh --file <path>` to incrementally re-index in ~20ms.
   - `spashta_routes()` / `routes` to verify backend views, template tags, and HTMX triggers.
   - `spashta_dead_code()` / `dead-code <lang>` to audit orphaned definitions before committing.
   - `spashta_scan()` / `scan` before git commit to ensure pristine `.spashta/` graph cache.

---

## ⚡ Unified Tool & Command Catalog

Dual delivery enabled: Native MCP tools deliver both formatted `content` text and native `structuredContent` (0 decoding). CLI `--json` outputs the identical universal envelope.

| Intent / Action | Native MCP Tool | Equivalent CLI Command | Key Parameters & Flags |
| :--- | :--- | :--- | :--- |
| **Safe Deletion** | `spashta_can_delete` | `spashta_ckg can-delete <sym>` | `--summary-only` (compact ~350 B blocker paths), `--depth N` |
| **Blast Radius** | `spashta_impact` | `spashta_ckg impact <sym>` | `--depth N` (default: 3), `--json` |
| **Outbound Deps** | `spashta_dependencies` | `spashta_ckg dependencies <sym>` | `--depth N` (what symbol calls/uses), `--json` |
| **Locate Symbol** | `spashta_locate` | `spashta_ckg locate <sym>` | Breaks ties via type weighting (Func > Class > Field), `--full` |
| **Symbol Search** | `spashta_search` | `spashta_ckg search <query>` | `--type <Type>`, `--app <Prefix>`, `--full` (untruncated docstrings) |
| **Full-Stack Routes**| `spashta_routes` | `spashta_ckg routes` | Connects endpoints, views, templates, and HTMX triggers |
| **Dead Code Audit** | `spashta_dead_code` | `spashta_ckg dead-code [lang]` | `lang`: `"css"` \| `"js"` \| `"py"` (dynamic syntax safe) |
| **Graph Health** | `spashta_stats` | `spashta_ckg stats` | Node breakdowns, edge types, semantic roles, freshness status |
| **Fast Refresh** | `spashta_refresh` | `spashta_ckg refresh` | `--file <paths>` (re-parses changed files in ~20ms) |
| **Full Scan** | `spashta_scan` | `spashta_ckg scan` | `--exclude "dir1,dir2"`, `-o <dir>`, `--incremental` |
| **Exclusions** | *N/A (Human Setup)* | `spashta_ckg init / config` | `init -e "misc,tests"`, `config --add-exclude "docs"` |
| **ORM Consumers** | *N/A (CLI Utility)* | `spashta_ckg consumers <Model>` | Finds ORM queries/filter sites (Graph + Grep hybrid) |
| **Class / Style** | *N/A (CLI Utility)* | `spashta_ckg class-usage / dup-styles` | HTML attributes + JS classList; duplicate `@keyframes` |

### 🔌 Enabling Native MCP in Your IDE (`mcp_config.json`)
Spashta operates via **both CLI and Native MCP** interchangeably. To register the 10 zero-click native tools in Claude Desktop, Cursor, Antigravity, or Windsurf, add to your `mcp_config.json` (or `.cursor/mcp.json`):
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
*(If installed in a project `.venv`: specify path to `.venv/Scripts/spashta_ckg_mcp.exe` on Windows or `.venv/bin/spashta_ckg_mcp` on Linux/macOS).*

---

## 📋 Universal Response Envelope Contract

All CLI `--json` and native MCP tools return this standardized schema:
```json
{
  "status": "ok" | "not_found" | "error",
  "command": "can_delete" | "impact" | "dependencies" | "locate" | "search" | ...,
  "target": { "query": "...", "resolved_id": "...", "node_type": "...", "file_path": "...", "line_start": 45 },
  "ambiguous": false,                // true if exact-name collision was resolved via type weighting
  "alternatives": [],                // populated with alternative symbol nodes when ambiguous is true
  "summary": {
    "total_items": 4, "returned_items": 4, "truncated": false,
    "discriminating": true           // true if callers span multiple files/modules vs single file
  },
  "can_delete": true,                // on can_delete: true if 0 production callers (safe deletion)
  "blockers": { "production": [...], "tests": [...] },
  "requires_test_updates": ["tests/test_mod.py"], // test files that must be updated/deleted alongside symbol
  "items": [ ... ],                  // caller/dependency nodes (empty when summary_only=true)
  "provenance": { "files_analyzed": 268, "symbols_considered": 4276 },
  "_meta": { "version": "3.2.8", "graph_built_at": "ISO-8601 UTC", "is_stale": false, "stale_files": [] }
}
```

---

## 📌 Agent Governance Rule (Paste into `AGENTS.md` / `CLAUDE.md`)

> **Why this is mandatory:** AI agents start every conversation session with zero memory. Pasting this governance rule into your project's `AGENTS.md`, `CLAUDE.md`, or `.cursorrules` ensures the agent executes the closed-loop protocol mechanically on every prompt.
> **Update periodically:** Review and update this governance block whenever Spashta is upgraded to ensure the agent adopts new decision tools (e.g. `can_delete`, `dependencies`, `summary_only`).

```markdown
<!-- SPASHTA-CKG AGENT GOVERNANCE RULE -->
## 🧠 Code Knowledge Graph & Impact Governance (Spashta-CKG)
This project uses **Spashta-CKG** (https://github.com/mpcoder1111/Spashta-CKG) for deterministic architectural memory.
1. **Pre-Flight Before Edits**:
   - *Deletion*: Call `spashta_can_delete(symbol)`. If `can_delete: true`, proceed and update test files in `requires_test_updates`. If `false`, abort.
   - *Refactor / Move*: Call `spashta_dependencies(symbol)` to discover outgoing helpers/models that must travel with the code.
   - *Modify / Rename*: Call `spashta_impact(symbol)` to evaluate all inbound callers across Python, JS, templates, and styles.
2. **Pinpoint, Don't Guess**: Use `spashta_locate(symbol)` to get exact file paths and line ranges instead of reading directories.
3. **Verify Couplings**: Call `spashta_routes()` when altering views or URLs to ensure template tags and HTMX listeners remain intact.
4. **Refresh & Periodic Rescan**:
   - *After edits*: Call `spashta_refresh(files="<path>")` (~20ms).
   - *After git pull / branch switches*: Run `spashta_scan()` to re-index changed project files.
   - *Before git commit*: Run `spashta_scan()` and `spashta_dead_code()`.
```

---

## 📚 Deep Reference & Catalog
Exhaustive catalog of all 39 node types, 32 edge types, and cross-language couplings: [`reference/spashta-query-guide.md`](reference/spashta-query-guide.md).
