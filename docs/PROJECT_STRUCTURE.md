# Backend project structure

`chat-widget-backend/` is an independent Python project alongside `chat-widget-frontend/`.

## Backend files

- `app/main.py` assembles the FastAPI application and middleware.
- `app/config.py` loads environment settings and CORS origins.
- `app/schemas.py` defines API request models.
- `app/session_store.py` persists user/environment session IDs.
- `app/vertex_client.py` wraps Vertex AI access and streaming.
- `app/routes/health.py` provides health and demo routes.
- `app/routes/chat.py` handles chat requests and SSE responses.
- `app/routes/session.py` deletes a conversation session.
- `benchmark.py` and `benchmark_prompts.json` run API latency checks.
- `.env` contains local backend settings and should not be committed.

`script.py` is retained as a compatibility entrypoint. New commands should use `app.main:app`.

## Runtime behavior

The backend session stores conversational state for the Vertex AI agent. It is not a transcript API and does not restore messages to the widget after refresh. The frontend remains responsible for rendering the transcript and does not use browser `localStorage` for persistence.

For setup, run commands, and environment variables, see [the backend README](../README.md).
