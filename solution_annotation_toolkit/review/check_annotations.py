"""Independent bounded serialization review; this does not check Lean typing."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "review"
EXE = ROOT / "tools" / "annotate_ndjson"
FINAL = REVIEW / "final"
FINAL.mkdir(exist_ok=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(name, source):
    output = FINAL / (name + "_annotated.txt")
    summary = FINAL / (name + "_summary.json")
    with source.open("rb") as src, output.open("wb") as dst:
        run = subprocess.run(
            [str(EXE), "--stdout", "--state-dir", str(FINAL / (name + "_state")),
             "--summary", str(summary)],
            stdin=src, stdout=dst, stderr=subprocess.PIPE, check=True,
        )
    (FINAL / (name + "_stderr.log")).write_bytes(run.stderr)
    raw = source.read_bytes()
    annotated = output.read_bytes()
    annotated.decode("utf-8", errors="strict")
    raw_lines = raw.split(b"\n")
    restored = bytearray()
    pos = 0
    variants = {}
    representatives = {}
    records = 0
    for line_no, line in enumerate(raw_lines, 1):
        if line_no == len(raw_lines) and not line:
            break
        has_lf = line_no < len(raw_lines)
        end = annotated.index(b"\n", pos)
        comment = annotated[pos:end].decode("utf-8")
        assert comment.startswith(f"-- @line {line_no} "), (name, line_no)
        assert not any(ord(ch) < 32 or 127 <= ord(ch) <= 159 or ch in "\u2028\u2029"
                       for ch in comment), (name, line_no, "control in comment")
        pos = end + 1
        expected = line + (b"\n" if has_lf else b"")
        actual = annotated[pos:pos + len(expected)]
        assert actual == expected, (name, line_no, "original changed")
        restored.extend(actual)
        pos += len(actual)
        record = json.loads(line)
        kind = next(k for k in record if k not in {"in", "il", "ie"})
        variants[kind] = variants.get(kind, 0) + 1
        representatives.setdefault(kind, {"line": line_no, "comment": comment,
                                          "original": line.decode("utf-8")})
        records += 1
    assert pos == len(annotated), (name, "trailing output")
    assert bytes(restored) == raw
    engine = json.loads(summary.read_text())
    assert engine["original_sha256"] == sha(raw)
    assert engine["records"] == records
    assert engine["original_bytes"] == len(raw)
    assert engine["counts"] == variants
    (FINAL / (name + "_representatives.json")).write_text(
        json.dumps(representatives, ensure_ascii=False, indent=2) + "\n")
    return {
        "name": name, "source": str(source), "records": records,
        "variants": variants, "original_bytes": len(raw),
        "annotated_bytes": len(annotated), "original_sha256": sha(raw),
        "restored_sha256": sha(restored), "exact_byte_recovery": True,
        "utf8_valid": True, "one_annotation_per_original_lf_record": True,
        "comments_have_no_ascii_or_unicode_line_controls": True,
        "engine_summary_independently_matched": True,
    }


binary_hash = sha(EXE.read_bytes())
report = {
    "scope": "147492 complete actual prefix lines and two 33-line synthetic fixtures only",
    "binary_sha256": binary_hash,
    "source_sha256": sha((ROOT / "tools" / "annotate_ndjson.cpp").read_bytes()),
    "runs": [
        check("prefix", ROOT / "source" / "prefix.ndjson"),
        check("synthetic", REVIEW / "synthetic_all_variants.ndjson"),
        check("framing", REVIEW / "synthetic_framing.ndjson"),
    ],
    "not_performed": ["full-source annotation review", "Lean typing or kernel validation",
                      "mathematical validity or target theorem assessment"],
}
assert binary_hash == sha(EXE.read_bytes()), "Binary changed during review"
(REVIEW / "independent_review_final.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False))
