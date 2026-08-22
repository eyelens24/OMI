from time import perf_counter
from server import analyse, demo_flight_events, flight_events_to_records

records = flight_events_to_records(demo_flight_events())
for label, rows in (("full_demo", records), ("initial_loss_window", records[-160:])):
    start = perf_counter()
    analyse(rows)
    print(f"{label}: {len(rows)} records, {perf_counter() - start:.3f}s")
print(f"events: {len(demo_flight_events())}; records: {len(records)}")
