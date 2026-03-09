from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sender_agent.models import JournalRecord, SenderTaskResultPayload
from sender_agent.task_journal import TaskJournal


def test_task_journal_tracks_and_replays_pending_result(tmp_path: Path) -> None:
    journal = TaskJournal(tmp_path / "sender.sqlite3")
    sent_at = datetime.fromisoformat("2026-03-08T08:00:00+08:00")
    payload = SenderTaskResultPayload(
        sender_id="sender-01",
        success=True,
        status="sent",
        retryable=False,
        sent_at=sent_at,
        detail={"chunk_count": 2},
    )

    record = journal.upsert(
        task_id="task-1",
        target_user="测试联系人",
        task_type="daily_report",
        status="result_pending",
        sent_chunks=2,
        result_payload=payload.model_dump(mode="json"),
    )

    assert record.status == "result_pending"
    pending = journal.list_pending_results()
    assert len(pending) == 1
    assert pending[0].task_id == "task-1"
    assert pending[0].payload["status"] == "sent"

    confirmed = journal.mark_result_confirmed("task-1")
    assert confirmed is not None
    assert confirmed.status == "result_confirmed"
    assert journal.list_pending_results() == []
