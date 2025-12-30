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

def load_scan_exclusions():
    """Loads exclusion rules from builder_rules.json."""
    exclude_dirs = set([".venv", "__pycache__"])  # Defaults
    exclude_patterns = []
    if BUILDER_RULES_PATH.exists():
        try:
            rules = json.loads(BUILDER_RULES_PATH.read_text("utf-8"))
            policy = rules.get("scan_policy", {})
            exclude_dirs.update(policy.get("exclude_dirs", []))
            exclude_patterns = policy.get("exclude_file_patterns", [])            
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
        
        for rules in self.mapping.get("tag_interactions", {}).values():
            for rule in rules:
                self._allowed_mapping_edges.add(rule["emits_edge"])

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
            if rule["attribute"] in attr_dict:
                self._process_interaction(rule, attr_dict[rule["attribute"]], line_number, context_attrs)

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
        
        target_id = self.ctx.emit_node(target_type, value, line_start=line_number, attributes=context_attrs) # Confidence handled inside
        
        self.ctx.emit_edge(
            edge_type, 
            self.ctx.current_file_id, 
            target_id, 
            "Template", 
            target_type
        )

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--out", default="runtime/code_knowledge_graph_html.json")
    args = parser.parse_args()

    root = Path(args.source_root).resolve()
    
    # Load Configuration
    # Load Configuration
    try:
        instr = json.loads(INSTRUCTIONS_PATH.read_text("utf-8"))
        mapping = json.loads(MAPPING_PATH.read_text("utf-8"))
        edges_schema = json.loads(CORE_EDGES_PATH.read_text("utf-8"))
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    # Initialize Components
    enforcer = SchemaEnforcer(edges_schema) # Mapping    enforcer = SchemaEnforcer(edges_schema)
    
    # SCAN FILES (Support Single File or Directory)
    if root.is_file():
        # Case: Unit Test or Single File Scan
        root_dir = root.parent
        html_files = [root]
    else:
        # Case: Project Scan
        root_dir = root
        exclude_dirs, exclude_patterns = load_scan_exclusions()
        
        def should_include(p):
            import fnmatch
            for part in p.parts:
                if part in exclude_dirs:
                    return False
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(p.name, pattern):
                    return False
            return True
        
        html_files = sorted([p for p in root.rglob("*.html") if should_include(p)])

    ctx = BuildContext(root_dir, instr, mapping, enforcer)
    
    # SCAN FILES
    print(f"Scanning {len(html_files)} files...")
    
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
            
        except Exception as e:
            ctx.logs.append({"error": str(e), "file": str(p)})

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
