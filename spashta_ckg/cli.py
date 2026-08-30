"""
Spashta CLI ('sp' / 'spashta') - Universal Command Line Interface for Humans and AI Agents.
Exposes all Spashta 2.1, 2.2, and 3.0 capabilities under one unified command.
"""

import sys
import json
import argparse
from pathlib import Path
from spashta_ckg.engine import CKG
import spashta_ckg.runtime.query_spashta as qs

def main():
    help_epilog = """
Supported Languages & Couplings (Auto-Detected):
  Languages:   Python (AST), JavaScript (Tree-sitter), HTML5, CSS3
  Frameworks:  Django, FastAPI, HTMX, Vanilla JS

Quickstart Workflow:
  1. (Optional) Initialize project directory exclusions:
     spashta_ckg init
     spashta_ckg init --exclude "misc,reference,legacy"

  2. View or edit excluded directories:
     spashta_ckg config
     spashta_ckg config --add-exclude "docs,fixtures"

  3. Scan & build CKG graph:
     spashta_ckg scan
     spashta_ckg scan --exclude "misc,legacy"

  4. Blast-radius impact analysis (pre-refactoring):
     spashta_ckg impact "MyFunctionOrClass" --depth 2 --json

  5. Inspect full-stack routes & dead code:
     spashta_ckg routes
     spashta_ckg dead-code css
"""

    parser = argparse.ArgumentParser(
        prog="spashta_ckg",
        description="Spashta CKG v3.0 - Full-Stack Code Knowledge Graph & Impact Engine",
        epilog=help_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Common arguments
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Output results in machine-readable JSON")
    common.add_argument("--project-dir", "-p", default=".", help="Target project root directory (default: .)")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. Project Initialization (3.0)
    p_init = subparsers.add_parser("init", parents=[common], help="Initialize a project profile.json with directory exclusions")
    p_init.add_argument("--exclude", "-e", help="Comma-separated directories to exclude (e.g. misc,tests,legacy)")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing profile.json if present")

    # 2. Configuration Management (3.0)
    p_cfg = subparsers.add_parser("config", parents=[common], help="View or update excluded directories")
    p_cfg.add_argument("--set-exclude", help="Set excluded directories (replaces current list)")
    p_cfg.add_argument("--add-exclude", help="Append directories to exclusion list (e.g. misc,docs)")

    # 3. Lifecycle & Scanning (3.0)
    p_scan = subparsers.add_parser("scan", aliases=["build"], parents=[common], help="Scan project across all languages and build/refresh CKG graph")
    p_scan.add_argument("--out", "-o", default=None, help="Output directory for CKG artifacts (default: <project_dir>/.spashta)")
    p_scan.add_argument("--exclude", "-e", default=None, help="Comma-separated directories to exclude during this scan")

    # 4. Impact Analysis (2.1, 2.2, 3.0)
    p_impact = subparsers.add_parser("impact", parents=[common], help="Calculate blast-radius: who depends on/calls this symbol?")
    p_impact.add_argument("node_id", help="Target symbol name or node ID")
    p_impact.add_argument("--depth", "-d", type=int, default=3, help="Max traversal depth (default: 3)")

    # 5. Dependencies (2.1, 2.2)
    p_deps = subparsers.add_parser("dependencies", aliases=["deps"], parents=[common], help="What does this symbol depend on? (Outgoing edges)")
    p_deps.add_argument("node_id", help="Target symbol name or node ID")
    p_deps.add_argument("--depth", "-d", type=int, default=3, help="Max traversal depth")

    # 6. Dead Code Audit (2.1, 2.2, 3.0)
    p_dead = subparsers.add_parser("dead-code", aliases=["dead"], parents=[common], help="Find unreferenced dead code across Python, JS, and CSS")
    p_dead.add_argument("language", nargs="?", choices=["css", "js", "py"], default=None, help="Optional language filter")

    # 7. Dead CSS & Keyframes (2.1, 2.2)
    p_dead_css = subparsers.add_parser("dead-css", parents=[common], help="Audit dead CSS classes and keyframes with dynamic usage safety")
    p_dead_css.add_argument("--kind", choices=["class", "keyframes", "all"], default="all", help="Target CSS item kind")

    # 8. Full-Stack Routes (2.2, 3.0)
    subparsers.add_parser("routes", parents=[common], help="List all full-stack routes with connected templates, views, and events")

    # 9. Call Graph (2.1)
    p_cg = subparsers.add_parser("call-graph", parents=[common], help="View function call relationships (callers and callees)")
    p_cg.add_argument("node_id", help="Target function or method name/ID")

    # 10. Search (2.1, 2.2)
    p_search = subparsers.add_parser("search", parents=[common], help="Search nodes by name, ID, or attributes")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("--type", "-t", default=None, help="Filter by node type (e.g. Function, Route, StyleClass)")
    p_search.add_argument("--app", help="Filter by Django/sub-app directory prefix")

    # 11. Locate (2.1, 2.2)
    p_locate = subparsers.add_parser("locate", parents=[common], help="Locate exact file path, start line, and end line of a symbol")
    p_locate.add_argument("node_id", help="Target symbol or node ID")

    # 12. Read Source (2.1)
    p_read = subparsers.add_parser("read", parents=[common], help="Read the actual source code of a node from disk")
    p_read.add_argument("node_id", help="Target symbol or node ID")

    # 13. Details (2.1)
    p_details = subparsers.add_parser("details", parents=[common], help="Get complete JSON metadata for a node")
    p_details.add_argument("node_id", help="Target symbol or node ID")

    # 14. Consumers (2.1)
    p_consumers = subparsers.add_parser("consumers", parents=[common], help="Find all ORM usage sites for a model (graph + grep hybrid)")
    p_consumers.add_argument("model_name", help="Django model class name")

    # 15. Scope Check (2.1)
    p_scope = subparsers.add_parser("scope-check", parents=[common], help="Verify analysis coverage before modifying code")
    p_scope.add_argument("node_id", help="Target node to check impact against")
    p_scope.add_argument("--analyzed", required=True, help="Comma-separated list of files already inspected")
    p_scope.add_argument("--depth", "-d", type=int, default=3, help="Impact depth")

    # 16. Class Usage (2.1, 2.2)
    p_cu = subparsers.add_parser("class-usage", parents=[common], help="Check where a specific CSS class is defined and used")
    p_cu.add_argument("name", help="CSS class name (e.g. .btn-primary or btn-primary)")

    # 17. Duplicate Styles (2.1, 2.2)
    subparsers.add_parser("dup-styles", parents=[common], help="Find classes defined across multiple files and identical keyframe blocks")

    # 18. List Files (2.1)
    p_lf = subparsers.add_parser("list-files", parents=[common], help="List all indexed source files in the project")
    p_lf.add_argument("--app", help="Filter by app folder")

    # 19. Stats (2.1, 2.2, 3.0)
    subparsers.add_parser("stats", parents=[common], help="Display comprehensive graph statistics and node breakdowns")

    # Global flags
    parser.add_argument("--json", action="store_true", help="Output results in machine-readable JSON")
    parser.add_argument("--project-dir", "-p", default=".", help="Target project root directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    project_root = Path(args.project_dir).resolve()

    # Handle init
    if args.command == "init":
        excl = [x.strip() for x in args.exclude.split(",")] if args.exclude else None
        try:
            p_file = CKG.init_profile(
                project_root=project_root,
                excluded_dirs=excl,
                force=args.force
            )
            if args.json:
                print(json.dumps({"status": "created", "path": str(p_file)}, indent=2))
            else:
                print(f"Initialized project profile at: {p_file}")
                cfg = CKG.get_profile_info(project_root=project_root)
                print(f"Excluded Dirs: {', '.join(cfg['excluded_directories'])}")
                print("\nRun 'spashta_ckg scan' to build your Code Knowledge Graph.")
        except FileExistsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    # Handle config
    if args.command == "config":
        set_excl = [x.strip() for x in args.set_exclude.split(",")] if args.set_exclude else None
        add_excl = [x.strip() for x in args.add_exclude.split(",")] if args.add_exclude else None

        if set_excl or add_excl:
            cfg = CKG.update_profile(
                project_root=project_root,
                set_exclude=set_excl,
                add_exclude=add_excl
            )
            if args.json:
                print(json.dumps(cfg, indent=2))
            else:
                print(f"Updated configuration in: {cfg['path']}")
                print(f"Excluded Dirs: {', '.join(cfg['excluded_directories'])}")
        else:
            cfg = CKG.get_profile_info(project_root=project_root)
            if args.json:
                print(json.dumps(cfg, indent=2))
            else:
                print(f"\nActive Profile:    {cfg['path']} {'(Custom)' if cfg['is_custom'] else '(Package Default)'}")
                print(f"Project Root:      {cfg['project_root']}")
                print(f"Excluded Dirs:      {', '.join(cfg['excluded_directories'])}")
                print("\nSupported Languages (Auto-Detected): Python, JavaScript, HTML, CSS")
                print("Supported Frameworks (Auto-Detected): Django, FastAPI, HTMX, Vanilla JS\n")
        sys.exit(0)

    # Handle scan / build
    if args.command in ("scan", "build"):
        excl = [x.strip() for x in args.exclude.split(",")] if getattr(args, "exclude", None) else None
        if not args.json:
            print(f"Scanning codebase at: {project_root}...")
        ckg = CKG.build(
            project_root=project_root,
            output_dir=args.out,
            excluded_dirs=excl
        )
        stats = ckg.stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(f"Scan complete! Indexed {stats['total_nodes']} nodes and {stats['total_edges']} edges.")
            print(f"Artifacts saved to: {project_root / '.spashta'}")
        sys.exit(0)

    # 2. Ensure CKG is available
    ckg_candidates = [
        project_root / ".spashta" / "code_knowledge_graph_enriched.json",
        project_root / "runtime" / "code_knowledge_graph_enriched.json",
        Path(__file__).resolve().parent / "runtime" / "code_knowledge_graph_enriched.json"
    ]
    graph_path = None
    for c in ckg_candidates:
        if c.exists():
            graph_path = c
            break

    if not graph_path:
        if not args.json:
            print(f"No existing CKG found for {project_root}. Running initial scan...")
        ckg = CKG.build(project_root=project_root)
        graph_path = project_root / ".spashta" / "code_knowledge_graph_enriched.json"

    # Load graph dict for runtime queries
    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    # Dispatch to battle-tested query implementations in query_spashta
    # Normalize args so query_spashta functions receive what they expect
    if not hasattr(args, "depth"): args.depth = 3
    if not hasattr(args, "kind"): args.kind = "all"
    if not hasattr(args, "app"): args.app = None

    if args.command == "routes":
        ckg = CKG(graph, project_root=project_root)
        res = ckg.routes()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"\nFull-Stack Routes ({len(res)} total):\n")
            rows = [
                [r['route'], ", ".join(r['views']) or "-", ", ".join(r['templates']) or "-", f"{r.get('file_path', '')}:{r.get('line_start', '')}"]
                for r in res
            ]
            # Formatted table
            col_w = [15, 20, 20, 20]
            if rows:
                col_w = [max(len(str(r[i])) for r in rows + [["Route", "Views", "Templates", "Defined In"]]) for i in range(4)]
            print(" | ".join(["Route".ljust(col_w[0]), "Views".ljust(col_w[1]), "Templates".ljust(col_w[2]), "Defined In".ljust(col_w[3])]))
            print("-+-".join("-" * col_w[i] for i in range(4)))
            for r in rows:
                print(" | ".join(str(r[i]).ljust(col_w[i]) for i in range(4)))

    elif args.command in ("dead-code", "dead"):
        ckg = CKG(graph, project_root=project_root)
        res = ckg.dead_code(language=args.language)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            lang_label = f" ({args.language.upper()})" if args.language else ""
            print(f"\nDead Code Candidates{lang_label}: {res['total_candidates']} found\n")
            for item in res["dead_items"][:50]:
                print(f"  - [{item['node_type']}] {item['name']} ({item.get('file_path', '')}:{item.get('line_start', '')})")
            if len(res["dead_items"]) > 50:
                print(f"... and {len(res['dead_items']) - 50} more. Use --json to see all.")

    else:
        # Call query_spashta handler directly with the loaded graph
        # Map node_id if argument is query / name
        if hasattr(args, "symbol") and not hasattr(args, "node_id"):
            args.node_id = args.symbol

        # Run query_spashta command logic
        cmd = args.command
        if cmd == "search":
            res = qs.smart_search(graph, args.query, getattr(args, "type", None), getattr(args, "app", None))
            if args.json:
                total_nodes = len(graph.get("nodes", []))
                qs.output({
                    "results": res,
                    "metadata": {
                        "total_matches": len(res),
                        "total_searched": total_nodes,
                        "query": args.query,
                        "type_filter": getattr(args, "type", None),
                        "app_filter": getattr(args, "app", None),
                    }
                }, True)
            else:
                qs.output(res, False)
        elif cmd == "locate":
            node = qs.get_node(graph, args.node_id)
            if node:
                fpath = node.get("file_path", "")
                if not fpath and "::" in node.get("id", ""):
                    fpath = node["id"].split("::")[0]
                    if fpath.startswith("File:"): fpath = fpath[5:]
                loc = {
                    "id": node["id"],
                    "file": fpath or node.get("name", "N/A"),
                    "line_start": node.get("line_start"),
                    "line_end": node.get("line_end"),
                    "node_type": node.get("node_type"),
                    "docstring": node.get("docstring")
                }
                qs.output(loc, args.json)
            else:
                qs.output(qs.node_not_found_response(graph, args.node_id), args.json)
        elif cmd == "read":
            qs.output(qs.read_content(graph, args.node_id), args.json)
        elif cmd == "details":
            node = qs.get_node(graph, args.node_id)
            qs.output(node if node else qs.node_not_found_response(graph, args.node_id), args.json)
        elif cmd == "impact":
            res = qs.trace_deps(graph, args.node_id, "incoming", args.depth)
            if args.json:
                coverage = qs.build_layer_coverage(res)
                qs.output({"results": res, **coverage}, True)
            else:
                qs.output(res, False)
        elif cmd in ("dependencies", "deps"):
            res = qs.trace_deps(graph, args.node_id, "outgoing", args.depth)
            qs.output(res, args.json)
        elif cmd == "call-graph":
            res = qs.get_call_graph(graph, args.node_id)
            qs.output(res, args.json)
        elif cmd == "stats":
            from collections import Counter
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            node_types = Counter(n.get("node_type", "Unknown") for n in nodes)
            edge_types = Counter()
            for e in edges:
                _, _, kind = qs.get_edge_endpoints(e)
                edge_types[kind or "Unknown"] += 1
            role_counts = Counter()
            for n in nodes:
                for r in n.get("semantic_roles", []):
                    role_counts[r] += 1
            stats = {
                "nodes": len(nodes),
                "edges": len(edges),
                "ambiguities": len(graph.get("ambiguities", [])),
                "node_types": dict(node_types.most_common()),
                "edge_types": dict(edge_types.most_common()),
                "semantic_roles": dict(role_counts.most_common()) if role_counts else {},
                "meta": graph.get("_meta", {})
            }
            qs.output(stats, args.json)
        elif cmd == "list-files":
            all_files = sorted({n.get("file_path") for n in graph.get("nodes", []) if n.get("file_path")})
            if args.app:
                all_files = [f for f in all_files if f.startswith(args.app + "/") or f.startswith(args.app + "\\")]
            if args.json:
                from collections import defaultdict
                grouped = defaultdict(list)
                for f in all_files:
                    app = f.split("/")[0] if "/" in f else "root"
                    grouped[app].append(f)
                qs.output({"total": len(all_files), "files_by_app": dict(grouped)}, True)
            else:
                qs.output(all_files, False)
        elif cmd == "scope-check":
            impact_results = qs.trace_deps(graph, args.node_id, "incoming", args.depth)
            analyzed_list = [f.strip() for f in args.analyzed.split(",") if f.strip()]
            production_files = {}
            for node_id, info in impact_results.items():
                layer = info.get("layer", qs.classify_layer(node_id))
                if layer != "test":
                    production_files[node_id] = {**info, "layer": layer}
            unanalyzed = {}
            for node_id, info in production_files.items():
                covered = any(a in node_id for a in analyzed_list)
                if not covered:
                    unanalyzed[node_id] = info
            total_prod = len(production_files)
            analyzed_count = total_prod - len(unanalyzed)
            coverage_pct = round(analyzed_count / total_prod * 100) if total_prod > 0 else 100
            verdict = "COMPLETE" if not unanalyzed else f"INCOMPLETE — {len(unanalyzed)} production file(s) not analyzed"
            result = {
                "target": args.node_id,
                "analyzed": analyzed_list,
                "total_production_files": total_prod,
                "analyzed_count": analyzed_count,
                "coverage_percent": coverage_pct,
                "verdict": verdict,
            }
            if unanalyzed:
                result["unanalyzed_production"] = unanalyzed
            qs.output(result, args.json)
        elif cmd == "consumers":
            res = qs.find_consumers(args.model_name, graph)
            qs.output(res, args.json)
        elif cmd == "dead-css":
            defines, style_users, anim_users, _ = qs._css_index(graph)
            dyn_text = qs._dynamic_class_text(graph)
            dead_classes, dynamic_classes, framework_classes, dead_kf = [], [], [], []
            for (tt, name), srcs in defines.items():
                if tt == "Keyframes":
                    if args.kind in ("keyframes", "all") and name not in anim_users:
                        dead_kf.append(name)
                    continue
                if args.kind not in ("class", "all") or name in style_users:
                    continue
                base = name.rsplit("--", 1)[0] if "--" in name else None
                var_modifier = bool(base) and (base + "--{{" in dyn_text or base + "--{%" in dyn_text)
                if any(name.startswith(p) for p in qs._FRAMEWORK_CLASS_PREFIXES):
                    framework_classes.append(name)
                elif name in dyn_text or var_modifier:
                    dynamic_classes.append(name)
                else:
                    dead_classes.append(name)
            res = {
                "dead_classes": sorted(dead_classes),
                "dynamically_referenced": sorted(dynamic_classes),
                "framework": sorted(framework_classes),
                "dead_keyframes": sorted(dead_kf),
                "counts": {"classes": len(dead_classes), "dynamically_referenced": len(dynamic_classes),
                           "framework": len(framework_classes), "keyframes": len(dead_kf)}
            }
            qs.output(res, args.json)
        elif cmd == "class-usage":
            defines, style_users, _, _ = qs._css_index(graph)
            name = args.name.lstrip(".")
            res = {
                "class": name,
                "defined_in": sorted(defines.get(("StyleClass", name), [])),
                "used_by": sorted(style_users.get(name, [])),
                "used": bool(style_users.get(name))
            }
            qs.output(res, args.json)
        elif cmd == "dup-styles":
            defines, _, _, kf_hashes = qs._css_index(graph)
            dup_classes = {name: sorted(srcs) for (tt, name), srcs in defines.items()
                           if tt == "StyleClass" and len(srcs) > 1}
            identical_kf = [sorted(names) for names in kf_hashes.values() if len(names) > 1]
            res = {
                "classes_defined_in_multiple_files": dict(sorted(dup_classes.items())),
                "identical_keyframes": identical_kf,
                "counts": {"dup_classes": len(dup_classes), "identical_keyframe_groups": len(identical_kf)}
            }
            qs.output(res, args.json)

if __name__ == "__main__":
    main()
