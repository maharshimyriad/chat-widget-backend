import os

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "development-team-403018")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")
DEPLOYED_RESOURCE_NAME = os.getenv(
    "VERTEX_AI_AGENT_RESOURCE",
    "projects/80153651050/locations/us-west1/"
    "reasoningEngines/3287350651050262528",
)
ENVIRONMENT_RESOURCES = {
    "dam": None,
    "eponymos": None,
    "media_center": None,
}
ALLOWED_ENVIRONMENTS = list(ENVIRONMENT_RESOURCES)

APP_TITLE = "Chat Widget API"
APP_VERSION = "1.0.0"


def get_cors_origins() -> list[str]:
    default_origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "")
    return default_origins + [
        item.strip() for item in configured.split(",") if item.strip()
    ]
