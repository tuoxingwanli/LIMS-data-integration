"""Application factory for the modular LIMS / SCADA integration service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import detection, health, work_orders
from app.core.config import Settings
from app.db.schema import init_db
from app.integrations.capture import CaptureAdapter, build_capture_adapter
from app.integrations.lims import HttpLimsClient
from app.services.detection import DetectionService
from app.services.work_orders import WorkOrderService


def create_app(
    settings: Settings | None = None,
    *,
    capture_adapter: CaptureAdapter | None = None,
    lims_client=None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    capture_adapter = capture_adapter or build_capture_adapter(settings.capture_backend)
    lims_client = lims_client or HttpLimsClient(settings.lims_result_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(app.state.settings.db_path)
        yield

    app = FastAPI(
        title="LIMS / SCADA Integration Demo",
        description="LIMS 工单、SCADA 实验结果、检测客户端通知及 LIMS 回推的最小闭环。",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.work_order_service = WorkOrderService(settings.db_path, lims_client)
    app.state.detection_service = DetectionService(settings.db_path, capture_adapter)
    app.include_router(health.router)
    app.include_router(work_orders.router)
    app.include_router(detection.router)
    return app


app = create_app()
