import unittest
from omi_core.imports import validate_event_bundle

class EventBundleImportTests(unittest.TestCase):
    def test_accepts_typed_local_event_bundle(self):
        result = validate_event_bundle({"events": [{"kind": "decision", "event_id": "d1", "timestamp": "2026-01-01T09:00:00Z", "model_version": "m1", "feature_snapshot_id": "f1", "available_at": "2026-01-01T08:00:00Z", "action": "BUY"}]})
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"], [])

    def test_rejects_unknown_or_unidentified_events(self):
        result = validate_event_bundle({"events": [{"kind": "mystery"}, {"kind": "fill"}]})
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(len(result["rejected"]), 2)
