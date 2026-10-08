from fastapi import APIRouter, HTTPException, Query

from app.config import DEPLOYED_RESOURCE_NAME, ENVIRONMENT_RESOURCES
from app.vertex_client import get_remote_app

router = APIRouter()


def as_mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {}


@router.get("/api/history", include_in_schema=False)
@router.get("/history")
async def get_history(
    user_id: str = Query(min_length=1, max_length=256),
    environment_id: str = Query(min_length=1, max_length=64),
    session_id: str | None = Query(default=None, min_length=1, max_length=256),
):
    if environment_id not in ENVIRONMENT_RESOURCES:
        raise HTTPException(status_code=400, detail="Unsupported environment_id")
    if not session_id:
        return {"messages": []}

    remote_app = get_remote_app(DEPLOYED_RESOURCE_NAME)
    try:
        session = await remote_app.async_get_session(
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail="Unable to load chat history") from error

    events = as_mapping(session).get("events", [])
    messages = []
    for event in events if isinstance(events, list) else []:
        event_data = as_mapping(event)
        content = as_mapping(event_data.get("content"))
        parts = content.get("parts", [])
        role = "user" if event_data.get("author") == "user" or content.get("role") == "user" else "assistant"
        text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict)
            and not part.get("thought", False)
            and isinstance(part.get("text"), str)
        ) if isinstance(parts, list) else ""
        if text:
            messages.append({"role": role, "content": text})

    return {"messages": messages}
