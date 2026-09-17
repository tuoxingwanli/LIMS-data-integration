"""Persistence operations for device detection sessions."""

import sqlite3


class DetectionSessionRepository:
    def latest(self, connection: sqlite3.Connection, blind_sample_no: str):
        return connection.execute(
            """
            SELECT * FROM detection_sessions
            WHERE blind_sample_no = ? ORDER BY id DESC LIMIT 1
            """,
            (blind_sample_no,),
        ).fetchone()

    def active(self, connection: sqlite3.Connection, blind_sample_no: str):
        return connection.execute(
            """
            SELECT * FROM detection_sessions
            WHERE blind_sample_no = ? AND status = 'recording'
            ORDER BY id DESC LIMIT 1
            """,
            (blind_sample_no,),
        ).fetchone()

    def create(
        self,
        connection: sqlite3.Connection,
        *,
        blind_sample_no: str,
        sample_id: int | None,
        started_at: str,
        capture_mode: str,
        recording_ref: str | None,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO detection_sessions
                (blind_sample_no, sample_id, status, started_at,
                 recording_ref, capture_mode)
            VALUES (?, ?, 'recording', ?, ?, ?)
            """,
            (blind_sample_no, sample_id, started_at, recording_ref, capture_mode),
        )
        return int(cursor.lastrowid)

    def create_failed(
        self,
        connection: sqlite3.Connection,
        *,
        blind_sample_no: str,
        sample_id: int | None,
        started_at: str,
        capture_mode: str,
        error_message: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO detection_sessions
                (blind_sample_no, sample_id, status, started_at,
                 capture_mode, error_message)
            VALUES (?, ?, 'failed', ?, ?, ?)
            """,
            (blind_sample_no, sample_id, started_at, capture_mode, error_message),
        )

    def stop(
        self,
        connection: sqlite3.Connection,
        session_id: int,
        *,
        ended_at: str,
        screenshot_ref: str | None,
    ) -> None:
        connection.execute(
            """
            UPDATE detection_sessions
            SET status = 'stopped', ended_at = ?, screenshot_ref = ?,
                updated_at = CURRENT_TIMESTAMP, error_message = NULL
            WHERE id = ?
            """,
            (ended_at, screenshot_ref, session_id),
        )
