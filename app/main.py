from fastapi import FastAPI

from app.config import APP_TITLE, APP_VERSION
from app.cors import add_cors_middleware
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router
from app.routes.session import router as session_router

app = FastAPI(title=APP_TITLE, version=APP_VERSION)
add_cors_middleware(app)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(session_router)
