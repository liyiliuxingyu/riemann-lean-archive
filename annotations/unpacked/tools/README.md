# Streaming annotation splitter

`split_annotations.cpp` decompresses one already-downloaded Zstandard annotation volume into ordinary text chunks. Each chunk contains complete pairs of one `-- @line N` annotation and its following original NDJSON line. It preserves every input byte, including CRLF and an explicitly allowed final original line without LF.

## Build

Requires a C++17 compiler, libzstd, and OpenSSL libcrypto development files:

```bash
g++ -O3 -DNDEBUG -std=c++17 -Wall -Wextra -Wpedantic split_annotations.cpp -lzstd -lcrypto -o split_annotations
```

## Parent-process interface

```text
split_annotations --source INPUT.txt.zst --out EXISTING_EMPTY_DIRECTORY --first FIRST --last LAST --max-bytes 50331648 [--allow-final-no-lf]
```

Only pass `--allow-final-no-lf` for the last original volume. The chunk budget must be positive and strictly below 100 MiB. An individual record pair exceeding the budget causes an explicit failure; the program never silently cuts a pair in half.

Standard output is newline-delimited JSON. For each closed chunk it prints and flushes:

```json
{"type":"chunk","file":"chunk0001.txt","bytes":123,"sha256":"...","first_line":1,"last_line":2,"records":2}
```

The parent must read and verify the chunk, import it into its destination (for example with `git hash-object -w`), remove this temporary chunk file, and send exactly `ok\n` to the child's standard input. The splitter checks that the temporary file has been removed before proceeding. It creates files with exclusive creation and rejects existing names rather than overwriting them. Thus only one temporary chunk occupies disk at a time.

On successful completion it emits one final JSON object with `type: complete` and these fields:

- `first_line`, `last_line`, `records`, `chunks`;
- `annotated_bytes`, `annotated_sha256`;
- `original_bytes`, `original_sha256`;
- `maximum_record_pair_bytes`;
- `compressed_bytes_read`, `zstd_frames`, `last_original_has_lf`.

Any error is written to standard error and exits nonzero. Previously acknowledged chunks do not make a failed volume complete. The parent must require both a successful final event and exit code 0, compare the result with the trusted original volume manifest, and only then publish a commit containing that complete volume.

The parent is responsible for verifying the compressed file's SHA-256 and size before invocation. The splitter itself validates Zstandard frame completion, consecutive canonical source line numbers, nonempty annotation text, strict annotation/original alternation, basic JSON object boundaries, byte totals, and hashes. It does not fully parse the JSON bodies, validate the mathematical meaning of annotations, or run Lean.

The in-memory chunk is at most the configured limit, as is the temporary record pair buffer. The other principal buffers are 4 MiB input, 4 MiB decompressed output, and approximately 8 MiB for batch hashing original text. Memory use remains bounded independently of the volume's total size.

## Tests

The test driver requires Python 3, the `zstd` CLI, and the real 147,492-record toolkit sample plus its compressed sibling:

```bash
python3 test_split_annotations.py --sample /path/to/solution_annotated.part001.txt
```

It independently reconstructs all emitted chunks and compares exact bytes and hashes. Cases cover 22 real-sample chunks, a non-1 starting line, exact pair-sized budgets, CRLF preservation, allowed and forbidden missing final LF, bad sequence numbers, empty annotation, missing original, invalid JSON boundaries, oversized pairs, range mismatch, no-overwrite behavior, rejected acknowledgement, undeleted acknowledged chunks, truncated Zstandard, trailing garbage, concatenated frames, and lines crossing decompressor buffers.

The saved `test_results.json` records the actual test run, whose scope is chunking and integrity rather than mathematical proof checking.
