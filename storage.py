"""Small local persistence layer for replay and diagnosis history."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class InvestigationStore:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS investigations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    label TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    replay_json TEXT
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    decision TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS flight_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    strategy_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_timestamp TEXT NOT NULL,
                    symbol TEXT,
                    payload_json TEXT NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_flight_events_strategy_time ON flight_events(strategy_id, event_timestamp)")

    def connect(self):
        return sqlite3.connect(self.database_path)

    def save(self, label, parameters, summary, replay=None):
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO investigations (created_at, label, parameters_json, summary_json, replay_json) VALUES (?, ?, ?, ?, ?)",
                (created_at, label, json.dumps(parameters), json.dumps(summary), json.dumps(replay) if replay else None),
            )
        return cursor.lastrowid

    def recent(self, limit=20):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, created_at, label, parameters_json, summary_json, replay_json FROM investigations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row[0], "created_at": row[1], "label": row[2], "parameters": json.loads(row[3]),
                "summary": json.loads(row[4]), "replay": json.loads(row[5]) if row[5] else None,
            }
            for row in rows
        ]

    def save_review(self, source, target, decision):
        if decision not in {"accepted", "rejected"}:
            raise ValueError("Review decision must be accepted or rejected.")
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO reviews (created_at, source, target, decision) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), source, target, decision),
            )
        return cursor.lastrowid

    def append_flight_events(self, events):
        """Append only: duplicate event IDs are ignored, never overwritten."""
        received_at = datetime.now(timezone.utc).isoformat()
        added = 0
        with self.connect() as connection:
            for event in events:
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO flight_events
                    (received_at, event_id, strategy_id, event_type, event_timestamp, symbol, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (received_at, event["event_id"], event["strategy_id"], event["event_type"], event["timestamp"], event.get("symbol"), json.dumps(event["data"], sort_keys=True)),
                )
                added += cursor.rowcount
        return {"accepted": added, "duplicates": len(events) - added}

    def flight_events(self, strategy_id, start=None, end=None):
        clauses, parameters = ["strategy_id = ?"], [strategy_id]
        if start:
            clauses.append("event_timestamp >= ?")
            parameters.append(start)
        if end:
            clauses.append("event_timestamp <= ?")
            parameters.append(end)
        query = f"SELECT event_id, strategy_id, event_type, event_timestamp, symbol, payload_json FROM flight_events WHERE {' AND '.join(clauses)} ORDER BY event_timestamp, id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [{
            "event_id": row[0], "strategy_id": row[1], "event_type": row[2], "timestamp": row[3],
            "symbol": row[4], "data": json.loads(row[5]),
        } for row in rows]

    def flight_status(self, strategy_id=None):
        clauses, parameters = [], []
        if strategy_id:
            clauses.append("strategy_id = ?")
            parameters.append(strategy_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            count, latest = connection.execute(f"SELECT COUNT(*), MAX(event_timestamp) FROM flight_events{where}", parameters).fetchone()
            types = connection.execute(f"SELECT event_type, COUNT(*) FROM flight_events{where} GROUP BY event_type ORDER BY event_type", parameters).fetchall()
        return {"strategy_id": strategy_id, "events": count, "latest_event_timestamp": latest, "by_type": {event_type: total for event_type, total in types}}
