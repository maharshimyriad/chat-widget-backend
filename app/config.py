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
