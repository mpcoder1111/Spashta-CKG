# Changelog

All notable changes to Spashta-CKG will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.0.0] - 2025-12-30

**Spashta-CKG 2.0 — Complete Architectural Redesign**

This is the first public release of Spashta-CKG with a production-ready architecture designed for AI-assisted coding at scale.

### 🎯 What is Spashta-CKG?

A **Code Knowledge Graph** tool that gives AI Agents deterministic, structured knowledge about codebases — eliminating guesswork and hallucinations.

### ✨ Key Features

- **AST-Based Parsing** — Extracts structure from Python, HTML, and CSS using native language tools
- **Line Numbers & Docstrings** — Exact locations and documentation for every code element
- **Import & Call Tracking** — Who imports whom, what calls what
- **Semantic Enrichment** — Framework-aware understanding (Django, FastAPI, HTMX)
- **Query Tool** — CLI for AI agents to query the graph without reading files
- **Incremental Updates** — Only re-process changed files

### 🏗️ Architecture Highlights

| Layer | Purpose |
|-------|---------|
| **Core** | Universal software schema (nodes.json, edges.json) |
| **Builders** | Language observers (Python, HTML, CSS) |
| **Adapters** | Framework interpreters (Django, FastAPI, HTMX) |
| **Runtime** | Execution engine (build → enrich → validate) |
| **Project** | Per-project configuration (profile.json) |

### 📊 Enrichment Levels

| Level | Description |
|-------|-------------|
| **L1** | Rule-based adapter enrichment (fast, deterministic) |
| **L2** | LLM-based enrichment (deep, business context) |

### 🔧 Supported Technologies

**Languages:**
- ✅ Python
- ✅ HTML
- ✅ CSS

**Frameworks:**
- ✅ Django
- ✅ FastAPI
- ✅ HTMX

### 📚 Documentation

Complete documentation suite included in `_docs/`:
- Architecture reference
- Builder & adapter guides
- Query tool reference
- Contributor guidelines

---

## [1.0.0] - Pre-2.0

Initial prototype. Superseded by 2.0 architecture.

---

*Spashta-CKG — Deterministic Architectural Memory for Agentic Coding*
