"""build_js_ast.py — Spashta-CKG JavaScript builder (MVP vertical slice).

Spec: Spashta_2.1/spec/js-support.md (US-1). Answers one question end-to-end:
"if I rename window.fp.showToast, which files call it?" — by emitting File + Function
nodes and the core `calls` edge over a Tree-sitter parse of the project's .js files.

Design (mirrors build_python_ast.py):
  * Parser = tree-sitter (tree-sitter-javascript) — a C library with Python bindings, no
    Node.js runtime, error-tolerant. The "camera" walks the syntax tree and records facts.
  * DETERMINISM: a `calls` edge is emitted ONLY when the callee resolves to exactly one known
    definition (a static/literal target). A dynamic or unknown callee becomes an
    emit_ambiguity(confidence="unresolved") — never a guessed edge. Same input -> same fragment.
  * Two passes over the whole JS file set (one fragment): (1) register every File + Function
    definition; (2) resolve every call site against the registry and emit `calls`.

MVP scope only: function definitions (declaration / assigned function-or-arrow / object-literal
function-valued members) + call sites. DOM-selector, route, and event edges are Phase 2.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import tree_sitter_javascript as tsjs
    from tree_sitter import Language, Node, Parser
except ImportError:  # pragma: no cover - explicit, actionable failure
    sys.stderr.write(
        "build_js_ast: missing parser. Run: pip install tree-sitter tree-sitter-javascript\n"
    )
    sys.exit(2)

# ── paths (relative to this script) ───────────────────────────────────────
BUILDER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILDER_DIR.parent.parent
INSTRUCTIONS_PATH = BUILDER_DIR / "builder_js_instructions_for_builder_code_development.json"
MAPPING_PATH = BUILDER_DIR / "js_language_mapping.json"
CORE_EDGES_PATH = PROJECT_ROOT / "core/software_schema/edges.json"

# directories/files never scanned for source JS (defaults; extended by project/profile.json +
# builder_rules.json so the JS builder honors the SAME project exclusions as the Python/HTML builders).
_EXCLUDE_DIR_PARTS = {"node_modules", ".venv", "venv", "env", "Spashta-CKG", ".git", "staticfiles"}


def _excluded_dir_parts(source_root=None, cli_exclude=None) -> set:
    """The default JS exclusions UNION the project's declared exclusions — project/profile.json
    (`excluded.directories`) + builder_rules.json (`scan_policy.exclude_dirs`) + CLI overrides."""
    dirs = set(_EXCLUDE_DIR_PARTS)
    if cli_exclude:
        for d in str(cli_exclude).split(","):
            d_clean = d.strip()
            if d_clean:
                dirs.add(d_clean)

    rules_path = PROJECT_ROOT / "core" / "builder_rules.json"
    if rules_path.exists():
        try:
            dirs.update(json.loads(rules_path.read_text("utf-8")).get("scan_policy", {}).get("exclude_dirs", []))
        except Exception:
            pass

    candidates = []
    if source_root:
        sr = Path(source_root).resolve()
        candidates.extend([sr / "profile.json", sr / ".spashta" / "profile.json"])
    candidates.append(PROJECT_ROOT / "project" / "profile.json")

    for profile_path in candidates:
        if profile_path.exists():
            try:
                dirs.update(json.loads(profile_path.read_text("utf-8")).get("excluded", {}).get("directories", []))
                break
            except Exception:
                pass
    return dirs



# ── schema enforcement (same contract as the Python builder) ──────────────
class SchemaEnforcer:
    """Validates edge creation against the Core Schema (edges.json) + the language mapping."""

    def __init__(self, mapping: dict, edges_schema: dict):
        self.node_map: Dict[str, str] = mapping.get("node_mappings", {})
        self.edge_map: Dict[str, str] = mapping.get("edge_mappings", {})
        self.edge_rules: Dict[str, dict] = {}
        for category in edges_schema.values():
            if isinstance(category, dict):
                for name, rule in category.items():
                    if isinstance(rule, dict) and "from" in rule:
                        self.edge_rules[name] = rule

    def map_node_type(self, ast_type: str) -> str:
        return self.node_map.get(ast_type, ast_type)

    def get_core_edge_type(self, logical_name: str) -> Optional[str]:
        return self.edge_map.get(logical_name)  # None -> ambiguity (strict)

    def is_allowed(self, edge_type: str, src_type: str, dst_type: str) -> bool:
        rule = self.edge_rules.get(edge_type)
        if not rule:
            return False
        return src_type in rule.get("from", []) and dst_type in rule.get("to", [])


class BuildContext:
    """Central bus: registry of confirmed nodes + emitted edges + ambiguity tickets."""

    def __init__(self, schema: SchemaEnforcer, instructions: dict):
        self.schema = schema
        self.instructions = instructions
        self.registry: Dict[str, dict] = {}
        self.nodes: List[dict] = []
        self.edges: List[dict] = []
        self.ambiguities: List[dict] = []
        self.logs: List[dict] = []

    def register_node(self, node_id: str, node_data: dict) -> None:
        if node_id in self.registry:
            return
        self.registry[node_id] = node_data
        self.nodes.append(node_data)

    def emit_edge(self, logical_edge: str, src_id: str, dst_id: str, **metadata) -> None:
        src, dst = self.registry.get(src_id), self.registry.get(dst_id)
        if not src or not dst:
            return
        core_edge = self.schema.get_core_edge_type(logical_edge)
        if not core_edge:
            self.emit_ambiguity(
                "mapping_violation", logical_edge,
                f"Logical edge '{logical_edge}' not in js_language_mapping",
                src_id, confidence="structural_violation",
            )
            return
        if self.schema.is_allowed(core_edge, src["node_type"], dst["node_type"]):
            edge = {"edge": core_edge, "from": src_id, "to": dst_id}
            edge.update(metadata)
            self.edges.append(edge)
        else:
            self.emit_ambiguity(
                "schema_violation", f"{logical_edge} -> {core_edge}",
                f"Edge not allowed between {src['node_type']} and {dst['node_type']}",
                src_id, confidence="structural_violation",
            )

    def emit_ambiguity(self, kind: str, expression: str, reason: str, scope: str,
                       confidence: str = "unresolved") -> None:
        self.ambiguities.append({
            "id": str(uuid.uuid4()),
            "kind": kind,
            "source_file": scope.split("::")[0] if "::" in scope else scope,
            "source_scope": scope,
            "expression": expression,
            "reason": reason,
            "confidence": confidence,
            "resolver": self.instructions.get("ambiguity_policy", {}).get("default_resolver", "agent"),
        })


# ── helpers ───────────────────────────────────────────────────────────────
def _text(node: Node) -> str:
    return node.text.decode("utf-8", "replace")


def _file_id(rel: str) -> str:
    return f"File:{rel}"


def _fn_id(name: str, rel: str) -> str:
    # A namespaced/member function (window.fp.showToast) gets a GLOBAL name-based id so a call in
    # another file resolves to the same node. A bare local function is file-scoped (avoids collisions).
    return f"js::sym::{name}" if "." in name else f"{rel}::{name}"


def _event_id(name: str) -> str:
    # Global name-based id so a dispatcher and a listener of the same event share one Event node.
    return f"js::event::{name}"


_EVENT_LISTEN_METHODS = {"addEventListener"}
_EVENT_DISPATCH_METHODS = {"dispatchEvent"}
_DOM_ID_METHODS = {"getElementById"}
_DOM_CLASS_METHODS = {"getElementsByClassName"}
_DOM_QUERY_METHODS = {"querySelector", "querySelectorAll"}
# el.classList.add/remove/toggle('x') — a bare class NAME (not a selector). These method names are generic,
# so they only count as class usage when the callee is actually `<obj>.classList.<method>` (see _is_classlist).
_DOM_CLASSLIST_METHODS = {"add", "remove", "toggle"}


def _is_classlist_callee(callee: Node) -> bool:
    """True iff a call's callee is `<obj>.classList.<method>` — i.e. the callee's object is a
    member_expression whose property is `classList`. Guards the generic add/remove/toggle names."""
    if callee.type != "member_expression":
        return False
    obj = callee.child_by_field_name("object")
    if obj is None or obj.type != "member_expression":
        return False
    prop = obj.child_by_field_name("property")
    return prop is not None and _text(prop) == "classList"

# a single literal selector: ".class" or "#id" (nothing else — a combinator/attribute/multiple is dynamic)
_SIMPLE_CLASS = re.compile(r"^\.([A-Za-z_][\w-]*)$")
_SIMPLE_ID = re.compile(r"^#([A-Za-z_][\w-]*)$")
_BARE_NAME = re.compile(r"^[A-Za-z_][\w-]*$")


def _string_value(node: Optional[Node]) -> Optional[str]:
    """The literal content of a tree-sitter `string` node (event names carry no escapes)."""
    if node is None or node.type != "string":
        return None
    txt = _text(node)
    return txt[1:-1] if len(txt) >= 2 and txt[0] in "'\"`" else txt


def _callee_method(callee: Node) -> str:
    """Trailing method name of a callee: member_expression.property, else a bare identifier."""
    if callee.type == "member_expression":
        prop = callee.child_by_field_name("property")
        return _text(prop) if prop is not None else ""
    return _text(callee)


# ── definition collection (pass 1) ─────────────────────────────────────────
class DefCollector:
    """Walks a file's tree registering File + Function nodes; indexes them for call resolution."""

    def __init__(self, ctx: BuildContext, rel: str, defs_by_name: Dict[str, List[str]],
                 fn_node_ids: Dict[int, str]):
        self.ctx = ctx
        self.rel = rel
        self.file_id = _file_id(rel)
        self.defs_by_name = defs_by_name
        self.fn_node_ids = fn_node_ids  # ts-node-id -> registered function id (for scope attribution)

    def _register_fn(self, name: str, def_node: Node, fn_node: Node) -> None:
        node_id = _fn_id(name, self.rel)
        self.ctx.register_node(node_id, {
            "id": node_id,
            "node_type": self.ctx.schema.map_node_type("function_declaration"),  # -> Function
            "name": name,
            "lang": "js",
            "file": self.rel,
            "line": def_node.start_point[0] + 1,
        })
        self.defs_by_name.setdefault(name, [])
        if node_id not in self.defs_by_name[name]:
            self.defs_by_name[name].append(node_id)
        self.fn_node_ids[fn_node.id] = node_id
        self.ctx.emit_edge("defines_function", self.file_id, node_id)

    def walk(self, node: Node) -> None:
        t = node.type
        if t == "function_declaration":
            nm = node.child_by_field_name("name")
            if nm is not None:
                self._register_fn(_text(nm), node, node)
        elif t == "assignment_expression":
            self._handle_assignment(node)
        for child in node.children:
            self.walk(child)

    def _handle_assignment(self, node: Node) -> None:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None:
            return
        if left.type not in ("member_expression", "identifier"):
            return
        target = _text(left)
        if right.type in ("function_expression", "arrow_function"):
            self._register_fn(target, node, right)  # window.showToast = function(){}
        elif right.type == "object":
            self._register_object_members(target, right)  # window.fp = { showToast: fn, ... }

    def _register_object_members(self, prefix: str, obj: Node) -> None:
        for member in obj.children:
            if member.type == "pair":
                key = member.child_by_field_name("key")
                val = member.child_by_field_name("value")
                if key is not None and val is not None and val.type in ("function_expression", "arrow_function"):
                    self._register_fn(f"{prefix}.{_text(key)}", member, val)
            elif member.type == "method_definition":
                key = member.child_by_field_name("name")
                if key is not None:
                    self._register_fn(f"{prefix}.{_text(key)}", member, member)


# ── call collection (pass 2) ───────────────────────────────────────────────
class CallCollector:
    """Walks a file's tree: resolves call sites (`calls`) and event listen/dispatch (`registers_event_handler` / `dispatches_event`)."""

    def __init__(self, ctx: BuildContext, rel: str, defs_by_name: Dict[str, List[str]],
                 fn_node_ids: Dict[int, str], events: set, dom_targets: set):
        self.ctx = ctx
        self.rel = rel
        self.file_id = _file_id(rel)
        self.defs_by_name = defs_by_name
        self.fn_node_ids = fn_node_ids
        self.events = events  # distinct event names already registered as Event nodes (shared)
        self.dom_targets = dom_targets  # (node_type, name) DOM placeholders already registered (shared)

    def walk(self, node: Node, scope_id: str) -> None:
        # entering a registered function switches the enclosing scope (the call's source)
        if node.id in self.fn_node_ids:
            scope_id = self.fn_node_ids[node.id]
        if node.type == "call_expression":
            self._handle_call(node, scope_id)
        for child in node.children:
            self.walk(child, scope_id)

    def _event_node(self, name: str) -> str:
        eid = _event_id(name)
        if name not in self.events:
            self.events.add(name)
            self.ctx.register_node(eid, {
                "id": eid, "node_type": self.ctx.schema.map_node_type("event"),  # -> Event
                "name": name, "lang": "js",
            })
        return eid

    def _handle_event(self, node: Node, scope_id: str, kind: str, line: int) -> None:
        args = node.child_by_field_name("arguments")
        named = args.named_children if args is not None else []
        name: Optional[str] = None
        if kind == "listen":
            if named and named[0].type == "string":
                name = _string_value(named[0])  # addEventListener('evt', handler)
            # A handler passed BY REFERENCE (addEventListener('evt', init) — a bare identifier or a
            # dotted name, not an inline function()/arrow) IS a real call relationship: this scope's
            # execution hands the browser a function it later invokes. Without this, a named handler
            # looks "dead" (0 inbound calls) purely because it's never written as init() — the same
            # resolver _handle_call uses for a direct call, reused here so a callback reference is
            # never a silent miss AND never a guessed edge (multiple/no match -> the same ambiguity).
            if len(named) > 1 and named[1].type in ("identifier", "member_expression"):
                self._resolve_and_emit_call(_text(named[1]), scope_id, line)
        else:  # dispatch: new CustomEvent('evt') / new Event('evt') / a bare string
            if named:
                first = named[0]
                if first.type == "new_expression":
                    nargs = first.child_by_field_name("arguments")
                    nnamed = nargs.named_children if nargs is not None else []
                    if nnamed and nnamed[0].type == "string":
                        name = _string_value(nnamed[0])
                elif first.type == "string":
                    name = _string_value(first)
        if name is None:  # a variable event name / event object -> not a static target
            self.ctx.emit_ambiguity(
                "unresolved_event", kind, f"{kind} with a non-literal event name",
                f"{self.rel}::L{line}", confidence="unresolved",
            )
            return
        logical = "registers_event_handler" if kind == "listen" else "dispatches_event"
        self.ctx.emit_edge(logical, scope_id, self._event_node(name), event_line=line, event=name)

    def _dom_node(self, node_type: str, name: str) -> str:
        # id WITHOUT "::" and WITHOUT file_path -> the merger canonicalises to `{type}:{name}`, so this
        # placeholder UNIFIES with the CSS StyleClass/StyleID of the same name (the cross-language link).
        nid = f"{node_type}:{name}"
        if (node_type, name) not in self.dom_targets:
            self.dom_targets.add((node_type, name))
            self.ctx.register_node(nid, {
                "id": nid, "node_type": node_type, "name": name, "lang": "css",
                "provisional": True,  # emitted by the JS builder; the CSS builder is the definer
            })
        return nid

    def _handle_dom(self, node: Node, scope_id: str, method: str, line: int) -> None:
        args = node.child_by_field_name("arguments")
        named = args.named_children if args is not None else []
        if not named or named[0].type != "string":
            return  # a dynamic (variable) selector -> not a static target; stay silent (no guess)
        sel = _string_value(named[0]) or ""
        node_type: Optional[str] = None
        name: Optional[str] = None
        if method in _DOM_ID_METHODS and _BARE_NAME.match(sel):
            node_type, name = "StyleID", sel
        elif (method in _DOM_CLASS_METHODS or method in _DOM_CLASSLIST_METHODS) and _BARE_NAME.match(sel):
            node_type, name = "StyleClass", sel
        elif method in _DOM_QUERY_METHODS:
            mc, mi = _SIMPLE_CLASS.match(sel), _SIMPLE_ID.match(sel)
            if mc:
                node_type, name = "StyleClass", mc.group(1)
            elif mi:
                node_type, name = "StyleID", mi.group(1)
        if node_type is None or name is None:
            # a complex/compound selector (combinator, attribute, multiple) -> ambiguity, never a guess
            self.ctx.emit_ambiguity(
                "unresolved_selector", sel, f"{method} with a non-simple selector",
                f"{self.rel}::L{line}", confidence="unresolved",
            )
            return
        self.ctx.emit_edge("queries_dom", scope_id, self._dom_node(node_type, name),
                           dom_line=line, selector=sel)

    def _handle_call(self, node: Node, scope_id: str) -> None:
        callee = node.child_by_field_name("function")
        if callee is None or callee.type not in ("identifier", "member_expression"):
            return  # computed/dynamic callee -> not a static target
        line = node.start_point[0] + 1
        method = _callee_method(callee)
        if method in _EVENT_LISTEN_METHODS:
            self._handle_event(node, scope_id, "listen", line)
            return
        if method in _EVENT_DISPATCH_METHODS:
            self._handle_event(node, scope_id, "dispatch", line)
            return
        if method in _DOM_ID_METHODS or method in _DOM_CLASS_METHODS or method in _DOM_QUERY_METHODS:
            self._handle_dom(node, scope_id, method, line)
            return
        if method in _DOM_CLASSLIST_METHODS and _is_classlist_callee(callee):
            self._handle_dom(node, scope_id, method, line)  # el.classList.add('x') -> queries_dom StyleClass x
            return
        self._resolve_and_emit_call(_text(callee), scope_id, line)

    def _resolve_and_emit_call(self, name: str, scope_id: str, line: int) -> None:
        """Resolve a callee NAME (a direct `name(...)` invocation, OR a callback reference handed to
        `addEventListener` — see _handle_event) against the file's def registry and emit `calls`. A
        single match -> a deterministic edge; zero or multiple matches -> the SAME `unresolved_call`
        ambiguity either caller would have produced — never a guessed edge."""
        targets = self.defs_by_name.get(name)
        if not targets:  # try the trailing property (fp.showToast defined as window.fp.showToast)
            short = name.rsplit(".", 1)[-1]
            matches = [ids for k, ids in self.defs_by_name.items()
                       if k == short or k.endswith("." + short)]
            targets = [i for ids in matches for i in ids]
        if len(targets) == 1:
            self.ctx.emit_edge("calls", scope_id, targets[0], call_line=line, callee=name)
        else:
            reason = ("callee not found in the JS def registry (external/cross-language/dynamic)"
                      if not targets else f"callee '{name}' matches {len(targets)} definitions")
            self.ctx.emit_ambiguity(
                "unresolved_call", name, reason, f"{self.rel}::L{line}", confidence="unresolved",
            )


# ── discovery + main ───────────────────────────────────────────────────────
def _iter_js_files(root: Path, cli_exclude=None) -> List[Path]:
    """Recurse root collecting .js files, skipping excluded directories."""
    excluded = _excluded_dir_parts(source_root=root, cli_exclude=cli_exclude)
    out: List[Path] = []
    for p in root.rglob("*.js"):
        if not p.is_file():
            continue
        try:
            rel_parts = p.relative_to(root).parts[:-1]
        except Exception:
            rel_parts = p.parts[:-1]
        if any(part in excluded for part in rel_parts):
            continue
        out.append(p)
    return sorted(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Spashta JS builder")
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--files", default=None, help="Comma-separated specific files to parse relative to source-root")
    parser.add_argument("--existing-ast", default=None, help="Path to existing raw AST JSON for global symbol resolution")
    parser.add_argument("--out", default="runtime/fragment_js.json")
    parser.add_argument("--exclude", default=None, help="Comma-separated directories to exclude")
    args = parser.parse_args()

    instructions = json.loads(INSTRUCTIONS_PATH.read_text("utf-8"))
    mapping = json.loads(MAPPING_PATH.read_text("utf-8"))
    edges_schema = json.loads(CORE_EDGES_PATH.read_text("utf-8"))
    ctx = BuildContext(SchemaEnforcer(mapping, edges_schema), instructions)

    ts_parser = Parser(Language(tsjs.language()))

    root = Path(args.source_root).resolve()
    if getattr(args, "files", None):
        raw_files = [f.strip() for f in args.files.split(",") if f.strip()]
        files = [Path(f).resolve() if Path(f).is_absolute() else (root / f).resolve() for f in raw_files]
        files = sorted([p for p in files if p.exists() and p.suffix == ".js"])
        root_dir = root
    else:
        files = [root] if root.is_file() else _iter_js_files(root, cli_exclude=args.exclude)
        root_dir = root.parent if root.is_file() else root

    defs_by_name: Dict[str, List[str]] = {}

    # Pre-populate definitions from existing AST if provided
    if getattr(args, "existing_ast", None) and Path(args.existing_ast).exists():
        try:
            with open(args.existing_ast, "r", encoding="utf-8") as f:
                prev_ast = json.load(f)
            reparse_rel_set = {p.relative_to(root_dir).as_posix() for p in files}
            for n in prev_ast.get("nodes", []):
                fpath = n.get("file_path") or n.get("file") or (n["id"].split("::")[0] if "::" in n.get("id", "") else "")
                if fpath not in reparse_rel_set and n.get("id"):
                    ctx.registry[n["id"]] = n
                    if n.get("name"):
                        defs_by_name.setdefault(n["name"], []).append(n["id"])
        except Exception:
            pass

    # parse once; reuse the same tree for both passes (stable node ids for scope attribution)
    parsed: List[Tuple[str, "Node"]] = []
    for path in files:
        try:
            rel = path.relative_to(root_dir).as_posix()
            src = path.read_bytes()
            tree = ts_parser.parse(src)
            file_id = _file_id(rel)
            ctx.register_node(file_id, {
                "id": file_id, "node_type": ctx.schema.map_node_type("program"),  # -> File
                "name": rel, "lang": "js", "file": rel,
                "hash": hashlib.sha1(src).hexdigest(),
            })
            parsed.append((rel, tree.root_node))
        except Exception as exc:  # never let one bad file abort the run
            ctx.logs.append({"error": str(exc), "file": str(path)})

    defs_by_name: Dict[str, List[str]] = {}
    fn_node_ids: Dict[int, str] = {}
    events: set = set()  # distinct event names -> one shared Event node (couples dispatch + listen)
    dom_targets: set = set()  # (type, name) DOM placeholders -> unify with CSS StyleClass/StyleID at merge
    for rel, root_node in parsed:  # pass 1 — all definitions before any edge
        DefCollector(ctx, rel, defs_by_name, fn_node_ids).walk(root_node)
    for rel, root_node in parsed:  # pass 2 — resolve calls + event listen/dispatch + DOM queries
        CallCollector(ctx, rel, defs_by_name, fn_node_ids, events, dom_targets).walk(root_node, _file_id(rel))

    out_data = {
        "_meta": {
            "builder": "build_js_ast.py",
            "builder_version": instructions.get("builder_identity", {}).get("version", "unknown"),
            "schema_version": mapping.get("_meta", {}).get("supported_core_schema", "unknown"),
            "generated_at": datetime.datetime.now().isoformat(),
        },
        "nodes": ctx.nodes,
        "edges": ctx.edges,
        "ambiguities": ctx.ambiguities,
        "logs": ctx.logs,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
    print(f"Done. {len(ctx.nodes)} nodes, {len(ctx.edges)} edges, {len(ctx.ambiguities)} ambiguities.")


if __name__ == "__main__":
    main()
