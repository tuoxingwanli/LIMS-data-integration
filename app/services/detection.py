"""Business logic for startTest and stopTest."""

import sqlite3

from app.core.time import utc_now_iso
from app.db.connection import connection_scope
from app.integrations.capture import CaptureAdapter
from app.repositories.detection_sessions import DetectionSessionRepository
from app.repositories.work_orders import WorkOrderRepository
from app.schemas.work_orders import ProtocolResponse


class DetectionService:
    def __init__(self, db_path, capture_adapter: CaptureAdapter) -> None:
        self.db_path = db_path
        self.capture_adapter = capture_adapter
        self.sessions = DetectionSessionRepository()
        self.work_orders = WorkOrderRepository()

    @staticmethod
    def _success(message: str = "成功") -> ProtocolResponse:
        return ProtocolResponse(code="0010", response=None, message=message)

    @staticmethod
    def _failure(message: str) -> ProtocolResponse:
        return ProtocolResponse(code="500", response=None, message=message)

    def start(self, blind_sample_no: str) -> ProtocolResponse:
        with connection_scope(self.db_path) as connection:
            if self.sessions.active(connection, blind_sample_no):
                return self._success("检测已开始")
            sample = self.work_orders.find_sample_by_no(connection, blind_sample_no)
            sample_id = sample["id"] if sample else None
            started_at = utc_now_iso()
            capture_result = self.capture_adapter.start(blind_sample_no)
            if not capture_result.success:
                try:
                    self.sessions.create_failed(
                        connection,
                        blind_sample_no=blind_sample_no,
                        sample_id=sample_id,
                        started_at=started_at,
                        capture_mode=self.capture_adapter.mode,
                        error_message=capture_result.error or "启动采集失败",
                    )
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                return self._failure(capture_result.error or "启动录屏失败")
            try:
                self.sessions.create(
                    connection,
                    blind_sample_no=blind_sample_no,
                    sample_id=sample_id,
                    started_at=started_at,
                    capture_mode=self.capture_adapter.mode,
                    recording_ref=capture_result.artifact_ref,
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                return self._failure("检测会话保存失败")
        return self._success("成功")

    def stop(self, blind_sample_no: str) -> ProtocolResponse:
        with connection_scope(self.db_path) as connection:
            session = self.sessions.active(connection, blind_sample_no)
            if session is None:
                latest = self.sessions.latest(connection, blind_sample_no)
                if latest and latest["status"] == "stopped":
                    return self._success("检测已结束")
                return self._failure("未找到正在进行的检测")
            capture_result = self.capture_adapter.stop(blind_sample_no)
            if not capture_result.success:
                try:
                    self.sessions.record_error(
                        connection,
                        session["id"],
                        capture_result.error or "结束采集失败",
                    )
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                return self._failure(capture_result.error or "结束录屏失败")
            try:
                self.sessions.stop(
                    connection,
                    session["id"],
                    ended_at=utc_now_iso(),
                    screenshot_ref=capture_result.artifact_ref,
                )
                connection.commit()
            except sqlite3.Error:
                connection.rollback()
                return self._failure("检测会话保存失败")
        return self._success("成功")
