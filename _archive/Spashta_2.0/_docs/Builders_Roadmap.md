# Spashta-CKG Builders – Roadmap & Limitations

This document consolidates the roadmaps and known limitations for all language builders.

---

## Table of Contents

1. [Python Builder](#1-python-builder)
2. [HTML Builder](#2-html-builder)
3. [CSS Builder](#3-css-builder)
4. [Cross-Builder Future Work](#4-cross-builder-future-work)
5. [Mental Rules](#5-mental-rules)

---

## 1. Python Builder

### Current Status: Full AST
The Python builder uses Python's native `ast` module for complete structural extraction.

### Implemented Features ✅
- [x] Function and Class extraction
- [x] Import tracking (absolute and relative)
- [x] Call graph edges with line numbers
- [x] Decorator detection
- [x] Line number metadata (`line_start`, `line_end`)
- [x] Docstring extraction
- [x] Function signature (arguments, return type)

### Known Limitations
1. ❌ **External Library Calls**: Calls to stdlib/third-party (e.g., `json.load`, `os.path`) are logged as ambiguities, not tracked as edges.
2. ❌ **Dynamic Calls**: Cannot resolve `getattr(obj, method)()` or similar dynamic patterns.
3. ❌ **Chained Calls**: Only first hop of `obj.method1().method2()` is resolved.

### Future Work
- **Type Inference**: Track variable types for better call resolution.
- **Stub Support**: Create nodes for common external libraries.

---

## 2. HTML Builder

### Current Status: DOM Parser
The HTML builder uses Python's `HTMLParser` for structural extraction.

### Implemented Features ✅
- [x] Template detection
- [x] Static asset linking (CSS, JS, images)
- [x] HTMX attributes (`hx-get`, `hx-post`, etc.)
- [x] Route/API endpoint extraction from forms and links
- [x] Line number tracking
- [x] ID and class attribute extraction

### Known Limitations
1. ❌ **No Full DOM Hierarchy**: Elements inside elements not modeled.
2. ❌ **No Event Binding**: JavaScript event handlers not tracked.
3. ❌ **Template Variables**: Django/Jinja `{{ }}` syntax not parsed.

### Future Work

| Feature | When to Add | Why Deferred |
|---------|-------------|--------------|
| **DOM Structure Semantics** | When HTML structure modeling needed | Current focus is cross-language links |
| **Events & JS Behavior** | After JavaScript builder exists | Events need JS context |
| **Template Engine Semantics** | After adapters are stable | Framework-specific, needs adapter layer |
| **Meta Tag Semantics** | When SEO/compliance use-cases arise | No consumers depend on it |
| **CSS Selector Targeting** | After CSS builder is mature | Requires DOM element modeling |

---

## 3. CSS Builder

### Current Status: Regex-First
The CSS builder uses **regex-based** heuristics to capture structural selectors (.class, #id) and @import dependencies efficiently.

### Implemented Features ✅
- [x] Class selector extraction (`.class`)
- [x] ID selector extraction (`#id`)
- [x] Element selector extraction (`div`, `body`)
- [x] `@import` dependency tracking
- [x] Pseudo-state detection (`:hover`, `:focus`)
- [x] Line number tracking

### Known Limitations
1. ❌ **No Media Query Scope**: Selectors inside `@media { ... }` are treated as top-level.
2. ❌ **No Nested Rules**: SCSS/CSS Nesting Module syntax may be mis-extracted.
3. ❌ **No Property Extraction**: Values (color, font-size) are intentionally ignored (structural focus).

### Future Work
- **Selector Resolving**: Map complex selectors (`div > .class`) to HTML nodes.
- **CSS Parser Integration**: Adopt `tinycss2` or similar for robustness.
- **Media Query Awareness**: Proper scoping of selectors within media queries.

---

## 4. Cross-Builder Future Work

These features require multiple builders to be stable first:

| Feature | Description | Prerequisites | Status |
|---------|-------------|---------------|--------|
| **Full Import Resolution** | Resolve imports across files, detect unused/missing | All language builders stable | 🔜 Future |
| **Agent Feedback Loop** | Agents consume ambiguity logs, auto-resolution | Stable graph structure | 🔜 Future |
| **Cross-Language Linking** | Template ← View → Model edges (automatic) | HTML + Python builders | ⚠️ Partial (schema ready, `render()` detection works, full automation pending) |

---

## 5. Mental Rules

### The Golden Rule
> **Add a feature only when:**
> 1. The schema can represent it
> 2. The builder can extract it without guessing
> 3. Another layer can actually use it

### Builder Principles
- **Builders are cameras**: They observe and record, never interpret or guess.
- **Structure before semantics**: Extract what exists, not what it means.
- **No framework logic**: Builders are language-aware, not framework-aware.
- **Log ambiguities**: When uncertain, log to ambiguities rather than emit wrong data.

---

## 6. Directory Structure

```
builders/
├── builder_rules.json          # Global builder policies
│
├── python/
│   ├── build_ast.py            # Python AST extractor
│   └── language_mapping.json   # Python syntax → Core concepts
│
├── html/
│   ├── build_dom.py            # HTML structure extractor
│   └── language_mapping.json   # HTML → Core concepts
│
└── css/
    ├── build_css.py            # CSS selector extractor
    └── language_mapping.json   # CSS → Core concepts
```

---

*Last Updated: 2025-12-30*
