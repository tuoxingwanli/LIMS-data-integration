"""LIMS / SCADA 数据对接 Demo。

业务闭环：LIMS 下发工单 -> SCADA 获取工单 -> SCADA 上传结果 -> 回推 LIMS。
"""

import json
import os
import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("LIMS_DB_PATH", str(BASE_DIR / "lims_demo.db")))
LIMS_RESULT_URL = os.getenv(
    "LIMS_RESULT_URL",
    "http://127.0.0.1:8000/mock/lims/results",
)


def get_db() -> sqlite3.Connection:
    """创建启用外键约束的 SQLite 连接。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    """初始化原型所需的三张业务表。"""
    with closing(get_db()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT UNIQUE NOT NULL,
                experimenter_id TEXT NOT NULL,
                project_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'in_progress', 'completed', 'pushed')),
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                sample_no TEXT NOT NULL,
                sample_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'completed')),
                FOREIGN KEY (work_order_id) REFERENCES work_orders(id),
                UNIQUE (work_order_id, sample_no)
            );

            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                sample_no TEXT NOT NULL,
                test_item TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT,
                raw_json TEXT NOT NULL,
                pushed_to_lims INTEGER NOT NULL DEFAULT 0
                    CHECK (pushed_to_lims IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (work_order_id) REFERENCES work_orders(id),
                UNIQUE (work_order_id, sample_no, test_item)
            );

            CREATE INDEX IF NOT EXISTS idx_work_orders_assignee_status
                ON work_orders(experimenter_id, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_samples_work_order
                ON samples(work_order_id);
            CREATE INDEX IF NOT EXISTS idx_results_work_order
                ON test_results(work_order_id);
            """
        )
        connection.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="LIMS / SCADA Integration Demo",
    description="用于验证 LIMS 工单、SCADA 实验结果及 LIMS 回推的最小闭环。",
    version="0.1.0",
    lifespan=lifespan,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SampleIn(StrictModel):
    sample_no: str = Field(min_length=1)
    sample_name: str | None = None


class WorkOrderIn(StrictModel):
    order_no: str = Field(min_length=1)
    experimenter_id: str = Field(min_length=1)
    project_name: str | None = None
    samples: list[SampleIn] = Field(min_length=1)
    test_items: list[str] = Field(default_factory=list)

    @field_validator("samples")
    @classmethod
    def sample_numbers_must_be_unique(cls, samples: list[SampleIn]) -> list[SampleIn]:
        numbers = [sample.sample_no for sample in samples]
        if len(numbers) != len(set(numbers)):
            raise ValueError("同一工单中的 sample_no 不能重复")
        return samples

    @field_validator("test_items")
    @classmethod
    def normalize_test_items(cls, items: list[str]) -> list[str]:
        normalized = [item.strip() for item in items]
        if any(not item for item in normalized):
            raise ValueError("test_items 不能包含空字符串")
        if len(normalized) != len(set(normalized)):
            raise ValueError("test_items 不能重复")
        return normalized


class ResultItem(StrictModel):
    sample_no: str = Field(min_length=1)
    test_item: str = Field(min_length=1)
    value: str | float | int
    unit: str | None = None


class ResultUpload(StrictModel):
    order_no: str = Field(min_length=1)
    results: list[ResultItem] = Field(min_length=1)
    finished: bool = True

    @field_validator("results")
    @classmethod
    def result_keys_must_be_unique(cls, results: list[ResultItem]) -> list[ResultItem]:
        keys = [(item.sample_no, item.test_item) for item in results]
        if len(keys) != len(set(keys)):
            raise ValueError("同一次上传中的样品和检测项目组合不能重复")
        return results


@app.get("/health", tags=["系统"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/work-orders", tags=["LIMS 工单"])
def receive_work_order(data: WorkOrderIn) -> dict[str, Any]:
    """接收 LIMS 下发的工单；重复工单号按幂等成功返回。"""
    with closing(get_db()) as connection:
        old = connection.execute(
            "SELECT id FROM work_orders WHERE order_no = ?",
            (data.order_no,),
        ).fetchone()
        if old:
            return {
                "success": True,
                "duplicate": True,
                "message": "工单已经存在",
                "order_no": data.order_no,
            }

        try:
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
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise HTTPException(status_code=500, detail="工单保存失败") from exc

    return {
        "success": True,
        "duplicate": False,
        "order_no": data.order_no,
        "message": "工单接收成功",
    }


@app.get("/api/scada/work-orders", tags=["SCADA"])
def get_scada_work_orders(experimenter_id: str) -> dict[str, Any]:
    """按实验人员唯一 ID 返回待处理及进行中的工单。"""
    if not experimenter_id.strip():
        raise HTTPException(status_code=422, detail="experimenter_id 不能为空")

    with closing(get_db()) as connection:
        orders = connection.execute(
            """
            SELECT * FROM work_orders
            WHERE experimenter_id = ? AND status IN ('pending', 'in_progress')
            ORDER BY created_at ASC, id ASC
            """,
            (experimenter_id.strip(),),
        ).fetchall()

        response = []
        for order in orders:
            samples = connection.execute(
                """
                SELECT sample_no, sample_name, status FROM samples
                WHERE work_order_id = ? ORDER BY id ASC
                """,
                (order["id"],),
            ).fetchall()
            raw_data = json.loads(order["raw_json"])
            response.append(
                {
                    "order_no": order["order_no"],
                    "experimenter_id": order["experimenter_id"],
                    "project_name": order["project_name"],
                    "status": order["status"],
                    "test_items": raw_data.get("test_items", []),
                    "samples": [dict(sample) for sample in samples],
                }
            )

    return {"success": True, "count": len(response), "work_orders": response}


@app.post("/api/scada/results", tags=["SCADA"])
def receive_scada_results(data: ResultUpload) -> dict[str, Any]:
    """校验并以 UPSERT 方式保存 SCADA 实验结果。"""
    with closing(get_db()) as connection:
        order = connection.execute(
            "SELECT * FROM work_orders WHERE order_no = ?",
            (data.order_no,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="工单不存在")

        work_order_id = order["id"]
        valid_samples = {
            row["sample_no"]
            for row in connection.execute(
                "SELECT sample_no FROM samples WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchall()
        }
        invalid_samples = sorted(
            {result.sample_no for result in data.results} - valid_samples
        )
        if invalid_samples:
            raise HTTPException(
                status_code=400,
                detail=f"样品不属于该工单: {', '.join(invalid_samples)}",
            )

        try:
            for result in data.results:
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

            status = "completed" if data.finished else "in_progress"
            connection.execute(
                """
                UPDATE work_orders
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, work_order_id),
            )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise HTTPException(status_code=500, detail="实验结果保存失败") from exc

    return {
        "success": True,
        "order_no": data.order_no,
        "finished": data.finished,
        "message": "实验结果保存成功",
    }


@app.get("/api/work-orders/{order_no}/results", tags=["LIMS 工单"])
def get_results(order_no: str) -> dict[str, Any]:
    """查询指定工单的已保存实验结果。"""
    with closing(get_db()) as connection:
        order = connection.execute(
            "SELECT * FROM work_orders WHERE order_no = ?",
            (order_no,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="工单不存在")

        results = connection.execute(
            """
            SELECT sample_no, test_item, value, unit, pushed_to_lims, created_at
            FROM test_results WHERE work_order_id = ?
            ORDER BY id ASC
            """,
            (order["id"],),
        ).fetchall()

    return {
        "order_no": order_no,
        "status": order["status"],
        "results": [dict(row) for row in results],
    }


@app.post("/api/work-orders/{order_no}/push-to-lims", tags=["LIMS 工单"])
async def push_results_to_lims(order_no: str) -> dict[str, Any]:
    """把已完成工单的全部结果回推到配置的 LIMS 地址。"""
    with closing(get_db()) as connection:
        order = connection.execute(
            "SELECT * FROM work_orders WHERE order_no = ?",
            (order_no,),
        ).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="工单不存在")
        if order["status"] not in ("completed", "pushed"):
            raise HTTPException(status_code=400, detail="实验还没有完成")

        results = connection.execute(
            """
            SELECT sample_no, test_item, value, unit FROM test_results
            WHERE work_order_id = ? ORDER BY id ASC
            """,
            (order["id"],),
        ).fetchall()
        if not results:
            raise HTTPException(status_code=400, detail="工单没有可推送的实验结果")

        payload = {
            "order_no": order_no,
            "experimenter_id": order["experimenter_id"],
            "results": [dict(row) for row in results],
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    LIMS_RESULT_URL,
                    json=payload,
                    headers={"X-Idempotency-Key": order_no},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"推送 LIMS 失败: {exc}") from exc

        try:
            connection.execute(
                "UPDATE test_results SET pushed_to_lims = 1 WHERE work_order_id = ?",
                (order["id"],),
            )
            connection.execute(
                """
                UPDATE work_orders SET status = 'pushed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (order["id"],),
            )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise HTTPException(status_code=500, detail="推送成功但本地状态更新失败") from exc

    return {
        "success": True,
        "order_no": order_no,
        "message": "实验结果已推送给 LIMS",
    }


@app.post("/mock/lims/results", tags=["本地 Mock"])
def mock_lims_receive_results(data: dict[str, Any]) -> dict[str, Any]:
    """本地联调使用；正式接入第三方 LIMS 后可删除。"""
    print("\n==============================")
    print("Mock LIMS 收到实验结果")
    print("==============================")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return {"success": True, "message": "Mock LIMS 接收成功"}
