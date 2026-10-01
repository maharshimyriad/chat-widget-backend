from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/", include_in_schema=False)
async def demo_page():
    root_index = Path(__file__).resolve().parents[2] / "index.html"
    if root_index.exists():
        return FileResponse(root_index)
    return {"status": "ok"}
