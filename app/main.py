from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_TITLE, APP_VERSION, get_cors_origins
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router
from app.routes.session import router as session_router

app = FastAPI(title=APP_TITLE, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(session_router)
