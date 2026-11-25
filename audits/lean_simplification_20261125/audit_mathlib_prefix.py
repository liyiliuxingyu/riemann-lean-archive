#!/usr/bin/env python3
"""Report, but never edit, leading-Mathlib imports with an order-preserving relay.

Input is audit_imports.py output.  The model uses explicit plain-header module
edges, treats external modules as opaque, and assumes Lean imports dependencies
before importers.  It is not a compiler or a claim about arbitrary metaprograms
that inspect direct-import metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read_jsonl(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def import_targets(row):
    return [entry[0] for entry in row["imports"]]


def candidates(rows):
    result = {}
    for source, row in rows.items():
        imports = row["imports"]
        if not row["ordinary_legacy_header"] or len(imports) < 2 or imports[0] != ["Mathlib", []]:
            continue
        via = imports[1][0]
        if via in rows and rows[via]["ordinary_legacy_header"] and rows[via]["imports"] and rows[via]["imports"][0] == ["Mathlib", []]:
            result[source] = via
    return result


def postorder(roots, graph):
    visited, active, result = set(), set(), []
    for root in roots:
        if root in visited:
            continue
        stack = [(root, False)]
        while stack:
            node, closing = stack.pop()
            if closing:
                active.remove(node)
                visited.add(node)
                result.append(node)
                continue
            if node in visited:
                continue
            if node in active:
                raise ValueError(f"cycle at {node}")
            active.add(node)
            stack.append((node, True))
            for child in reversed(graph.get(node, [])):
                if child not in visited:
                    stack.append((child, False))
    return result


def trace_hash(sequence):
    return hashlib.sha256(("\n".join(sequence) + "\n").encode()).hexdigest()


def main(args):
    rows = {row["module"]: row for row in read_jsonl(args.audit / "import_graph.jsonl")}
    original_candidates = candidates(rows)
    changed_after_stage1 = {}
    for row in read_jsonl(args.audit / "duplicate_changes.jsonl"):
        changed_after_stage1[row["path"]] = row["after_header"]["imports"]
    for row in rows.values():
        key = "project/lean/original/src/" + row["path"]
        if key in changed_after_stage1:
            row["imports"] = changed_after_stage1[key]
    after_stage1_candidates = candidates(rows)
    anchors, lengths = {}, {}
    for source in after_stage1_candidates:
        chain, current, seen = [], source, set()
        while current in after_stage1_candidates and current not in anchors:
            if current in seen:
                raise ValueError(f"candidate relay cycle at {current}")
            seen.add(current)
            chain.append(current)
            current = after_stage1_candidates[current]
        anchor, length = anchors.get(current, current), lengths.get(current, 0)
        for node in reversed(chain):
            length += 1
            anchors[node], lengths[node] = anchor, length
    for anchor in set(anchors.values()):
        assert anchor not in after_stage1_candidates
        assert rows[anchor]["imports"][0] == ["Mathlib", []]
    original_graph = {source: import_targets(row) for source, row in rows.items()}
    revised_graph = {source: imports[1:] if source in after_stage1_candidates else imports for source, imports in original_graph.items()}
    before_trace = postorder(["Main"], original_graph)
    after_trace = postorder(["Main"], revised_graph)
    assert before_trace == after_trace
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "mathlib_prefix_candidates.jsonl").open("w") as out:
        for source, via in sorted(after_stage1_candidates.items()):
            row = {"source": source, "path": rows[source]["path"], "proposed_import_to_remove": "Mathlib", "immediately_following_import": via, "eventual_unchanged_mathlib_anchor": anchors[source], "relay_length": lengths[source], "source_rewrite_performed": False, "lean_compilation_performed": False}
            out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {
        "candidate_files_before_duplicate_patch": len(original_candidates),
        "candidate_files_after_duplicate_patch": len(after_stage1_candidates),
        "newly_exposed_by_duplicate_patch": len(set(after_stage1_candidates) - set(original_candidates)),
        "unmodified_anchor_modules": len(set(anchors.values())),
        "max_relay_length": max(lengths.values(), default=0),
        "main_dfs_postorder_identical": before_trace == after_trace,
        "main_dfs_postorder_nodes": len(before_trace),
        "before_trace_sha256": trace_hash(before_trace),
        "after_trace_sha256": trace_hash(after_trace),
        "proof_model": "For a legacy plain source beginning [Mathlib, A, ...], if A begins [Mathlib, ...], deleting the first Mathlib preserves dependency-first DFS completion order from every dependency-closed initial loaded set. Simultaneous deletions terminate at unchanged Mathlib anchors because the internal graph is finite and acyclic; induction from those anchors preserves the order. The complete Main DFS trace was also compared before and after all modeled deletions.",
        "limits": [
            "No source rewritten; no Lean build or elaboration performed.",
            "External modules, including Mathlib and implicit Init, are opaque. Their implementation was not inspected by this script.",
            "The order model does not establish semantic equivalence of arbitrary elaborator extensions that observe direct-import metadata, nor unchanged build dependencies or trace metadata.",
            "This is a separate potentially large patch class and should pass a full pinned-toolchain build gate before integration.",
        ],
        "examples": [{"source": source, "via": after_stage1_candidates[source], "anchor": anchors[source], "relay_length": lengths[source]} for source in list(sorted(after_stage1_candidates))[:8]],
    }
    (args.output / "mathlib_prefix_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
