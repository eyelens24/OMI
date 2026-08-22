import time
import unittest

from server import analyse, demo_flight_events, flight_events_to_records


class DemoPerformanceTests(unittest.TestCase):
    def test_builtin_demo_analysis_finishes_promptly(self):
        records = flight_events_to_records(demo_flight_events())
        started = time.perf_counter()
        analyse(records)
        self.assertLess(time.perf_counter() - started, 5.0)

if __name__ == "__main__": unittest.main()
