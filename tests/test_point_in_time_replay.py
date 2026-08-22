import unittest

from investigation_graph import reconstruct_as_of


class PointInTimeReplayTests(unittest.TestCase):
    def test_reconstruction_excludes_future_marks_and_exposes_known_count(self):
        records = [
            {"timestamp": "2026-08-21T09:30:00+00:00", "pnl": 1},
            {"timestamp": "2026-08-21T09:35:00+00:00", "pnl": 2},
            {"timestamp": "2026-08-21T09:40:00+00:00", "pnl": -50},
        ]
        replay = reconstruct_as_of(records, "2026-08-21T09:35:00+00:00")
        self.assertEqual([row["pnl"] for row in replay], [1, 2])

if __name__ == "__main__": unittest.main()
