from fastapi import APIRouter, Request

from app.schemas.work_orders import DetectionRequest, ProtocolResponse


router = APIRouter()


@router.post("/startTest", response_model=ProtocolResponse, tags=["检测客户端"])
def start_test(data: DetectionRequest, request: Request) -> ProtocolResponse:
    return request.app.state.detection_service.start(data.blind_sample_no)


@router.post("/stopTest", response_model=ProtocolResponse, tags=["检测客户端"])
def stop_test(data: DetectionRequest, request: Request) -> ProtocolResponse:
    return request.app.state.detection_service.stop(data.blind_sample_no)
