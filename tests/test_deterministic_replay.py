import unittest
from server import analyse, demo_flight_events, flight_events_to_records
from investigation_graph import reconstruct_as_of

class DeterministicReplayTests(unittest.TestCase):
    def test_same_as_of_snapshot_has_identical_analysis_twice(self):
        records = flight_events_to_records(demo_flight_events())
        snapshot = reconstruct_as_of(records, records[-1]["timestamp"])
        self.assertEqual(analyse(snapshot), analyse(snapshot))

if __name__ == '__main__': unittest.main()
