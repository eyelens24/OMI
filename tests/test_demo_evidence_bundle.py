import json
import unittest
from pathlib import Path
from omi_core.imports import validate_event_bundle
from omi_core.ledger import ledger_for_records
from omi_core.ai_forensics import assess_ai_decision

class DemoEvidenceBundleTests(unittest.TestCase):
    def test_ai_rationale_demo_has_reconciled_lifecycle_and_detected_contradiction(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "ai-rationale-contradiction.json"
        bundle = json.loads(path.read_text())
        imported = validate_event_bundle(bundle)
        self.assertEqual(imported["accepted"], 6)
        self.assertFalse(imported["rejected"])
        self.assertIsNone(ledger_for_records(imported["events"])["first_break"])
        decision = next(event for event in imported["events"] if event["kind"] == "decision")
        self.assertEqual(assess_ai_decision(decision)["status"], "contradicted")
