#!/usr/bin/env python3
"""Recheck original module imports. This is a source audit, not Lean elaboration."""
import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--exporter", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    spec = importlib.util.spec_from_file_location("bundle_format", args.exporter)
    fmt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fmt)
    records = []
    with args.index.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            if record.get("kind") == "source":
                records.append(record)
    names = [r["module"] for r in records]
    positions = {name: i for i, name in enumerate(names)}
    duplicates = len(names) - len(positions)
    dependencies = [[] for _ in names]
    importers = [[] for _ in names]
    indegree = [0 for _ in names]
    external = collections.Counter()
    unresolved = []
    syntax_errors = []
    edge_count = 0
    for i, r in enumerate(records):
        try:
            imports = fmt.parse_imports(args.project / r["path"])
        except Exception as e:
            syntax_errors.append({"path": r["path"], "error": str(e)})
            continue
        seen = set()
        for target, line, modifiers in imports:
            if target in positions:
                j = positions[target]
                if j not in seen:
                    seen.add(j)
                    dependencies[i].append(j)
                    importers[j].append(i)
                    indegree[i] += 1
                    edge_count += 1
            else:
                external[target] += 1
                if target.split(".")[0] not in fmt.DEFAULT_EXTERNAL:
                    unresolved.append({"path": r["path"], "line": line,
                                       "target": target, "modifiers": modifiers})
        if (i + 1) % 25000 == 0:
            print(f"Parsed {i + 1}/{len(names)} module headers", flush=True)
    queue = collections.deque(i for i, degree in enumerate(indegree) if degree == 0)
    consumed = 0
    while queue:
        i = queue.popleft()
        consumed += 1
        for j in importers[i]:
            indegree[j] -= 1
            if indegree[j] == 0:
                queue.append(j)
    remaining = [names[i] for i, degree in enumerate(indegree) if degree]
    closure = set()
    pending = [positions["Main"]] if "Main" in positions else []
    while pending:
        i = pending.pop()
        if i not in closure:
            closure.add(i)
            pending.extend(dependencies[i])
    shadowed = [name for name in names if name.split(".")[0] in fmt.DEFAULT_EXTERNAL]
    config_hashes = {}
    for name in ("lean-toolchain", "lakefile.toml", "lake-manifest.json"):
        p = args.project / name
        config_hashes[name] = {"bytes": p.stat().st_size,
                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    result = {
        "scope": "standard source module headers; excludes theorem elaboration and external dependency internals",
        "parser": "parse_imports from the supplied export_lean_bundle.py; same parser as archive creator",
        "module_count": len(names), "duplicate_module_names": duplicates,
        "internal_unique_import_edges": edge_count,
        "acyclic": consumed == len(names), "remaining_after_topological_removal": remaining,
        "unresolved_nonstandard_imports": unresolved,
        "header_parser_errors": syntax_errors,
        "external_imports": dict(sorted(external.items())),
        "modules_in_Main_transitive_import_closure": len(closure),
        "modules_outside_Main_import_closure": sorted(name for i, name in enumerate(names) if i not in closure),
        "source_modules_shadowing_external_roots": shadowed,
        "config_files": config_hashes,
        "lean_compilation_performed": False,
        "theorem_level_dependency_cycle_check_performed": False,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in
                      {"external_imports", "modules_outside_Main_import_closure", "config_files"}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
