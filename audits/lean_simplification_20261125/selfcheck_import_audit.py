#!/usr/bin/env python3
"""Adversarial header checks and independent BFS oracle for the audit graph."""
from pathlib import Path
import json
import random
import tempfile

from audit_imports import duplicate_patch, parse_header, transitive_candidates


def reach(start, graph, ordinary):
    found, todo = set(), [start]
    while todo:
        node = todo.pop()
        if node not in found:
            found.add(node)
            if ordinary[node]:
                todo.extend(graph[node])
    return found


def main():
    text = "/- import Fake /- import Nested -/ -/\nimport A\nimport B -- retained\nimport A\n\ndef x := \"import Bogus\"\n"
    header = parse_header(text)
    assert [i.target for i in header.imports] == ["A", "B", "A"]
    candidates, change, patch = duplicate_patch(text, header, "src/X.lean")
    assert len(candidates) == 1 and change["removed_lines"] == [4]
    assert all(change["invariants"].values())
    assert patch.count("-import A\n") == 1
    for text in ["module\nimport A\nimport A\n", "prelude\nimport A\nimport A\n", "public import A\npublic import A\n", "meta import A\nmeta import A\n", "import all A\nimport all A\n", "import A\nimport A -- shake: keep\n", "import A\nimport\n A\n"]:
        candidates, change, patch = duplicate_patch(text, parse_header(text), "src/X.lean")
        assert len(candidates) == 1 and not candidates[0]["proposed"] and change is None and not patch
    quoted = parse_header("import Foo.«A.B»\nimport Foo.«A.B»\n")
    assert [i.target for i in quoted.imports] == ["Foo.«A.B»", "Foo.«A.B»"]
    assert parse_header("import A\n/- only comments remain -/\n").body_token is None
    assert parse_header("/- import fake -/\ndef x := 1").body_token == "def"
    for invalid in ["import\n", "import A\n/- unterminated", "import «unterminated"]:
        try:
            parse_header(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"did not reject {invalid!r}")
    rng = random.Random(20261125)
    checked = 0
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        output = Path(folder) / "transitive.jsonl"
        for n in range(1, 90):
            graph = [rng.sample(range(i), min(i, rng.randrange(0, 10))) for i in range(n)]
            ordinary = [rng.random() > 0.15 for _ in range(n)]
            names = [str(i) for i in range(n)]
            expected = set()
            closures = [reach(i, graph, ordinary) for i in range(n)]
            for source, deps in enumerate(graph):
                if ordinary[source]:
                    for dep in deps:
                        if any(dep in closures[other] for other in deps if other != dep):
                            expected.add((source, dep))
            transitive_candidates(graph, ordinary, names, output)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            actual = {(int(row["source"]), int(row["redundant_direct_import"])) for row in rows}
            assert actual == expected, (n, actual ^ expected)
            for row in rows:
                source, via, target = int(row["source"]), int(row["also_directly_imported"]), int(row["redundant_direct_import"])
                assert via in graph[source] and target in graph[source] and via != target and target in closures[via]
            checked += len(expected)
    print(json.dumps({"header_cases_passed": True, "random_dags_compared_with_independent_bfs": 89, "transitive_witnesses_verified": checked}))


if __name__ == "__main__":
    main()
