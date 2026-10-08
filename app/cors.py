import os
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse


def get_allowed_origins(origins_value: str | None = None) -> list[str]:
    configured_origins = (
        os.getenv("CORS_ALLOWED_ORIGINS", "")
        if origins_value is None
        else origins_value
    )
    return parse_origins(configured_origins)


def parse_origins(value: str) -> list[str]:
    origins = []
    for line in value.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        origins.extend(origin.strip() for origin in line.split(",") if origin.strip())
    return origins


class OriginValidationMiddleware:
    def __init__(
        self,
        app,
        allowed_origins: list[str],
        allowed_origins_file: Path | None = None,
    ):
        self.app = app
        self.allowed_origins = allowed_origins
        self.allowed_origins_file = allowed_origins_file
        self._cached_file_signature = None
        self._cached_file_origins: list[str] = []
        self._cache_lock = threading.Lock()

    def get_current_allowed_origins(self) -> list[str]:
        if self.allowed_origins_file is None:
            return self.allowed_origins

        try:
            file_stat = self.allowed_origins_file.stat()
            signature = (file_stat.st_mtime_ns, file_stat.st_size, file_stat.st_ino)
        except OSError:
            signature = None

        if signature != self._cached_file_signature:
            with self._cache_lock:
                if signature != self._cached_file_signature:
                    try:
                        contents = self.allowed_origins_file.read_text(encoding="utf-8")
                        self._cached_file_origins = parse_origins(contents)
                    except OSError:
                        self._cached_file_origins = []
                    self._cached_file_signature = signature

        return self._cached_file_origins

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] != "OPTIONS":
            origin = next(
                (
                    value.decode("latin-1")
                    for name, value in scope["headers"]
                    if name.lower() == b"origin"
                ),
                None,
            )
            allowed_origins = self.get_current_allowed_origins()
            if (
                origin
                and "*" not in allowed_origins
                and origin not in allowed_origins
            ):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "This site is not authorized to use the chat widget."},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def add_cors_middleware(
    app: FastAPI,
    origins_value: str | None = None,
    origins_file: str | Path | None = None,
) -> None:
    configured_file = origins_file
    if configured_file is None:
        configured_file = os.getenv("CORS_ALLOWED_ORIGINS_FILE")
    allowlist_path = Path(configured_file).expanduser() if configured_file else None
    allowed_origins = [] if allowlist_path else get_allowed_origins(origins_value)
    app.add_middleware(
        OriginValidationMiddleware,
        allowed_origins=allowed_origins,
        allowed_origins_file=allowlist_path,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )