# Amazon EC2 Deployment Runbook

This runbook records the EC2 setup used for the chat widget backend. It targets Amazon Linux 2023 on x86_64 and assumes the backend repository is at `/var/www/html/chat-widget/chat-widget-backend` and the service user is `ec2-user`. Change paths and user names if your instance differs.

## 1. Install Python 3.11 alongside the system Python

The backend uses Python union type annotations that require Python 3.10 or newer. Google client libraries also warn on Python 3.9. On Amazon Linux 2023, install Python 3.11 without replacing `/usr/bin/python3`:

```bash
sudo dnf install -y python3.11 python3.11-pip
python3.11 --version
```

Create a new environment with the explicit interpreter. If the existing `.venv` was created with Python 3.9, deactivate it and keep it as a backup before recreating `.venv`:

```bash
cd /var/www/html/chat-widget/chat-widget-backend
deactivate
mv .venv .venv-py39-backup
python3.11 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
python -c "from app.main import app; print(app.title)"
```

The import should print `Chat Widget API`. Chat sessions and their history are stored by Agent Engine; PostgreSQL and Redis are not required.

## 2. Configure backend environment

Create `.env` from `.env.example` and set the real project, location, Vertex AI resource, and CORS settings. Do not commit `.env`, ADC credentials, or service-account key files.

- `GOOGLE_CLOUD_PROJECT`: Google Cloud project ID used for API/quota context.
- `GOOGLE_CLOUD_LOCATION`: Vertex AI location.
- `VERTEX_AI_AGENT_RESOURCE`: deployed reasoning engine resource path.
- `CORS_ALLOWED_ORIGINS_FILE`: optional path to a live-reloaded, one-origin-per-line allowlist. When set, it takes precedence over `CORS_ALLOWED_ORIGINS`; edits apply on the next request without restarting. Keep the file readable by `ec2-user` and outside the repository.
- `CORS_ALLOWED_ORIGINS`: static alternative: `*` to accept widgets from any origin, or a comma-separated list of exact origins (scheme, host, and optional port). If both settings are unset, browser-origin requests are rejected. Origin validation is not API authentication.

The frontend bundle separately needs `VITE_API_URL` set to the public HTTPS API URL ending in `/api/chat` when it is built.

## 3. Google Cloud authentication

The Python Google Cloud libraries use Application Default Credentials (ADC). Installing `gcloud` or running `gcloud auth login` alone does not authenticate the Python app.

### Temporary smoke-test authentication

For a temporary test, install the Google Cloud CLI using the [official Linux install guide](https://docs.cloud.google.com/sdk/docs/install-sdk#linux). Select the archive matching `uname -m`, verify its published SHA-256 checksum, extract it under `/home/ec2-user`, and run `~/google-cloud-sdk/install.sh` as `ec2-user` (not with `sudo`).

Then authenticate ADC interactively:

```bash
gcloud auth application-default login --no-launch-browser
gcloud auth application-default set-quota-project YOUR_GOOGLE_CLOUD_PROJECT_ID
gcloud auth application-default print-access-token >/dev/null && echo "ADC credentials OK"
```

Open the printed URL on your workstation and enter the authorization code directly in the SSH terminal. Never put the code or token in source control or logs. Use the same project ID configured for `GOOGLE_CLOUD_PROJECT`; the account needs Vertex AI access and Service Usage Consumer permissions for the quota project.

A personal user's ADC is only suitable for a temporary smoke test. For a long-running EC2 production service, configure AWS-to-Google Workload Identity Federation and grant the federated AWS role the required Vertex AI permissions. Do not rely on a developer's interactive credentials for production availability.

## 4. Run once in the foreground

For an initial test, from the backend directory with `.venv` active:

```bash
python -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

In another SSH terminal, check health:

```bash
curl -i http://127.0.0.1:8000/health
```

Expected response: HTTP 200 with `{"status":"ok"}`. A real `POST /api/chat` smoke test calls Vertex AI and may use billable quota.

Stop a foreground test with `Ctrl+C` before starting the systemd service so port 8000 is free.

## 5. Run the API under systemd

Create `/etc/systemd/system/chat-widget-backend.service`:

```ini
[Unit]
Description=Chat Widget FastAPI backend
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/var/www/html/chat-widget/chat-widget-backend
Environment=HOME=/home/ec2-user
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/var/www/html/chat-widget/chat-widget-backend/.env
ExecStart=/var/www/html/chat-widget/chat-widget-backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`HOME` lets the process find the temporary ADC file under `/home/ec2-user/.config/gcloud/`. For production, configure the service for Workload Identity Federation instead.

Load and start the unit:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now chat-widget-backend
sudo systemctl status chat-widget-backend --no-pager
```

Verify it responds:

```bash
curl -i http://127.0.0.1:8000/health
```

View logs and control the process:

```bash
sudo journalctl -u chat-widget-backend -f
sudo systemctl restart chat-widget-backend
sudo systemctl stop chat-widget-backend
sudo systemctl disable --now chat-widget-backend
sudo systemctl enable --now chat-widget-backend
```

`stop` stops it until started again; the enabled service still starts on reboot. `disable --now` stops it and prevents startup on reboot.

## 6. Expose the API and deploy the widget

The service intentionally listens on `127.0.0.1:8000`. Put Nginx or another reverse proxy in front of it, configure TLS, and proxy the public API hostname to this local listener. Do not expose port 8000 directly to the internet. For production site restrictions without restart-per-client, configure `CORS_ALLOWED_ORIGINS_FILE` once, then edit the external origins file; the widget receives a readable 403 for unlisted sites. Apply rate limiting at the reverse proxy or API layer because origin validation is not authentication.

Build the widget from the frontend repository with the public backend URL:

```bash
cd /var/www/html/chat-widget/chat-widget-frontend
npm ci
VITE_API_URL=https://api.your-domain.com/api/chat npm run build:embed
test -s dist/embed/lam-chat-widget.js
```

Replace the example hostname. `npm ci` requires `package.json` and `package-lock.json` to be synchronized. If npm reports `EACCES` under `/var/www/html`, fix checkout ownership or build as `ec2-user` in the home directory and copy only the generated bundle; do not run npm as root. Host `dist/embed/lam-chat-widget.js` over HTTPS as a static asset.

## Current deployment checks and known gaps

- Python 3.11.14 was installed side by side with system Python 3.9; the app imported successfully and `pip check` reported no broken requirements.
- Google Cloud CLI 587.0.0 was installed under `/home/ec2-user/google-cloud-sdk`; the app does not require the CLI at runtime when production ADC is configured properly.
- `chat-widget-backend.service` was enabled and reported `active (running)`, bound to `127.0.0.1:8000`.
- Session persistence and history restoration are handled by Agent Engine, with the widget retaining the session ID in local storage.
- Complete the Vertex AI stream test, public reverse-proxy/TLS setup, production Workload Identity Federation, and public-origin widget test before declaring deployment ready.
- At the time this runbook was written, frontend `package.json` requested Vite `^8.3.0` while `package-lock.json` pinned `5.4.21`; `npm ci --dry-run` failed because of that mismatch. Reconcile and test both files, then commit them together before building on the server.
