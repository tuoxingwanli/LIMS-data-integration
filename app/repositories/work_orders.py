"""Persistence operations for work orders, samples, and results."""

import json
import sqlite3
from typing import Any

from app.schemas.work_orders import ResultItem, WorkOrderIn


class WorkOrderRepository:
    def find_by_order_no(self, connection: sqlite3.Connection, order_no: str):
        return connection.execute(
            "SELECT * FROM work_orders WHERE order_no = ?", (order_no,)
        ).fetchone()

    def create(self, connection: sqlite3.Connection, data: WorkOrderIn) -> int:
        raw_json = json.dumps(data.model_dump(), ensure_ascii=False)
        cursor = connection.execute(
            """
            INSERT INTO work_orders
                (order_no, experimenter_id, project_name, status, raw_json)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (data.order_no, data.experimenter_id, data.project_name, raw_json),
        )
        work_order_id = cursor.lastrowid
        connection.executemany(
            """
            INSERT INTO samples (work_order_id, sample_no, sample_name)
            VALUES (?, ?, ?)
            """,
            [
                (work_order_id, sample.sample_no, sample.sample_name)
                for sample in data.samples
            ],
        )
        return int(work_order_id)

    def list_for_experimenter(self, connection: sqlite3.Connection, experimenter_id: str):
        return connection.execute(
            """
            SELECT * FROM work_orders
            WHERE experimenter_id = ? AND status IN ('pending', 'in_progress')
            ORDER BY created_at ASC, id ASC
            """,
            (experimenter_id,),
        ).fetchall()

    def samples_for_order(self, connection: sqlite3.Connection, work_order_id: int):
        return connection.execute(
            """
            SELECT sample_no, sample_name, status FROM samples
            WHERE work_order_id = ? ORDER BY id ASC
            """,
            (work_order_id,),
        ).fetchall()

    def sample_ids_for_order(self, connection: sqlite3.Connection, work_order_id: int) -> set[str]:
        return {
            row["sample_no"]
            for row in connection.execute(
                "SELECT sample_no FROM samples WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchall()
        }

    def find_sample_by_no(self, connection: sqlite3.Connection, sample_no: str):
        return connection.execute(
            "SELECT * FROM samples WHERE sample_no = ? ORDER BY id DESC LIMIT 1",
            (sample_no,),
        ).fetchone()

    def upsert_result(
        self,
        connection: sqlite3.Connection,
        work_order_id: int,
        result: ResultItem,
    ) -> None:
        raw_json = json.dumps(result.model_dump(), ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO test_results
                (work_order_id, sample_no, test_item, value, unit, raw_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(work_order_id, sample_no, test_item) DO UPDATE SET
                value = excluded.value,
                unit = excluded.unit,
                raw_json = excluded.raw_json,
                pushed_to_lims = 0
            """,
            (
                work_order_id,
                result.sample_no,
                result.test_item,
                str(result.value),
                result.unit,
                raw_json,
            ),
        )
        connection.execute(
            """
            UPDATE samples SET status = 'completed'
            WHERE work_order_id = ? AND sample_no = ?
            """,
            (work_order_id, result.sample_no),
        )

    def update_status(self, connection: sqlite3.Connection, work_order_id: int, status: str) -> None:
        connection.execute(
            """
            UPDATE work_orders
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, work_order_id),
        )

    def results_for_order(self, connection: sqlite3.Connection, work_order_id: int):
        return connection.execute(
            """
            SELECT sample_no, test_item, value, unit, pushed_to_lims, created_at
            FROM test_results WHERE work_order_id = ? ORDER BY id ASC
            """,
            (work_order_id,),
        ).fetchall()

    def push_payload_results(self, connection: sqlite3.Connection, work_order_id: int):
        return connection.execute(
            """
            SELECT sample_no, test_item, value, unit FROM test_results
            WHERE work_order_id = ? ORDER BY id ASC
            """,
            (work_order_id,),
        ).fetchall()

    def mark_pushed(self, connection: sqlite3.Connection, work_order_id: int) -> None:
        connection.execute(
            "UPDATE test_results SET pushed_to_lims = 1 WHERE work_order_id = ?",
            (work_order_id,),
        )
        self.update_status(connection, work_order_id, "pushed")
