"""
Spashta-CKG — Adapter Rules Governance Validator

PURPOSE
-------
This script validates that framework adapters (e.g., Django, FastAPI, HTMX)
conform strictly to Spashta-CKG governance rules.

It enforces the core architectural invariant:
    Adapters may override VALUES, never STRUCTURE.

Specifically, it ensures that:
1. Adapter rule files contain only keys defined in Core rules.
2. Adapter rule files include ALL required Core rule keys.
3. Adapter values match Core value types (with safe numeric flexibility).
4. Framework mappings reference only valid Core schema node types.
5. Adapter contracts use valid severity levels.
6. Governance metadata (_meta) is present and preserved.

WHAT THIS SCRIPT IS
-------------------
• A governance and consistency validator
• Framework-agnostic
• Language-agnostic
• Deterministic and machine-verifiable
• Safe to run in CI and automated agent workflows

WHAT THIS SCRIPT IS NOT
-----------------------
• NOT a builder
• NOT an adapter executor
• NOT a semantic or behavioral validator
• NOT an agent or enrichment engine

It validates structure and governance only.

WHO USES THIS
-------------
• Contributors before committing adapter changes
• CI pipelines enforcing architectural discipline
• Agents (indirectly), by consuming the validation report

OUTPUT
------
Produces a machine-readable JSON report indicating:
• framework name
• pass / fail status
• detailed violations and warnings

The report can be emitted to stdout or written to a file via --out.

DESIGN PRINCIPLE
----------------
When validation fails:
• The validator is NOT weakened
• Adapters are NOT allowed to invent keys
• Core vocabulary is reviewed and promoted deliberately if needed

This script exists to prevent architectural drift.

FUTURE ROADMAP (Micro-Improvements)
-----------------------------------
1. Support `--all` flag to validate all adapters in `adapters/` directory.
2. Include Core Version in report (read from `_meta.version`).
3. Distinct separation between Violations (Error) and Warnings (Info).
"""


import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CORE_RULES_DIR = BASE_DIR / "core" / "agent_rules"
ADAPTERS_DIR = BASE_DIR / "adapters"
SCHEMA_DIR = BASE_DIR / "core" / "software_schema"

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_keys_and_types(core_data: Dict, adapter_data: Dict, path_prefix: str = "") -> List[Dict]:
    violations = []
    # Ignore _meta for key logic, implicitly handled separately
    adapter_keys = set(k for k in adapter_data.keys() if k != "_meta")
    core_keys = set(k for k in core_data.keys() if k != "_meta")
    
    # 1. Check for Extra Keys (Forbidden)
    extra_keys = adapter_keys - core_keys
    for k in extra_keys:
        violations.append({
            "issue": "Unknown key",
            "key": f"{path_prefix}{k}",
            "details": "Key does not exist in Core Rules"
        })

    # 1.5 Check for Missing Keys (Required)
    missing_keys = core_keys - adapter_keys
    for k in missing_keys:
        violations.append({
            "issue": "Missing key",
            "key": f"{path_prefix}{k}",
            "details": "Required Core Rule key missing in Adapter"
        })

    # 2. Check Types for Shared Keys
    shared_keys = adapter_keys.intersection(core_keys)
    for k in shared_keys:
        core_val = core_data[k]
        adapter_val = adapter_data[k]
        
        # Recursive check for objects
        if isinstance(core_val, dict) and isinstance(adapter_val, dict):
            violations.extend(validate_keys_and_types(core_val, adapter_val, f"{path_prefix}{k}."))
        elif type(core_val) != type(adapter_val):
             # Allow float/int mismatch (Python considers them diff types)
             if isinstance(core_val, (int, float)) and isinstance(adapter_val, (int, float)):
                 pass
             else:
                violations.append({
                    "issue": "Type mismatch",
                    "key": f"{path_prefix}{k}",
                    "expected": type(core_val).__name__,
                    "found": type(adapter_val).__name__
                })
    return violations

def validate_meta_compliance(core_data: Dict, adapter_data: Dict, fname: str) -> List[Dict]:
    violations = []
    if "_meta" in core_data:
        if "_meta" not in adapter_data:
             violations.append({"file": fname, "issue": "Missing _meta", "details": "_meta block required for governance"})
    return violations

def validate_framework_mapping(mapping_data: Dict, nodes_schema: Dict) -> List[Dict]:
    violations = []
    # nodes.json keys are the node types
    valid_node_types = set(nodes_schema.keys()) 
    
    mappings = mapping_data.get("mappings", [])
    for idx, rule in enumerate(mappings):
        c_node = rule.get("core_node")
        if c_node and c_node not in valid_node_types:
             violations.append({
                "file": "framework_mapping.json",
                "issue": "Invalid Core Node",
                "key": f"mappings[{idx}].core_node",
                "value": c_node
            })

        # Extended Check: Warn if semantic_role is not a known Core Node Type
        sem_role = rule.get("semantic_role")
        if sem_role and sem_role not in valid_node_types:
             violations.append({ # Currently appended to violations effectively as a warning/error mix
                "file": "framework_mapping.json",
                "issue": "Unknown Semantic Role (Warning)",
                "key": f"mappings[{idx}].semantic_role",
                "value": sem_role,
                "details": "Role is not defined in core/software_schema/nodes.json"
            })
    return violations

def validate_contracts(contracts_data: Dict) -> List[Dict]:
    violations = []
    valid_severities = {"info", "warning", "error"}
    contracts = contracts_data.get("contracts", {})
    for role, contract in contracts.items():
        sev = contract.get("violation_severity")
        if sev and sev not in valid_severities:
             violations.append({
                "file": "adapter_contracts.json",
                "issue": "Invalid Severity",
                "key": f"contracts['{role}'].violation_severity",
                "value": sev
            })
    return violations

def validate_adapter(framework: str, output_file: str = None):
    adapter_path = ADAPTERS_DIR / framework
    report = {"framework": framework, "status": "pass", "violations": [], "warnings": []}
    
    # 1. Validate Rules against Core
    rule_files = ["agent_behavior_rules.json", "code_purity_rules.json", "architecture_boundary_rules.json"]
    for fname in rule_files:
        core_file = CORE_RULES_DIR / fname
        adapter_file = adapter_path / fname
        
        if not core_file.exists():
             report["violations"].append({"file": fname, "issue": "Missing Core Rule File", "details": "Core file not found in core/agent_rules/"})
             continue

        if not adapter_file.exists():
            continue 
            
        try:
            core_data = load_json(core_file)
            adapter_data = load_json(adapter_file)
            
            # Check Meta Compliance
            meta_errs = validate_meta_compliance(core_data, adapter_data, fname)
            for e in meta_errs:
                e["file"] = fname
                report["violations"].append(e)

            # Check Keys and Types
            errs = validate_keys_and_types(core_data, adapter_data)
            for e in errs:
                e["file"] = fname
                report["violations"].append(e)
                
        except Exception as e:
             report["violations"].append({"file": fname, "issue": "JSON Parse/Read Error", "details": str(e)})

    # 2. Validate Framework Mapping (Reference Validity)
    mapping_file = adapter_path / "framework_mapping.json"
    if mapping_file.exists():
        try:
            nodes_data = load_json(SCHEMA_DIR / "nodes.json")
            mapping_data = load_json(mapping_file)
            errs = validate_framework_mapping(mapping_data, nodes_data)
            report["violations"].extend(errs)
        except Exception as e:
             report["violations"].append({"file": "framework_mapping.json", "issue": "Error", "details": str(e)})

    # 3. Validate Contracts
    contracts_file = adapter_path / "adapter_contracts.json"
    if contracts_file.exists():
        try:
            contracts_data = load_json(contracts_file)
            errs = validate_contracts(contracts_data)
            report["violations"].extend(errs)
        except Exception as e:
            report["violations"].append({"file": "adapter_contracts.json", "issue": "Error", "details": str(e)})

    # Final Status
    if report["violations"]:
        report["status"] = "fail"
        
    # Output
    report_json = json.dumps(report, indent=2)
    
    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report_json)
            print(f"Validation report saved to: {output_file}")
        except Exception as e:
            print(f"Error writing report: {e}")
            print(report_json)
    else:
        print(report_json)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_adapter_rules.py <framework_name> [--out <file>]")
        sys.exit(1)
    
    framework = sys.argv[1]
    out_file = None
    
    # Basic arg parsing
    if len(sys.argv) >= 4 and sys.argv[2] == "--out":
        out_file = sys.argv[3]
        
    validate_adapter(framework, out_file)
