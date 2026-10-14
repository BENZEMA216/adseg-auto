import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verify_artifacts import verify_artifacts


class ArtifactContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "delivery"
        self.bundle.mkdir()
        self.inputs = self.root / "input.json"
        self.manifest = self.bundle / "candidate_manifest.json"
        self.source_data = {"sources": [
            {"source_id": "a", "channel": "synthetic", "duration": 3.5},
            {"source_id": "b", "channel": "synthetic", "duration": 2},
        ]}
        self.rows = {
            "a": [self.row("a", "a1", 0, .4, "ad"),
                  self.row("a", "a2", .4, 2, "program"),
                  self.row("a", "a3", 2, 3.5, "unknown")],
            "b": [self.row("b", "b1", 0, 2, "unknown")],
        }
        self.candidate = {"schema": "local-candidate-evaluation-v1",
                          "candidate_id": "synthetic_test", "origin": "synthetic_contract_fixture",
                          "provenance_note": "Generated tempfile contract fixture", "cases": {}}
        for source_id, rows in self.rows.items():
            self.candidate["cases"][source_id] = {
                "raw": self.write_rows(source_id + "_raw.jsonl", rows),
                "floor": self.write_rows(source_id + "_floor.jsonl", [
                    dict(row, start=math.floor(row["start"]), end=math.floor(row["end"]))
                    for row in rows]),
                "unknown_causes": {row["segment_id"]: "technical" for row in rows
                                   if row["type"] == "unknown"}}
        self.save()

    @staticmethod
    def row(source, segment, start, end, kind):
        return {"source_id": source, "segment_id": segment,
                "start": start, "end": end, "type": kind}

    def write_rows(self, name, rows):
        content = "".join(json.dumps(row) + "\n" for row in rows).encode()
        (self.bundle / name).write_bytes(content)
        return {"path": name, "sha256": hashlib.sha256(content).hexdigest()}

    def save(self):
        self.inputs.write_text(json.dumps(self.source_data))
        self.manifest.write_text(json.dumps(self.candidate))

    def check(self):
        self.save()
        return verify_artifacts(self.inputs, self.manifest)

    def assert_failure(self, text):
        result = self.check()
        self.assertEqual(result["status"], "failed", result)
        self.assertIn(text, " ".join(item["message"] for item in result["errors"]))

    def replace_rows(self, representation, rows, source="a"):
        self.candidate["cases"][source][representation] = self.write_rows(
            source + "_" + representation + ".jsonl", rows)

    def test_valid_quantization_preserves_all_rows_and_warns(self):
        result = self.check()
        self.assertEqual(result["status"], "passed", result)
        zero = [w for w in result["warnings"] if w["code"] == "QUANTIZATION_ZERO_LENGTH"]
        self.assertEqual([(w["source_id"], w["segment_id"]) for w in zero], [("a", "a1")])
        self.assertEqual(result["sources"][0]["rows"], 3)
        self.assertEqual(result["semantic_accuracy"], "NOT EVALUATED")
        self.assertEqual(result["private_and_held_out_metrics"], "NOT EVALUATED")

    def test_top_level_source_array_needs_no_added_schema(self):
        self.source_data = self.source_data["sources"]
        self.assertEqual(self.check()["status"], "passed")

    def test_missing_and_extra_source(self):
        saved = self.candidate["cases"].pop("b")
        self.assert_failure("source set mismatch")
        self.candidate["cases"]["b"] = saved
        self.candidate["cases"]["extra"] = saved
        self.assert_failure("unexpected=['extra']")

    def test_hash_tamper_is_detected_before_parsing(self):
        (self.bundle / "a_raw.jsonl").write_text("not-json\n")
        self.assert_failure("SHA256 mismatch")

    def test_relative_and_absolute_path_escape(self):
        for value in ("../outside.jsonl", "/tmp/outside.jsonl", "C:\\outside.jsonl", "https://example.test/a"):
            with self.subTest(path=value):
                self.candidate["cases"]["a"]["raw"]["path"] = value
                self.assert_failure("relative path")

    def test_symlink_escape(self):
        outside = self.root / "outside.jsonl"
        outside.write_bytes((self.bundle / "a_raw.jsonl").read_bytes())
        (self.bundle / "link.jsonl").symlink_to(outside)
        self.candidate["cases"]["a"]["raw"]["path"] = "link.jsonl"
        self.assert_failure("escapes")

    def test_unknown_causes_missing_extra_or_wrong(self):
        for value in ({}, {"a3": "technical", "a1": "semantic"}, {"a3": "failed"}):
            with self.subTest(causes=value):
                self.candidate["cases"]["a"]["unknown_causes"] = value
                self.assert_failure("unknown_causes")

    def test_nan_infinity_and_boolean_times(self):
        for value in (float("nan"), float("inf"), -float("inf"), True, False):
            with self.subTest(value=value):
                rows = [dict(row) for row in self.rows["a"]]
                rows[0]["start"] = value
                self.replace_rows("raw", rows)
                self.assertEqual(self.check()["status"], "failed")

    def test_exponent_overflow_and_boolean_duration(self):
        path = self.bundle / "a_raw.jsonl"
        text = path.read_text().replace('"start": 0', '"start": 1e999', 1)
        path.write_text(text)
        self.candidate["cases"]["a"]["raw"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assert_failure("finite")
        self.source_data["sources"][0]["duration"] = True
        self.assert_failure("not a boolean")

    def test_floor_zero_length_row_cannot_be_deleted(self):
        rows = [dict(row, start=math.floor(row["start"]), end=math.floor(row["end"]))
                for row in self.rows["a"]][1:]
        self.replace_rows("floor", rows)
        self.assert_failure("row counts differ")

    def test_floor_correspondence_ids_types_and_flooring(self):
        for field, value in (("segment_id", "changed"), ("type", "ad"), ("end", 1)):
            with self.subTest(field=field):
                rows = [dict(row, start=math.floor(row["start"]), end=math.floor(row["end"]))
                        for row in self.rows["a"]]
                rows[1][field] = value
                if field == "end":
                    rows[2]["start"] = value  # Remains gap-free, but no longer floor(raw).
                self.replace_rows("floor", rows)
                self.assertEqual(self.check()["status"], "failed")

    def test_raw_gap_overlap_and_incomplete_end(self):
        for field, value in (("start", .5), ("start", .3), ("end", 3)):
            with self.subTest(field=field, value=value):
                rows = [dict(row) for row in self.rows["a"]]
                rows[1 if field == "start" else 2][field] = value
                self.replace_rows("raw", rows)
                self.assertEqual(self.check()["status"], "failed")

    def test_duplicate_segment_id_and_extra_field(self):
        rows = [dict(row) for row in self.rows["a"]]
        rows[1]["segment_id"] = "a1"
        self.replace_rows("raw", rows)
        self.assert_failure("repeats a segment_id")
        rows[1]["segment_id"] = "a2"
        rows[1]["score"] = 1
        self.replace_rows("raw", rows)
        self.assert_failure("exactly")

    def test_wrong_schema_and_origin(self):
        self.candidate["schema"] = "other"
        self.assert_failure("candidate schema")
        self.candidate["schema"] = "local-candidate-evaluation-v1"
        self.candidate["origin"] = "verified_private_accuracy"
        self.assert_failure("origin must")

    def test_duplicate_json_key(self):
        self.save()
        self.manifest.write_text('{"schema":"x","schema":"y"}')
        report = verify_artifacts(self.inputs, self.manifest)
        self.assertEqual(report["status"], "failed")
        self.assertIn("duplicate JSON key", report["errors"][0]["message"])

    def test_cli_exit_and_read_only_behavior(self):
        script = Path(__file__).with_name("verify_artifacts.py")
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        args = [sys.executable, "-B", str(script), "--input-manifest", str(self.inputs),
                "--candidate-manifest", str(self.manifest)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")
        after = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.candidate["cases"].pop("b")
        self.save()
        failed = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(json.loads(failed.stdout)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
