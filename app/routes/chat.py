import json
import logging
import re
import traceback
import uuid
from time import perf_counter

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import DEPLOYED_RESOURCE_NAME, ENVIRONMENT_RESOURCES, PROJECT_ID
from app.schemas import ChatRequest
from app.session_store import load_session_id, remove_session_id, store_session_id
from app.vertex_client import get_remote_app, stream_agent_query

router = APIRouter()
logger = logging.getLogger(__name__)


def cloud_trace_fields(headers) -> dict[str, str | bool]:
    cloud_context = headers.get("x-cloud-trace-context", "")
    match = re.fullmatch(r"([0-9a-fA-F]{32})(?:/(\d+))?(?:;o=([01]))?", cloud_context)
    if match:
        trace_id, span_number, sampled_flag = match.groups()
        fields: dict[str, str | bool] = {
            "logging.googleapis.com/trace": (
                f"projects/{PROJECT_ID}/traces/{trace_id.lower()}"
            )
        }
        if span_number:
            fields["logging.googleapis.com/spanId"] = f"{int(span_number):016x}"
        if sampled_flag is not None:
            fields["logging.googleapis.com/trace_sampled"] = sampled_flag == "1"
        return fields

    traceparent = headers.get("traceparent", "")
    parts = traceparent.split("-")
    if (
        len(parts) == 4
        and len(parts[1]) == 32
        and len(parts[2]) == 16
        and re.fullmatch(r"[0-9a-fA-F]+", parts[1])
        and re.fullmatch(r"[0-9a-fA-F]+", parts[2])
        and re.fullmatch(r"[0-9a-fA-F]{2}", parts[3])
    ):
        fields = {
            "logging.googleapis.com/trace": (
                f"projects/{PROJECT_ID}/traces/{parts[1].lower()}"
            ),
            "logging.googleapis.com/spanId": parts[2].lower(),
            "logging.googleapis.com/trace_sampled": bool(int(parts[3], 16) & 1),
        }
        return fields
    return {}


def log_chat_event(
    severity: str,
    message: str,
    request_id: str,
    trace_fields: dict[str, str | bool],
    **fields,
) -> None:
    entry = {
        "severity": severity,
        "message": message,
        "request_id": request_id,
        **trace_fields,
        **fields,
    }
    print(json.dumps(entry, separators=(",", ":")), flush=True)


def is_session_not_found(error: Exception) -> bool:
    message = str(error).lower()
    return "not found" in message or "not_found" in message


async def create_session(
    remote_app,
    session_key: tuple[str, str],
    scoped_user_id: str,
    environment_id: str,
    profile: dict[str, str],
) -> str:
    session = await remote_app.async_create_session(
        user_id=scoped_user_id,
        state={
            "home_environment": environment_id,
            "allowed_environments": list(ENVIRONMENT_RESOURCES),
            "user_profile": profile,
        },
    )
    session_id = session["id"] if isinstance(session, dict) else session.id
    await store_session_id(session_key, session_id)
    return session_id


@router.post("/api/chat", include_in_schema=False)
@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events stream containing chat response chunks.",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'data: {"text":"Hello"}\n\ndata: {"done":true}\n\n',
                }
            },
        }
    },
)
async def chat(request: ChatRequest, http_request: Request):
    if not request.user_id.strip() or not request.message.strip():
        raise HTTPException(
            status_code=422,
            detail="user_id and message must not be blank",
        )

    if request.environment not in ENVIRONMENT_RESOURCES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported environment_id",
        )

    request_id = str(uuid.uuid4())
    request_started = perf_counter()
    trace_fields = cloud_trace_fields(http_request.headers)

    async def event_stream():
        first_event_ms = None
        first_text_ms = None
        event_count = 0
        scoped_user_id = f"{request.user_id}::{request.environment}"
        session_key = (request.user_id, request.environment)
        try:
            resource_name = (
                ENVIRONMENT_RESOURCES.get(request.environment)
                or DEPLOYED_RESOURCE_NAME
            )
            remote_app = get_remote_app(resource_name)
            session_id = await load_session_id(session_key)
            if not session_id:
                session_id = await create_session(
                    remote_app,
                    session_key,
                    scoped_user_id,
                    request.environment,
                    {
                        key: request.profile.get(key, "")
                        for key in ("name", "role", "organization")
                    },
                )

            retried_session = False
            saw_partial = False
            while True:
                try:
                    async for chunk in stream_agent_query(
                        remote_app,
                        request.message,
                        scoped_user_id,
                        session_id,
                    ):
                        event_count += 1
                        if first_event_ms is None:
                            first_event_ms = (perf_counter() - request_started) * 1000

                        content = chunk.get("content", {}) if isinstance(chunk, dict) else {}
                        parts = content.get("parts", []) if isinstance(content, dict) else []
                        part_types = set()
                        if isinstance(parts, list):
                            for part in parts:
                                if not isinstance(part, dict):
                                    continue
                                if part.get("thought", False):
                                    part_types.add("thought")
                                elif part.get("text"):
                                    part_types.add("text")
                                if isinstance(part.get("function_call"), dict):
                                    part_types.add("function_call")
                                if isinstance(part.get("function_response"), dict):
                                    part_types.add("function_response")
                        event_type = "+".join(sorted(part_types)) or "other"
                        log_chat_event(
                            "INFO",
                            "chat_event",
                            request_id,
                            trace_fields,
                            event_type=event_type,
                        )

                        partial = bool(chunk.get("partial", False)) if isinstance(chunk, dict) else False
                        if isinstance(parts, list):
                            for part in parts:
                                if not isinstance(part, dict):
                                    continue
                                if part.get("thought", False):
                                    continue

                                function_call = part.get("function_call")
                                if isinstance(function_call, dict):
                                    yield (
                                        "event: function_call\n"
                                        f"data: {json.dumps(function_call)}\n\n"
                                    )

                                text = part.get("text")
                                if not isinstance(text, str) or not text:
                                    continue
                                if not partial and saw_partial:
                                    continue
                                if partial:
                                    saw_partial = True
                                if first_text_ms is None:
                                    first_text_ms = (perf_counter() - request_started) * 1000
                                yield f"data: {json.dumps({'text': text})}\n\n"
                    break
                except Exception as error:
                    if retried_session or event_count or not is_session_not_found(error):
                        raise
                    await remove_session_id(session_key)
                    session_id = await create_session(
                        remote_app,
                        session_key,
                        scoped_user_id,
                        request.environment,
                        {
                            key: request.profile.get(key, "")
                            for key in ("name", "role", "organization")
                        },
                    )
                    retried_session = True

            yield 'data: {"done": true}\n\n'
        except Exception:
            log_chat_event(
                "ERROR",
                "chat_request_failed",
                request_id,
                trace_fields,
                exception=traceback.format_exc(),
            )
            yield 'event: error\ndata: {"message": "Chat request failed"}\n\n'
        finally:
            log_chat_event(
                "INFO",
                "chat_request_complete",
                request_id,
                trace_fields,
                environment=request.environment,
                time_to_first_event_ms=round(first_event_ms) if first_event_ms is not None else None,
                time_to_first_text_ms=round(first_text_ms) if first_text_ms is not None else None,
                total_time_ms=round((perf_counter() - request_started) * 1000),
                event_count=event_count,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )
