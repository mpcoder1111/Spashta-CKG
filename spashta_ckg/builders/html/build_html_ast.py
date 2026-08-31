"""
Spashta-CKG – HTML AST Builder (Strict Implementation)

AUTHORITATIVE CONTRACT: `builders/html/builder_html_instructions_for_builder_code_development.json`

## Overview
This script captures the **Structure Only** of the HTML codebase. It parses HTML files as Templates and identifies static relationships (Assets, API calls) based strictly on the schema.

## Data Flow & Formats
1. [Codebase] -> [HTML Parser] -> [StructureWalker] -> [Context]
2. [Context] -> Output: code_knowledge_graph_html.json (Nodes, Edges, Ambiguities, Meta)

## Strict Compliance
- **Structure Only**: No DOM tree construction.
- **Schema Enforcement**: `SchemaEnforcer` validates against Core Schema ONLY.
- **Mapping Discipline**: Builder validates edges against `html_language_mapping.json` BEFORE schema.
- **Scoped IDs**: Symbolic nodes are scoped to file to prevent global collision (Python parity).
- **Explicit Ambiguity**: Dynamic values (config-driven) & External URLs emit explicit ambiguities.
"""

import json
import hashlib
import re
import sys
import uuid
import argparse
import datetime
from pathlib import Path
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Any

# ---------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------

# PATHS RELATIVE TO THIS SCRIPT
BUILDER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILDER_DIR.parent.parent

INSTRUCTIONS_PATH = BUILDER_DIR / "builder_html_instructions_for_builder_code_development.json"
MAPPING_PATH = BUILDER_DIR / "html_language_mapping.json"
CORE_EDGES_PATH = PROJECT_ROOT / "core/software_schema/edges.json"
BUILDER_RULES_PATH = BUILDER_DIR.parent / "builder_rules.json"

def load_scan_exclusions(source_root=None, cli_exclude=None):
    """Loads exclusion rules from builder_rules.json + profile.json (in source_root or package) + CLI overrides."""
    exclude_dirs = set([".venv", "venv", "env", "__pycache__", ".git", "node_modules"])  # Defaults
    if cli_exclude:
        for d in str(cli_exclude).split(","):
            d_clean = d.strip()
            if d_clean:
                exclude_dirs.add(d_clean)

    exclude_patterns = []
    if BUILDER_RULES_PATH.exists():
        try:
            rules = json.loads(BUILDER_RULES_PATH.read_text("utf-8"))
            policy = rules.get("scan_policy", {})
            exclude_dirs.update(policy.get("exclude_dirs", []))
            exclude_patterns = policy.get("exclude_file_patterns", [])
        except Exception:
            pass

    # Project-specific exclusions from profile.json (check source_root first, then package default)
    candidates = []
    if source_root:
        sr = Path(source_root).resolve()
        candidates.extend([sr / "profile.json", sr / ".spashta" / "profile.json"])
    candidates.append(PROJECT_ROOT / "project" / "profile.json")

    for profile_path in candidates:
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text("utf-8"))
                exclude_dirs.update(profile.get("excluded", {}).get("directories", []))
                break
            except Exception:
                pass
    return exclude_dirs, exclude_patterns


# ---------------------------------------------------------
# SCHEMA ENFORCER
# ---------------------------------------------------------
class SchemaEnforcer:
    """
    Validates edge creation against the Core Schema ONLY.
    DOES NOT know about Language Mapping.
    """
    def __init__(self, edges_schema: dict):
        # Flatten edge schema for easier lookup: {edge_name: {from: [], to: []}}
        self.edge_rules = {}
        for category in edges_schema.values():
            if isinstance(category, dict):
                 for k, v in category.items():
                     if isinstance(v, dict) and "from" in v: # Valid edge def
                         self.edge_rules[k] = v

    def is_allowed(self, edge_type: str, src_type: str, dst_type: str) -> bool:
        """Checks if Core Schema allows this connection."""
        rule = self.edge_rules.get(edge_type)
        if not rule:
            return False # Unknown edge type in Core
            
        allowed_src = rule.get("from", [])
        allowed_dst = rule.get("to", [])
        
        return (src_type in allowed_src) and (dst_type in allowed_dst)

# ---------------------------------------------------------
# BUILD CONTEXT
# ---------------------------------------------------------
class BuildContext:
    def __init__(self, root_path: Path, instructions: dict, mapping: dict, schema_enforcer: SchemaEnforcer):
        self.root_path = root_path
        self.instructions = instructions
        self.mapping = mapping
        self.schema = schema_enforcer
        
        self.nodes = []
        self.edges = []
        self.ambiguities = []
        self.logs = []
        
        # Internal tracking
        self._node_ids = set()
        self._edge_keys = set()
        self.current_file = None
        self.current_file_id = None
        self.current_file_hash = None
        
        # Pre-process allowed mapping edges for fast check
        self._allowed_mapping_edges = set()
        self._collect_allowed_edges()
        
        # Config caching
        self.dynamic_patterns = self.instructions.get("dynamic_content_policy", {}).get("template_expressions", ["{{", "{%"])

    def _collect_allowed_edges(self):
        """Extract all valid edge types defined in the language mapping."""
        for rule in self.mapping.get("attribute_interactions", []):
            self._allowed_mapping_edges.add(rule["emits_edge"])
            # A rule may declare an ADDITIONAL edge (e.g. hx-trigger emits triggers_event AND, for a
            # `from:` clause, listens_to — the HTMX-listens-for-a-JS-event coupling). Register it too.
            if rule.get("listener_edge"):
                self._allowed_mapping_edges.add(rule["listener_edge"])

        for rules in self.mapping.get("tag_interactions", {}).values():
            for rule in rules:
                self._allowed_mapping_edges.add(rule["emits_edge"])

        # P1 — Django/Jinja template-tag relations ({% extends %}/{% include %} → Template→Template).
        for edge in self.mapping.get("template_relations", {}).values():
            if isinstance(edge, str):
                self._allowed_mapping_edges.add(edge)

        # CSS coverage P1 — class="…" → uses_style (Template→StyleClass).
        cu = self.mapping.get("class_usage")
        if isinstance(cu, dict) and cu.get("emits_edge"):
            self._allowed_mapping_edges.add(cu["emits_edge"])
        # dead-code-accuracy P3 — inline <script> classList/querySelector → uses_style.
        scu = self.mapping.get("script_class_usage")
        if isinstance(scu, dict) and scu.get("emits_edge"):
            self._allowed_mapping_edges.add(scu["emits_edge"])

    def emit_node(self, node_type: str, name: str, confidence: str = "structural", **kwargs):
        # Generate ID: Scoped to file for strict determinism
        if node_type == "Template":
            node_id = name
            # Template is truly structural
            final_confidence = "structural"
        else:
            # Symbolic nodes (Routes, Assets) are scoped to the file they appear in
            # This prevents "index.html linking to /login" and "nav.html linking to /login" 
            # from magically merging without proof.
            node_id = f"{self.current_file}::{node_type}::{name}"
            # Symbolic nodes are heuristic/symbolic, not structural definitions
            final_confidence = "heuristic"

        if node_id not in self._node_ids:
            node_data = {
                "node_type": node_type,
                "name": name,
                "id": node_id,
                "analysis_confidence": final_confidence,
                "line_start": kwargs.get("line_start"),
                "line_end": kwargs.get("line_end"), # Explicitly None for HTML structure nodes
                "attributes": kwargs.get("attributes")
            }
            node_data.update(kwargs)
            # Clean up None values if desired, or keep them for schema parity. 
            # We keep them to match Python structural output.
            
            self.nodes.append(node_data)
            self._node_ids.add(node_id)
        return node_id

    def emit_edge(self, edge_type: str, src_id: str, dst_id: str, src_type: str, dst_type: str):
        # 1. Mapping Gate
        if edge_type not in self._allowed_mapping_edges:
             self.emit_ambiguity("mapping_violation", edge_type, f"Edge type '{edge_type}' not defined in mapping", self.current_file)
             return

        # 2. Schema Gate
        if not self.schema.is_allowed(edge_type, src_type, dst_type):
            self.emit_ambiguity("schema_violation", f"{edge_type}:{src_type}->{dst_type}", "Edge not allowed by Core Schema", self.current_file, confidence="structural_violation")
            return

        # 3. Emit
        edge_key = (edge_type, src_id, dst_id)
        if edge_key not in self._edge_keys:
            self.edges.append({
                "edge": edge_type,
                "from": src_id,
                "to": dst_id
            })
            self._edge_keys.add(edge_key)

    def emit_ambiguity(self, kind: str, expression: str, reason: str, scope: str, confidence: str = "unresolved"):
        self.ambiguities.append({
            "id": str(uuid.uuid4()),
            "kind": kind,
            "source_file": scope,
            "source_scope": scope,
            "expression": expression,
            "reason": reason,
            "confidence": confidence,
            "resolver": self.instructions.get("ambiguity_policy", {}).get("default_resolver", "agent")
        })

# ---------------------------------------------------------
# STRUCTURE WALKER
# ---------------------------------------------------------
class StructureWalker(HTMLParser):
    def __init__(self, ctx: BuildContext):
        super().__init__()
        self.ctx = ctx
        self.attr_interactions = ctx.mapping.get("attribute_interactions", [])
        self.tag_interactions = ctx.mapping.get("tag_interactions", {})
        
    def handle_starttag(self, tag, attrs):
        attr_dict = {k: v for k, v in attrs if v is not None}
        
        line_number = self.getpos()[0]
        context_attrs = self._extract_context(tag, attr_dict)
        
        # 1. Attribute Rules (e.g. hx-get)
        for rule in self.attr_interactions:
            if rule["attribute"] not in attr_dict:
                continue
            # P5 (OOB): a rule may target the element's OWN context attribute (its id) rather than the
            # triggering attribute's value — hx-swap-oob refreshes the element with the SAME id, so the
            # coupling target is `id`, not the "true"/"outerHTML" swap value. value_from_context={} → the
            # standard attribute-value flow (byte-identical). A missing id → nothing to target (skip).
            vfc = rule.get("value_from_context")
            if vfc:
                value = attr_dict.get(vfc)
                if not value:
                    continue
                # A templated id (id="x-{{ var }}") is not a stable literal target — an ambiguity, never a
                # guessed edge. Checked locally on the brace MARKERS: the shared dynamic_patterns are the
                # literal strings "{{ }}"/"{% %}" (only empty braces), and broadening that shared check
                # would wrongly ambiguate a `{% url %}` value BEFORE the route regex extracts its name.
                if any(m in value for m in ("{{", "}}", "{%", "%}")):
                    self.ctx.emit_ambiguity("dynamic_value_unresolved", value,
                                            f"Templated {vfc} — not a stable OOB target", self.ctx.current_file)
                    continue
            else:
                value = attr_dict[rule["attribute"]]
            self._process_interaction(rule, value, line_number, context_attrs)

        # 1b. Class usage (CSS coverage P1): class="a b c" → uses_style per literal token.
        self._emit_class_usage(attr_dict, line_number, context_attrs)

        # 2. Tag Rules (e.g. <link rel=...>)
        if tag in self.tag_interactions:
            for rule in self.tag_interactions[tag]:
                # Condition Check (Supports Strings and Lists)
                cond = rule.get("condition")
                if cond:
                    match = True
                    for k, v in cond.items():
                        actual = attr_dict.get(k)
                        if isinstance(v, list):
                            if actual not in v: 
                                match = False; break
                        elif actual != v:
                            match = False; break
                    if not match: continue
                
                target_attr = rule["attribute"]
                if target_attr in attr_dict:
                     self._process_interaction(rule, attr_dict[target_attr], line_number, context_attrs)

    def _extract_context(self, tag, attr_dict):
        """Extracts UI context: tag, id, class, method."""
        ctx = {"tag": tag}
        
        # Standard Identity
        if "id" in attr_dict: ctx["id"] = attr_dict["id"]
        if "class" in attr_dict: ctx["class"] = attr_dict["class"]
        
        # Method / Action Context
        if "method" in attr_dict: ctx["method"] = attr_dict["method"].upper()
        
        # HTMX Method Heuristic (if we see hx-post/put/delete, capture that intent)
        for method in ["post", "put", "delete", "patch"]:
            if f"hx-{method}" in attr_dict:
                 ctx["method"] = method.upper(); break
                 
        return ctx

    def _emit_class_usage(self, attr_dict, line_number, context_attrs):
        """CSS coverage P1 (+ dead-code-accuracy P1): a class attribute applies CSS classes → one `uses_style`
        edge (Template → StyleClass) per LITERAL token, joined by name at merge to the CSS StyleClass
        (`defines`) + JS `queries_dom`. Off when `class_usage` is unconfigured.

        The template tags are STRIPPED (each `{% … %}`/`{{ … }}` → a space, a token boundary) BEFORE
        tokenizing, so a literal class BETWEEN tags is captured — `class="a {% if x %}b{% endif %}"` yields
        both `a` AND `b`, while the tag CONTENTS (`if`/`x`/`endif`) are removed with the tag so no bogus class
        leaks. A token split by a variable (`fp-{{ v }}` → `fp-`, or `{{ v }}-x` → `-x`) has a dangling
        leading/trailing hyphen and is rejected — it stays a dynamic ambiguity, never a guessed edge."""
        cfg = self.ctx.mapping.get("class_usage")
        if not isinstance(cfg, dict) or cfg.get("attribute") not in attr_dict:
            return
        value = attr_dict[cfg["attribute"]]
        if not value:
            return
        edge, ttype = cfg.get("emits_edge", "uses_style"), cfg.get("target_node_type", "StyleClass")
        stripped = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", value)
        for token in stripped.split():
            # a full class token: letter/underscore start, alnum/underscore end (a dangling hyphen from a
            # variable-split partial is rejected). A single letter/underscore is also a valid class.
            if not re.fullmatch(r"[A-Za-z_]([\w-]*[A-Za-z0-9_])?", token):
                continue
            target_id = self.ctx.emit_node(ttype, token, line_start=line_number, attributes=context_attrs)
            self.ctx.emit_edge(edge, self.ctx.current_file_id, target_id, "Template", ttype)
        if stripped != value:  # the attribute carried template tags → record the dynamic signal (for dead-css)
            self.ctx.emit_ambiguity("dynamic_class_unresolved", value.strip()[:100],
                                    "Templated class attribute — some tokens are dynamic", self.ctx.current_file)

    def _process_interaction(self, rule, value, line_number, context_attrs):
        # 1. Dynamic Ambiguity Check (Config Driven)
        for pattern in self.ctx.dynamic_patterns:
            if pattern in value:
                self.ctx.emit_ambiguity(
                    "dynamic_value_unresolved", value, 
                    f"Contains dynamic pattern '{pattern}'", self.ctx.current_file
                )
                return

        # 2. External URL Check (Strict)
        if value.strip().lower().startswith(("http:", "https:", "//", "mailto:")):
             self.ctx.emit_ambiguity(
                 "external_reference_unmodeled", value,
                 "External URL references are not structural edges", self.ctx.current_file
             )
             return

        # 3. Emit Valid Structure
        target_type = rule["target_node_type"]
        edge_type = rule["emits_edge"]

        # ADDITIVE (frontend-route-coupling): a Route target whose value is a Django `{% url 'name' … %}`
        # tag resolves to the bare url-name, so the template's calls_api Route JOINS BY NAME to the
        # Python builder's Route('name') (path(…, name='name')). A dynamic `{% url var %}` / `{{ … }}`
        # is left unchanged (stays a full-value placeholder — no regression, no guessed edge).
        if target_type == "Route":
            m = re.match(r"\{%\s*url\s+['\"]([\w:.-]+)['\"]", value.strip())
            if m:
                value = m.group(1)

        target_id = self.ctx.emit_node(target_type, value, line_start=line_number, attributes=context_attrs) # Confidence handled inside

        self.ctx.emit_edge(
            edge_type,
            self.ctx.current_file_id,
            target_id,
            "Template",
            target_type
        )

        # ADDITIVE (htmx-event-coupling): a rule may ALSO couple a listener. hx-trigger declares
        # listener_edge=listens_to — for each `from:` clause it emits a listens_to edge onto a Event
        # node named by the BARE event name (modifiers/[filter] stripped), so it joins BY NAME with the
        # JS builder's dispatches_event('<name>') (the placeholder-per-emitter model, like queries_dom).
        # The generic triggers_event above is left untouched (the HTMX adapter's Component detection).
        if rule.get("listener_edge"):
            self._emit_htmx_listeners(rule["listener_edge"], value, line_number, context_attrs)

    def _emit_htmx_listeners(self, listener_edge, value, line_number, context_attrs):
        """For an hx-trigger value, emit a listens_to edge per clause that carries a `from:` modifier
        (the element listens for an event fired on ANOTHER element — the JS dispatchEvent coupling).
        The Event node uses the BARE event name; a templated/dynamic name becomes an ambiguity."""
        for clause in value.split(","):
            clause = clause.strip()
            if not clause or not re.search(r"(^|\s)from:", clause):
                continue  # no `from:` → a self-trigger, already covered by triggers_event
            match = re.match(r"([^\s\[]+)", clause)  # first token, minus a trailing [filter]
            event = match.group(1) if match else clause
            # A templated / dynamic event name is unresolvable → an ambiguity, never a guessed edge
            # (the determinism contract). Covers Django {{ }}/{% %} + any configured dynamic pattern.
            if "{" in event or "}" in event or any(p in clause for p in self.ctx.dynamic_patterns):
                self.ctx.emit_ambiguity(
                    "unresolved_event", clause,
                    "Dynamic / templated hx-trigger event name",
                    self.ctx.current_file,
                )
                continue
            ev_id = self.ctx.emit_node("Event", event, line_start=line_number, attributes=context_attrs)
            self.ctx.emit_edge(listener_edge, self.ctx.current_file_id, ev_id, "Template", "Event")

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def _emit_template_relations(ctx, scanned):
    """P1: {% extends "x" %} / {% include "y" %} → Template→Template edges. Matches the tag's logical
    path to a physical Template by its /templates/-relative name (deterministic one-or-none; a dynamic
    `{% extends var %}` has no quotes so it never matches; a 3rd-party/absent target → an ambiguity)."""
    tag_edges = {tag: edge for tag, edge in ctx.mapping.get("template_relations", {}).items()
                 if isinstance(edge, str)}
    if not tag_edges:
        return
    def _logical(s):  # the /templates/-relative name (templates/ at start OR mid-path)
        return re.split(r"(?:^|/)templates/", s)[-1]
    logical = {}
    for nd in ctx.nodes:
        if nd.get("node_type") == "Template":
            logical.setdefault(_logical(nd["id"]), nd["id"])
    tag_re = re.compile(r"\{%\s*(" + "|".join(map(re.escape, tag_edges)) + r")\s+['\"]([^'\"]+)['\"]")
    for rel, content, src_id in scanned:
        for m in tag_re.finditer(content):
            tag, path = m.group(1), m.group(2).strip()
            target = logical.get(path) or logical.get(_logical(path))
            if target:
                ctx.emit_edge(tag_edges[tag], src_id, target, "Template", "Template")
            else:
                ctx.emit_ambiguity("unresolved_template_ref", path,
                                   f"{{% {tag} %}} target not found in scanned templates", rel)


def _emit_inline_script_usage(ctx, scanned):
    """dead-code-accuracy P3: scan each template's inline <script> blocks for LITERAL DOM-class references —
    `el.classList.add/remove/toggle('x')` and `querySelector('.x')`/`querySelectorAll('.x')` (a SIMPLE
    `.class` selector only) — and emit `uses_style` (Template → StyleClass). Closes the 'JS embedded in a
    template, not a .js file' blind spot (the JS builder scans .js files only). A variable selector is not
    literal → unmodeled, never a guess. Off when script_class_usage is unconfigured."""
    cfg = ctx.mapping.get("script_class_usage")
    if not isinstance(cfg, dict):
        return
    edge, ttype = cfg.get("emits_edge", "uses_style"), cfg.get("target_node_type", "StyleClass")
    pats = []
    clm = "|".join(re.escape(m) for m in cfg.get("classlist_methods", []))
    if clm:  # el.classList.add('x') — a bare class name (first string arg)
        pats.append(re.compile(r"\.classList\.(?:" + clm + r")\(\s*['\"]([A-Za-z_][\w-]*)['\"]"))
    qm = "|".join(re.escape(m) for m in cfg.get("query_methods", []))
    if qm:  # querySelector('.x') — a SIMPLE .class selector (the closing quote right after the name)
        pats.append(re.compile(r"(?:" + qm + r")\(\s*['\"]\.([A-Za-z_][\w-]*)['\"]"))
    script_re = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
    for rel, content, tid in scanned:
        ctx.current_file, ctx.current_file_id = rel, tid
        for sm in script_re.finditer(content):
            body = sm.group(1)
            for pat in pats:
                for m in pat.finditer(body):
                    nid = ctx.emit_node(ttype, m.group(1))
                    ctx.emit_edge(edge, tid, nid, "Template", ttype)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, help="Root directory or file to parse")
    parser.add_argument("--files", default=None, help="Comma-separated specific files to parse relative to source-root")
    parser.add_argument("--existing-ast", default=None, help="Path to existing raw AST JSON for global symbol resolution")
    parser.add_argument("--out", required=True, help="Path to write output AST JSON")
    parser.add_argument("--exclude", default=None, help="Comma-separated directories to exclude")
    args = parser.parse_args()
    
    root = Path(args.source_root).resolve()
    
    # Load Configuration
    try:
        instr = json.loads(INSTRUCTIONS_PATH.read_text("utf-8"))
        mapping = json.loads(MAPPING_PATH.read_text("utf-8"))
        edges_schema = json.loads(CORE_EDGES_PATH.read_text("utf-8"))
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    # Initialize Components
    enforcer = SchemaEnforcer(edges_schema)
    
    # SCAN FILES (Support Specific Files, Single File, or Directory)
    if getattr(args, "files", None):
        root_dir = root
        raw_files = [f.strip() for f in args.files.split(",") if f.strip()]
        html_files = [Path(f).resolve() if Path(f).is_absolute() else (root_dir / f).resolve() for f in raw_files]
        html_files = sorted([p for p in html_files if p.exists() and p.suffix == ".html"])
    elif root.is_file():
        # Case: Unit Test or Single File Scan
        root_dir = root.parent
        html_files = [root]
    else:
        # Case: Project Scan
        root_dir = root
        exclude_dirs, exclude_patterns = load_scan_exclusions(source_root=root_dir, cli_exclude=args.exclude)
        
        def should_include(p):
            import fnmatch
            try:
                rel_parts = p.relative_to(root_dir).parts[:-1]
            except Exception:
                rel_parts = p.parts[:-1]
            for part in rel_parts:
                if part in exclude_dirs:
                    return False
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(p.name, pattern):
                    return False
            return True
        
        html_files = sorted([p for p in root.rglob("*.html") if should_include(p)])

    ctx = BuildContext(root_dir, instr, mapping, enforcer)

    # Pre-populate registry from existing AST if provided
    if getattr(args, "existing_ast", None) and Path(args.existing_ast).exists():
        try:
            with open(args.existing_ast, "r", encoding="utf-8") as f:
                prev_ast = json.load(f)
            reparse_rel_set = {p.relative_to(root_dir).as_posix() for p in html_files}
            for n in prev_ast.get("nodes", []):
                fpath = n.get("file_path") or n.get("file") or (n["id"].split("::")[0] if "::" in n.get("id", "") else "")
                if fpath not in reparse_rel_set and n.get("id"):
                    ctx.registry[n["id"]] = n
        except Exception:
            pass
    
    # SCAN FILES
    print(f"Scanning {len(html_files)} files...")
    
    scanned = []  # (rel, content, template_id) — kept for the P1 template-relation second pass
    for p in html_files:
        try:
            rel = p.relative_to(root_dir).as_posix()
            content = p.read_text("utf-8")
            ctx.current_file = rel
            ctx.current_file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

            # File Node
            ctx.current_file_id = ctx.emit_node("Template", ctx.current_file, hash=ctx.current_file_hash)

            # Parse
            parser = StructureWalker(ctx)
            parser.feed(content)
            scanned.append((rel, content, ctx.current_file_id))

        except Exception as e:
            ctx.logs.append({"error": str(e), "file": str(p)})

    # ── P1 second pass: {% extends %}/{% include %} → Template→Template ──────────────
    # Runs AFTER every Template node is registered so a target resolves in-registry. Match the tag's
    # logical path to a physical Template by its /templates/-relative name (deterministic one-or-none;
    # a 3rd-party/absent target → an ambiguity, never a guess). Config: mapping.template_relations.
    _emit_template_relations(ctx, scanned)

    # ── P3 (dead-code-accuracy): inline <script> classList/querySelector → uses_style ──────────────
    _emit_inline_script_usage(ctx, scanned)

    # Output
    out_data = {
         "_meta": {
            "builder": "build_html_ast.py",
            "builder_version": instr.get("builder_identity", {}).get("version", "unknown"),
             "generated_at": datetime.datetime.now().isoformat()
        },
        "nodes": ctx.nodes,
        "edges": ctx.edges,
        "ambiguities": ctx.ambiguities,
        "logs": ctx.logs
    }
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
    print(f"Done. {len(ctx.nodes)} nodes, {len(ctx.edges)} edges.")

if __name__ == "__main__":
    main()
