from __future__ import annotations

from typing import Any
from uuid import uuid4

from market_loader.database.repositories import MarketRepository


class RecordingCursor:
    def __init__(self) -> None:
        self.query = ""
        self.parameters: tuple[Any, ...] = ()

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, parameters: tuple[Any, ...]) -> None:
        self.query = query
        self.parameters = parameters

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []


class RecordingConnection:
    def __init__(self) -> None:
        self.recording_cursor = RecordingCursor()

    def cursor(self) -> RecordingCursor:
        return self.recording_cursor


def test_run_validation_uses_exists_without_multiplying_objects() -> None:
    connection = RecordingConnection()
    run_id = uuid4()

    assert MarketRepository(connection).validation_objects(run_id=run_id) == []

    query = " ".join(connection.recording_cursor.query.split())
    assert "WHERE EXISTS (" in query
    assert "pp.result_manifest_id = dm.id" in query
    assert connection.recording_cursor.parameters == (run_id,)
