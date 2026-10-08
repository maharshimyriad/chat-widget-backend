# Chat Widget Backend

FastAPI service that manages Vertex AI agent sessions and streams chat responses to the widget as Server-Sent Events (SSE).

## Project layout

See [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for the module map. The frontend is a separate sibling project at `../chat-widget-frontend/`.

## Requirements and setup

Use Python 3.11 or newer. Python 3.9 is unsupported by current Google client libraries and the source uses union type annotations that require Python 3.10 or newer.

Linux / Amazon Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Copy `.env.example` to `.env` and configure `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `VERTEX_AI_AGENT_RESOURCE`. For an allowlist that can change without restarting, copy `allowed-origins.example.txt` to a server path, set `CORS_ALLOWED_ORIGINS_FILE` to that path, and edit one origin per line. Restart once after setting the file path; later edits are picked up automatically. Otherwise, use `CORS_ALLOWED_ORIGINS` for a static `*` or comma-separated origin list. If both settings are unset, browser-origin requests are rejected. Browser credentials are disabled in every mode. Keep `.env`, credentials, and the live origins file out of source control.

## Run and test the API

```bash
python -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/health`. `POST /api/chat` accepts `user_id`, `environment_id`, `message`, and `session_id`, then streams JSON `session`, `message`, `error`, and `done` events. `GET /api/history` reads messages from the Agent Engine session. CORS stays non-credentialed so the widget can display a readable 403 for an unlisted origin. Origin validation is not API authentication. The widget owns session IDs in local storage; the backend does not store session IDs or transcript copies. `script.py` remains as a compatibility entry point, but new commands should use `app.main:app`.

Run the latency benchmark from this directory with a running API:

```bash
python benchmark.py --base-url http://127.0.0.1:8000 --run-id smoke --output smoke.jsonl
```

## Authentication and sessions

The Google Python client uses Application Default Credentials (ADC). For a temporary local or smoke test, ADC can be created with `gcloud auth application-default login`; set its quota project to the same Google Cloud project used by the app. Do not use a personal user login as the long-term EC2 service identity. Use AWS-to-Google Workload Identity Federation for production.

Use the same stable `user_id` when creating a session and on every message. The widget prefixes its stable user ID with `client_id` and stores a separate Agent Engine session ID for each user and environment. Agent Engine is the source of truth for conversation history.

## EC2 deployment

See [docs/EC2_DEPLOYMENT.md](docs/EC2_DEPLOYMENT.md) for the Amazon Linux 2023, Python 3.11, ADC testing, systemd, health-check, logs, and service-control steps.
