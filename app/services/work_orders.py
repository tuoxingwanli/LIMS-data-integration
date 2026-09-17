"""Business logic for the LIMS / SCADA work-order loop."""

import json
import sqlite3
from typing import Any

from fastapi import HTTPException

from app.db.connection import connection_scope
from app.integrations.lims import LimsClientError
from app.repositories.work_orders import WorkOrderRepository
from app.schemas.work_orders import ResultUpload, WorkOrderIn


class WorkOrderService:
    def __init__(self, db_path, lims_client) -> None:
        self.db_path = db_path
        self.lims_client = lims_client
        self.repository = WorkOrderRepository()

    def receive(self, data: WorkOrderIn) -> dict[str, Any]:
        with connection_scope(self.db_path) as connection:
            old = self.repository.find_by_order_no(connection, data.order_no)
            if old:
                return {
                    "success": True,
                    "duplicate": True,
                    "message": "工单已经存在",
                    "order_no": data.order_no,
                }
            try:
                self.repository.create(connection, data)
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

    def list_for_experimenter(self, experimenter_id: str) -> dict[str, Any]:
        if not experimenter_id.strip():
            raise HTTPException(status_code=422, detail="experimenter_id 不能为空")
        experimenter_id = experimenter_id.strip()
        with connection_scope(self.db_path) as connection:
            orders = self.repository.list_for_experimenter(connection, experimenter_id)
            response = []
            for order in orders:
                samples = self.repository.samples_for_order(connection, order["id"])
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

    def receive_results(self, data: ResultUpload) -> dict[str, Any]:
        with connection_scope(self.db_path) as connection:
            order = self.repository.find_by_order_no(connection, data.order_no)
            if not order:
                raise HTTPException(status_code=404, detail="工单不存在")
            valid_samples = self.repository.sample_ids_for_order(connection, order["id"])
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
                    self.repository.upsert_result(connection, order["id"], result)
                self.repository.update_status(
                    connection,
                    order["id"],
                    "completed" if data.finished else "in_progress",
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

    def get_results(self, order_no: str) -> dict[str, Any]:
        with connection_scope(self.db_path) as connection:
            order = self.repository.find_by_order_no(connection, order_no)
            if not order:
                raise HTTPException(status_code=404, detail="工单不存在")
            results = self.repository.results_for_order(connection, order["id"])
        return {
            "order_no": order_no,
            "status": order["status"],
            "results": [dict(row) for row in results],
        }

    async def push_results(self, order_no: str) -> dict[str, Any]:
        with connection_scope(self.db_path) as connection:
            order = self.repository.find_by_order_no(connection, order_no)
            if not order:
                raise HTTPException(status_code=404, detail="工单不存在")
            if order["status"] not in ("completed", "pushed"):
                raise HTTPException(status_code=400, detail="实验还没有完成")
            results = self.repository.push_payload_results(connection, order["id"])
            if not results:
                raise HTTPException(status_code=400, detail="工单没有可推送的实验结果")
            payload = {
                "order_no": order_no,
                "experimenter_id": order["experimenter_id"],
                "results": [dict(row) for row in results],
            }
            work_order_id = order["id"]
        try:
            await self.lims_client.push_results(payload, idempotency_key=order_no)
        except LimsClientError as exc:
            raise HTTPException(status_code=502, detail=f"推送 LIMS 失败: {exc}") from exc
        try:
            with connection_scope(self.db_path) as connection:
                self.repository.mark_pushed(connection, work_order_id)
                connection.commit()
        except sqlite3.Error as exc:
            raise HTTPException(status_code=500, detail="推送成功但本地状态更新失败") from exc
        return {"success": True, "order_no": order_no, "message": "实验结果已推送给 LIMS"}
