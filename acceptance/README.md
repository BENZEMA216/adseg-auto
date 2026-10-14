# Artifact contract verifier / 交付文件合同检查

独立、只读、仅 Python 标准库的结构验收工具。它没有分割算法，不读取视频、帧、ASR、GT 或凭据，不调用模型或网络。通过只表示所检查的文件合同一致；语义准确率、私有集和盲测始终标为 `NOT EVALUATED`。

This is a standalone, read-only standard-library verifier, not the segmentation pipeline. It reads only the supplied source manifest, candidate manifest and referenced raw/floor JSONL files. It never evaluates media, ground truth, semantic accuracy or model execution claims.

## Run

From the repository root:

```sh
python3 -B acceptance/verify_artifacts.py \
  --input-manifest path/to/input.json \
  --candidate-manifest path/to/candidate_manifest.json

python3 -B -m unittest discover -s acceptance -p 'test_*.py' -v
```

Output is a JSON report on stdout. Exit code `0` means structural checks passed (possibly with quantization warnings), `1` means checks failed, and argparse uses `2` for invalid command arguments. No output files are created or overwritten.

## Input and artifact contract

The input uses the `source_id`, `channel` and positive finite `duration` fields already listed in `TASK.txt`. No new schema/version field is required. The verifier accepts `{"sources": [...]}` or the sources array directly because TASK.txt does not prescribe a top-level container. Other input fields are left untouched and are not validated or opened.

Minimal input example (an interface illustration, not evaluation data):

```json
{"sources":[{"source_id":"example","channel":"synthetic","duration":2.5}]}
```

Checked constraints:

- Candidate schema, candidate ID, declared origin, provenance note and exact input/candidate source set.
- Artifact paths are relative to the candidate manifest, contain no traversal or platform-specific absolute form, and resolve inside its directory, including symlink resolution. SHA256 is checked before JSONL parsing.
- Every JSONL row has exactly the five fields in TASK.txt. IDs are nonempty and unique within each source. Raw intervals have positive length, start at zero, share exact adjacent stored endpoints, and end at that source's duration. No tolerance, clipping or repair is applied.
- Floor keeps the same row order, IDs and types; every endpoint equals `math.floor` of its raw counterpart. It covers `[0, floor(duration)]`. Zero-length floor rows remain present and produce `QUANTIZATION_ZERO_LENGTH` warnings. A fractional source duration also produces `QUANTIZATION_DURATION`.
- `unknown_causes` contains exactly the unknown row IDs, with `technical` or `semantic` values. Empty maps are required when there are no unknowns.
- NaN, Infinity, numeric overflow to infinity, boolean times/durations, duplicate JSON keys, missing/extra sources, duplicate IDs, blank JSONL rows, gaps and overlaps are rejected.

## Limits / 局限

Hashes bind files to a declared manifest; they do not authenticate a provider, prove semantic correctness or prevent an author from replacing both a file and its declared hash. Stable IDs are checked within the delivered raw/floor pair, not across independent runs. The verifier does not inspect receipts, evidence ledgers, costs, native-frame provenance or the rest of TASK.txt's implementation requirements.

Use a trusted frozen input manifest when checking completeness. A synthetic fixture can pass all structural checks without solving advertisement segmentation. Quantization warnings are retained for local evaluation; the verifier neither deletes short units nor declares them acceptable to an external scorer. The files should remain unchanged during verification; this is not an adversarial concurrent-filesystem sandbox.
