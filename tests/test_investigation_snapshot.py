import unittest

from investigation_snapshot import make_snapshot


class InvestigationSnapshotTests(unittest.TestCase):
    def test_snapshot_id_is_stable_for_same_evidence_and_changes_with_as_of(self):
        records = [{"timestamp": "2026-08-21T09:30:00+00:00", "pnl": -1}]
        first = make_snapshot(records, "2026-08-21T09:30:00+00:00", "demo")
        second = make_snapshot(records, "2026-08-21T09:30:00+00:00", "demo")
        later = make_snapshot(records, "2026-08-21T09:35:00+00:00", "demo")
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertNotEqual(first["snapshot_id"], later["snapshot_id"])

if __name__ == "__main__": unittest.main()
