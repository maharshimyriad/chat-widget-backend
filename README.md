# Chat Widget Backend

FastAPI service that streams Vertex AI responses for the chat widget and manages server-side conversation sessions.

## Project layout

See [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for the module overview. The frontend is a separate sibling project at `../chat-widget-frontend/`.

## Setup

From this directory, create a virtual environment, install dependencies, and configure local settings:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set the Google Cloud project, location, Vertex AI agent resource, and any Redis settings in `.env`. Keep real credentials out of source control. If Redis is unset, session IDs use process memory, which is suitable only for local development.

## Run the API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

The API health check is available at `http://127.0.0.1:8000/health`. The frontend’s local API URL is configured separately in `../chat-widget-frontend/.env` as `VITE_API_URL`.

## Run the latency benchmark

The benchmark sends the prompt set to the `dam`, `eponymos`, and `media_center` environments and measures streaming latency:

```powershell
.\.venv\Scripts\python.exe benchmark.py --base-url http://127.0.0.1:8000 --run-id smoke --output smoke.jsonl
```

Use a fresh run ID and output path for each run. `benchmark_prompts.json` contains the prompts used by default.

## Compatibility

`script.py` remains available for older commands:

```powershell
.\.venv\Scripts\python.exe -m uvicorn script:app --env-file .env --host 127.0.0.1 --port 8000
```
