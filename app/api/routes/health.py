from fastapi import APIRouter


router = APIRouter(tags=["系统"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
