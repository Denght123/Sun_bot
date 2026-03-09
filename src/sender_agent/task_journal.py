from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sender_agent.errors import PendingResultReport
from sender_agent.models import JournalRecord


class TaskJournal:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_journal (
                    task_id TEXT PRIMARY KEY,
                    target_user TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sent_chunks INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    result_payload TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_confirmed_at TEXT
                )
                """
            )

    def get(self, task_id: str) -> JournalRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM task_journal WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return self._to_record(row)

    def upsert(
        self,
        *,
        task_id: str,
        target_user: str,
        task_type: str,
        status: str,
        sent_chunks: int = 0,
        last_error: str | None = None,
        result_payload: dict[str, Any] | None = None,
        result_confirmed_at: datetime | None = None,
    ) -> JournalRecord:
        now = datetime.now().isoformat()
        current = self.get(task_id)
        created_at = current.created_at.isoformat() if current else now
        serialized_result = None
        if result_payload is not None:
            import json

            serialized_result = json.dumps(result_payload, ensure_ascii=False)
        elif current is not None and current.result_payload is not None:
            import json

            serialized_result = json.dumps(current.result_payload, ensure_ascii=False)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_journal (
                    task_id, target_user, task_type, status, sent_chunks, last_error,
                    result_payload, created_at, updated_at, result_confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    target_user = excluded.target_user,
                    task_type = excluded.task_type,
                    status = excluded.status,
                    sent_chunks = excluded.sent_chunks,
                    last_error = excluded.last_error,
                    result_payload = excluded.result_payload,
                    updated_at = excluded.updated_at,
                    result_confirmed_at = excluded.result_confirmed_at
                """,
                (
                    task_id,
                    target_user,
                    task_type,
                    status,
                    sent_chunks,
                    last_error,
                    serialized_result,
                    created_at,
                    now,
                    result_confirmed_at.isoformat() if result_confirmed_at else None,
                ),
            )
        record = self.get(task_id)
        assert record is not None
        return record

    def mark_result_confirmed(self, task_id: str) -> JournalRecord | None:
        current = self.get(task_id)
        if current is None:
            return None
        return self.upsert(
            task_id=task_id,
            target_user=current.target_user,
            task_type=current.task_type,
            status="result_confirmed",
            sent_chunks=current.sent_chunks,
            last_error=current.last_error,
            result_payload=current.result_payload,
            result_confirmed_at=datetime.now(),
        )

    def list_pending_results(self) -> list[PendingResultReport]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM task_journal WHERE status = 'result_pending' ORDER BY updated_at ASC"
            ).fetchall()

        reports: list[PendingResultReport] = []
        for row in rows:
            record = self._to_record(row)
            reports.append(
                PendingResultReport(
                    task_id=record.task_id,
                    payload=record.result_payload or {},
                    recorded_at=record.updated_at,
                )
            )
        return reports

    def _to_record(self, row: sqlite3.Row) -> JournalRecord:
        import json

        result_payload = json.loads(row["result_payload"]) if row["result_payload"] else None
        return JournalRecord(
            task_id=row["task_id"],
            target_user=row["target_user"],
            task_type=row["task_type"],
            status=row["status"],
            sent_chunks=int(row["sent_chunks"]),
            last_error=row["last_error"],
            result_payload=result_payload,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result_confirmed_at=datetime.fromisoformat(row["result_confirmed_at"]) if row["result_confirmed_at"] else None,
        )
