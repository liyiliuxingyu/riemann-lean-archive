"""Independently check observed input fields against the pinned format specification.

This audits serialization, not typing or mathematical validity. It reads the
acquired complete-line prefix and writes an explicitly prefix-only report.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "format_spec.json").read_text())
SOURCE = HERE.parent / "source" / "prefix.ndjson"
TABLES = {"NameIdx": {0}, "LevelIdx": {0}, "ExprIdx": set()}
counts = Counter()
errors = []
line_number = 0


def fail(path, message):
    errors.append({"line": line_number, "path": path, "message": message})


def check(value, shape, path):
    if isinstance(shape, dict) and not isinstance(shape.get("type"), str):
        if not isinstance(value, dict):
            fail(path, "Expected object")
            return
        actual, expected = set(value), set(shape)
        if actual != expected:
            fail(path, {"unexpected": sorted(actual - expected), "missing": sorted(expected - actual)})
        for key in actual & expected:
            check(value[key], shape[key], path + "." + key)
        return
    typ = shape["type"] if isinstance(shape, dict) else shape
    if typ in SPEC["nested_structures"]:
        check(value, SPEC["nested_structures"][typ]["shape"], path)
    elif typ.startswith("Array<"):
        if not isinstance(value, list):
            fail(path, "Expected array")
            return
        for i, item in enumerate(value):
            check(item, typ[6:-1], f"{path}[{i}]")
    elif typ.startswith("Tuple<"):
        types = typ[6:-1].split(",")
        if not isinstance(value, list) or len(value) != len(types):
            fail(path, "Expected exact-size tuple")
            return
        for i, (item, item_type) in enumerate(zip(value, types)):
            check(item, item_type, f"{path}[{i}]")
    elif typ in TABLES or typ in ("Nat", "NameIdxDef", "LevelIdxDef", "ExprIdxDef"):
        if type(value) is not int or value < 0:
            fail(path, "Expected nonnegative integer, not float or bool")
        elif typ in TABLES and value not in TABLES[typ]:
            fail(path, f"Undefined {typ} {value}")
    elif typ == "Bool":
        if type(value) is not bool:
            fail(path, "Expected boolean")
    elif typ == "String":
        if type(value) is not str:
            fail(path, "Expected string")
    elif typ == "DecimalNatString":
        if type(value) is not str or re.fullmatch(r"[0-9]+", value) is None:
            fail(path, "Expected decimal natural-number string")
    elif typ == "Object<String,String>":
        if type(value) is not dict or any(type(k) is not str or type(v) is not str for k, v in value.items()):
            fail(path, "Expected string-to-string object")
    elif typ == "ReducibilityHints":
        if value not in ("opaque", "abbrev"):
            if type(value) is not dict or set(value) != {"regular"}:
                fail(path, "Unknown reducibility hint")
            elif type(value["regular"]) is not int or not 0 <= value["regular"] <= 2**32 - 1:
                fail(path, "regular must be UInt32 value")
    elif typ in SPEC["enums"]:
        if type(value) is not str or value not in SPEC["enums"][typ]:
            fail(path, f"Unknown {typ} enum")
    else:
        raise RuntimeError("Unsupported specification type: " + typ)


digest = hashlib.sha256()
with SOURCE.open("rb") as source:
    for line_number, raw in enumerate(source, 1):
        digest.update(raw)
        obj = json.loads(raw)
        keys = set(obj) - {"in", "il", "ie"}
        if len(keys) != 1:
            fail("$", "Expected exactly one variant")
            continue
        variant = next(iter(keys))
        counts[variant] += 1
        record = SPEC["record_variants"].get(variant)
        if record is None:
            fail("$", "Unknown variant " + variant)
            continue
        check(obj, record["shape"], "$")
        for key, table in record.get("defines", {}).items():
            idx = obj.get(key)
            if type(idx) is not int or idx < 0:
                continue
            if idx in TABLES[table]:
                fail("$." + key, f"Duplicate {table} {idx}")
            TABLES[table].add(idx)

report = {
    "scope": "Only complete-line acquired prefix, NOT full solution.ndjson",
    "source": "source/prefix.ndjson",
    "input_bytes": SOURCE.stat().st_size,
    "input_sha256": digest.hexdigest(),
    "source_line_range_inclusive": [1, line_number],
    "record_counts": dict(sorted(counts.items())),
    "observed_variant_count": len(counts),
    "supported_but_unobserved_variants": sorted(set(SPEC["record_variants"]) - set(counts)),
    "table_entry_counts_including_predefined": {k: len(v) for k, v in TABLES.items()},
    "error_count": len(errors),
    "errors": errors,
    "checks": ["all known field names and field types", "enum values", "natural literal string encoding", "all table references precede use", "no duplicate index definitions"],
    "not_performed": ["full-file download or checksum verification", "Lean expression type checking", "binder scope validation", "kernel verification", "target theorem identification or proof assessment"],
}
(HERE / "prefix_schema_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: v for k, v in report.items() if k != "errors"}, ensure_ascii=False))
if errors:
    print(json.dumps(errors[:10], ensure_ascii=False))
    raise SystemExit(1)
