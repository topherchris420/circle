"""Behavioral tests for evidence serialization and replay integrity."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from models.session_records import (
    SessionRecordError, canonical_record_bytes, compute_crc32c, load_session,
    seal_record, validate_record, validate_session,
)


def snapshot(sequence=0, timestamp=0, stream="SENSOR", payload=None):
    return seal_record({
        "schema_version": "2.1.0", "record_type": "SAMPLE_CHUNK", "provenance": "TEST",
        "device_time_start_us": timestamp, "device_time_end_us": timestamp,
        "status_flags": ["OK"], "stream_id": stream, "sequence": sequence,
        "payload": payload or {"ppg_red": 100.0 + sequence},
    })


class SessionIntegrityTest(unittest.TestCase):
    def test_castagnoli_known_vectors_and_canonical_order(self):
        self.assertEqual(compute_crc32c("123456789"), "E3069283")
        self.assertEqual(compute_crc32c(b""), "00000000")
        record = snapshot()
        reordered = dict(reversed(list(record.items())))
        self.assertEqual(canonical_record_bytes(record), canonical_record_bytes(reordered))
        validate_record(reordered)

    def test_sealing_does_not_mutate_or_share_input(self):
        original = snapshot()
        sealed = seal_record(original)
        sealed["payload"]["ppg_red"] = -1
        self.assertEqual(original["payload"]["ppg_red"], 100)

    def test_corruption_is_rejected(self):
        record = snapshot()
        record["payload"]["ppg_red"] += 1
        with self.assertRaisesRegex(SessionRecordError, "CRC-32C mismatch"):
            validate_record(record)

    def test_actual_schema_rejects_invalid_types_and_unknown_properties(self):
        for field, value in (("sequence", True), ("status_flags", ["OK", "OK"]),
                             ("stream_id", ""), ("extra", "unexpected"),
                             ("payload", {"ppg_red": "100"})):
            with self.subTest(field=field):
                record = snapshot()
                record[field] = value
                with self.assertRaises(SessionRecordError):
                    seal_record(record)

    def test_time_bounds_and_nonfinite_data_are_rejected(self):
        for field, value in (("device_time_end_us", -1), ("device_time_end_us", 1),
                             ("payload", {"ppg_red": float("nan")}),
                             ("payload", {"ppg_red": float("inf")})):
            record = snapshot()
            record[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(SessionRecordError):
                seal_record(record)

    def test_model_lineage_ranges_must_be_complete_and_nonoverlapping(self):
        base = {
            "schema_version": "2.0.0", "record_type": "MODEL_RESULT", "provenance": "MODEL_INFERRED",
            "device_time_start_us": 0, "device_time_end_us": 1,
            "status_flags": [], "source_stream_ids": ["SENSOR"],
            "source_sequence_ranges": [{"stream_id": "SENSOR", "first_sequence": 0, "last_sequence": 1}],
            "model": {"name": "model", "version": "1"},
        }
        validate_record(seal_record(base))
        bad_ranges = [[], [{"stream_id": "OTHER", "first_sequence": 0, "last_sequence": 1}],
                      [{"stream_id": "SENSOR", "first_sequence": 3, "last_sequence": 1}],
                      base["source_sequence_ranges"] * 2]
        for ranges in bad_ranges:
            with self.subTest(ranges=ranges), self.assertRaises(SessionRecordError):
                seal_record({**base, "source_sequence_ranges": ranges})

    def test_intervention_without_actuation_evidence_fails(self):
        record = snapshot()
        record.update(record_type="INTERVENTION", provenance="INTERVENTION", decision_id="D1")
        with self.assertRaises(SessionRecordError):
            seal_record(record)

    def test_session_sequence_and_time_validation(self):
        for second in (snapshot(0, 20), snapshot(2, 20), snapshot(1, 0)):
            with self.subTest(second=second), self.assertRaises(SessionRecordError):
                validate_session([snapshot(), second])
        validate_session([snapshot(40, 100), snapshot(41, 200)])

    def test_explicit_gap_accounts_for_missing_sequences(self):
        gap = seal_record({
            "schema_version": "2.1.0", "record_type": "GAP", "provenance": "TEST",
            "device_time_start_us": 10, "device_time_end_us": 10,
            "status_flags": [], "stream_id": "SENSOR", "dropped_first_sequence": 1,
            "dropped_last_sequence": 2, "cause": "test dropout",
        })
        validate_session([snapshot(), gap, snapshot(3, 30)])
        with self.assertRaises(SessionRecordError):
            validate_session([snapshot(), gap, snapshot(4, 40)])

    def test_loader_supports_object_array_and_ndjson(self):
        records = [snapshot(), snapshot(1, 20)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            for text, expected in ((json.dumps(records[0], indent=2), records[:1]),
                                   (json.dumps(records), records),
                                   ("\n".join(json.dumps(r) for r in records), records)):
                path.write_text(text)
                self.assertEqual(load_session(path), expected)

    def test_loader_rejects_duplicate_keys_malformed_empty_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            for text in ('{"sequence":0,"sequence":1}', '[]', '', '{', 'null', '{"x":NaN}'):
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(SessionRecordError):
                        load_session(path)
