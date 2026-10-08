# Backend project structure

`chat-widget-backend/` is an independent Python project alongside `chat-widget-frontend/`.

## Backend files

- `app/main.py` assembles the FastAPI application and middleware.
- `app/config.py` loads Vertex AI environment settings.
- `app/schemas.py` defines API request models.
- `app/vertex_client.py` wraps Vertex AI access and streaming.
- `app/routes/health.py` provides health and demo routes.
- `app/routes/chat.py` handles chat requests and SSE responses.
- `app/routes/session.py` retrieves message history from Agent Engine sessions.
- `benchmark.py` and `benchmark_prompts.json` run API latency checks.
- `.env` contains local backend settings and should not be committed.

`script.py` is retained as a compatibility entrypoint. New commands should use `app.main:app`.

## Runtime behavior

Agent Engine owns session state and conversation history. The widget stores the session ID in browser `localStorage`, scoped by stable user ID and environment, and sends it with each message. The backend reads past messages from Agent Engine with `async_get_session`; it does not keep a separate transcript or session-ID store.

For setup, run commands, and environment variables, see [the backend README](../README.md).
