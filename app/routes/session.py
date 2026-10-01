from fastapi import APIRouter, HTTPException

from app.config import DEPLOYED_RESOURCE_NAME, ENVIRONMENT_RESOURCES
from app.schemas import SessionRequest
from app.session_store import load_session_id, remove_session_id
from app.vertex_client import get_remote_app

router = APIRouter()


def is_session_not_found(error: Exception) -> bool:
    message = str(error).lower()
    return "not found" in message or "not_found" in message


@router.delete("/api/session", include_in_schema=False)
@router.delete("/session")
async def clear_session(request: SessionRequest):
    if request.environment not in ENVIRONMENT_RESOURCES:
        raise HTTPException(status_code=400, detail="Unsupported environment_id")

    session_key = (request.user_id, request.environment)
    session_id = await load_session_id(session_key)
    if not session_id:
        return {"deleted": False}

    resource_name = (
        ENVIRONMENT_RESOURCES.get(request.environment)
        or DEPLOYED_RESOURCE_NAME
    )
    remote_app = get_remote_app(resource_name)
    scoped_user_id = f"{request.user_id}::{request.environment}"
    try:
        await remote_app.async_delete_session(
            user_id=scoped_user_id,
            session_id=session_id,
        )
    except Exception as error:
        if not is_session_not_found(error):
            raise HTTPException(status_code=502, detail="Unable to delete chat session") from error
    await remove_session_id(session_key)
    return {"deleted": True}
