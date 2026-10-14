#!/usr/bin/env python3
"""Read-only structural checks for TASK.txt artifacts; no semantic evaluation."""

import argparse
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import sys


SCHEMA = "local-candidate-evaluation-v1"
ROW_KEYS = {"source_id", "segment_id", "start", "end", "type"}
TYPES = {"ad", "program", "unknown"}
ORIGINS = {"unverified_model_output", "synthetic_contract_fixture"}


class ContractError(ValueError):
    pass


def fail(message):
    raise ContractError(message)


def reject_constant(value):
    fail("non-finite JSON constant: " + value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_json(text):
    return json.loads(text, parse_constant=reject_constant,
                      object_pairs_hook=unique_object)


def load_json(path):
    return parse_json(Path(path).read_text(encoding="utf-8"))


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        fail(label + " must be a nonempty string")
    return value


def require_number(value, label):
    # bool subclasses int, so isinstance(value, (int, float)) is insufficient.
    if type(value) not in (int, float):
        fail(label + " must be a JSON number, not a boolean")
    if type(value) is float and not math.isfinite(value):
        fail(label + " must be finite")
    return value


def read_sources(path):
    data = load_json(path)
    # TASK.txt describes sources without prescribing a top-level schema/version.
    sources = data.get("sources") if isinstance(data, dict) else data
    if not isinstance(sources, list) or not sources:
        fail("input must contain a nonempty sources list (or be that list)")
    result = {}
    for index, source in enumerate(sources):
        label = "sources[{}]".format(index)
        if not isinstance(source, dict):
            fail(label + " must be an object")
        source_id = require_text(source.get("source_id"), label + ".source_id")
        require_text(source.get("channel"), label + ".channel")
        duration = require_number(source.get("duration"), label + ".duration")
        if duration <= 0:
            fail(label + ".duration must be positive")
        if source_id in result:
            fail("duplicate input source_id: " + source_id)
        result[source_id] = duration
    return result


def read_artifact(base, descriptor, label):
    if not isinstance(descriptor, dict):
        fail(label + " must contain path and sha256")
    relative = require_text(descriptor.get("path"), label + ".path")
    path = Path(relative)
    # Reject foreign-platform absolute paths too, including Windows drives/UNC.
    if (path.is_absolute() or PureWindowsPath(relative).drive
            or "\\" in relative or ":" in relative or ".." in path.parts):
        fail(label + ".path must be a portable relative path without traversal")
    resolved = (base / path).resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError:
        fail(label + ".path escapes the candidate directory (including symlinks)")
    if not resolved.is_file():
        fail(label + ".path must resolve to a regular file")
    expected = descriptor.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        fail(label + ".sha256 must be 64 hexadecimal characters")
    content = resolved.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected.lower():
        fail(label + ": SHA256 mismatch")
    rows = []
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), 1):
        if not line.strip():
            fail("{} line {} is blank".format(label, line_number))
        try:
            rows.append(parse_json(line))
        except (ValueError, UnicodeError) as exc:
            fail("{} line {}: {}".format(label, line_number, exc))
    return rows


def validate_rows(rows, source_id, duration, representation):
    if not rows:
        fail(representation + " must include rows covering the source")
    seen = set()
    previous_end = 0
    target_end = duration if representation == "raw" else math.floor(duration)
    for index, row in enumerate(rows):
        label = "{}[{}]".format(representation, index)
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            fail(label + " must have exactly source_id, segment_id, start, end, type")
        if row["source_id"] != source_id:
            fail(label + " has the wrong source_id")
        segment_id = require_text(row["segment_id"], label + ".segment_id")
        if segment_id in seen:
            fail(label + " repeats a segment_id")
        seen.add(segment_id)
        if not isinstance(row["type"], str) or row["type"] not in TYPES:
            fail(label + ".type must be ad, program or unknown")
        start = require_number(row["start"], label + ".start")
        end = require_number(row["end"], label + ".end")
        if start < 0 or end > target_end:
            fail(label + " extends outside the source duration")
        if end < start or (representation == "raw" and end == start):
            fail(label + " has an invalid interval length")
        if start != previous_end:
            fail(label + " is unsorted or introduces a gap/overlap")
        previous_end = end
    if previous_end != target_end:
        fail(representation + " does not cover the full source interval")


def verify_case(base, source_id, duration, case):
    if not isinstance(case, dict):
        fail("case must be an object")
    raw = read_artifact(base, case.get("raw"), "raw")
    floor = read_artifact(base, case.get("floor"), "floor")
    validate_rows(raw, source_id, duration, "raw")
    validate_rows(floor, source_id, duration, "floor")
    if len(raw) != len(floor):
        fail("raw/floor row counts differ; quantized zero-length rows must be retained")
    warnings = []
    for index, (raw_row, floor_row) in enumerate(zip(raw, floor)):
        for key in ("source_id", "segment_id", "type"):
            if raw_row[key] != floor_row[key]:
                fail("raw/floor row {} differs in {}".format(index, key))
        for key in ("start", "end"):
            if floor_row[key] != math.floor(raw_row[key]):
                fail("floor row {} {} is not math.floor(raw)".format(index, key))
        if floor_row["start"] == floor_row["end"]:
            warnings.append({"code": "QUANTIZATION_ZERO_LENGTH",
                             "source_id": source_id,
                             "segment_id": raw_row["segment_id"],
                             "message": "Retained floor row has zero duration; downstream scoring may be incompatible."})
    if math.floor(duration) != duration:
        warnings.append({"code": "QUANTIZATION_DURATION",
                         "source_id": source_id,
                         "message": "floor covers [0, floor(duration)]; its quantized end differs from raw duration."})
    causes = case.get("unknown_causes")
    if not isinstance(causes, dict):
        fail("unknown_causes must be an object, including when empty")
    unknown_ids = {row["segment_id"] for row in raw if row["type"] == "unknown"}
    if set(causes) != unknown_ids:
        fail("unknown_causes must contain exactly all unknown segment IDs")
    if any(not isinstance(value, str) or value not in {"technical", "semantic"}
           for value in causes.values()):
        fail("unknown_causes values must be technical or semantic")
    return {"source_id": source_id, "rows": len(raw),
            "unknown_rows": len(unknown_ids)}, warnings


def verify_artifacts(input_manifest, candidate_manifest):
    report = {"status": "failed", "scope": "artifact_structure_only",
              "semantic_accuracy": "NOT EVALUATED",
              "private_and_held_out_metrics": "NOT EVALUATED",
              "errors": [], "warnings": [], "sources": []}
    try:
        sources = read_sources(input_manifest)
        candidate_path = Path(candidate_manifest).resolve(strict=True)
        base = candidate_path.parent
        candidate = load_json(candidate_path)
        if not isinstance(candidate, dict) or candidate.get("schema") != SCHEMA:
            fail("candidate schema must be " + SCHEMA)
        require_text(candidate.get("candidate_id"), "candidate_id")
        origin = candidate.get("origin")
        if not isinstance(origin, str) or origin not in ORIGINS:
            fail("origin must be unverified_model_output or synthetic_contract_fixture")
        require_text(candidate.get("provenance_note"), "provenance_note")
        cases = candidate.get("cases")
        if not isinstance(cases, dict):
            fail("candidate cases must be an object")
        if set(cases) != set(sources):
            fail("source set mismatch: missing={} unexpected={}".format(
                sorted(set(sources) - set(cases)), sorted(set(cases) - set(sources))))
        for source_id, duration in sources.items():
            try:
                summary, warnings = verify_case(base, source_id, duration, cases[source_id])
                report["sources"].append(summary)
                report["warnings"].extend(warnings)
            except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
                report["errors"].append({"source_id": source_id, "message": str(exc)})
    except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
        report["errors"].append({"message": str(exc)})
    if not report["errors"]:
        report["status"] = "passed"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", required=True,
                        help="JSON sources list or object containing sources")
    parser.add_argument("--candidate-manifest", required=True)
    args = parser.parse_args(argv)
    report = verify_artifacts(args.input_manifest, args.candidate_manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
