from fastapi import APIRouter, Query, Request

from app.schemas.work_orders import ResultUpload, WorkOrderIn


router = APIRouter()


@router.post("/api/work-orders", tags=["LIMS 工单"])
def receive_work_order(data: WorkOrderIn, request: Request):
    return request.app.state.work_order_service.receive(data)


@router.get("/api/scada/work-orders", tags=["SCADA"])
def get_scada_work_orders(
    request: Request,
    experimenter_id: str = Query(...),
):
    return request.app.state.work_order_service.list_for_experimenter(experimenter_id)


@router.post("/api/scada/results", tags=["SCADA"])
def receive_scada_results(data: ResultUpload, request: Request):
    return request.app.state.work_order_service.receive_results(data)


@router.get("/api/work-orders/{order_no}/results", tags=["LIMS 工单"])
def get_results(order_no: str, request: Request):
    return request.app.state.work_order_service.get_results(order_no)


@router.post("/api/work-orders/{order_no}/push-to-lims", tags=["LIMS 工单"])
async def push_results_to_lims(order_no: str, request: Request):
    return await request.app.state.work_order_service.push_results(order_no)


@router.post("/mock/lims/results", tags=["本地 Mock"])
def mock_lims_receive_results(data: dict):
    """Local integration target; replace with the real LIMS endpoint in deployment."""
    import json

    print("\n==============================")
    print("Mock LIMS 收到实验结果")
    print("==============================")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return {"success": True, "message": "Mock LIMS 接收成功"}
