from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.logging import setup_logging
from app.platforms.slack.adapter import router as slack_router
from app.platforms.teams.bot import router as teams_router
from app.platforms.outlook.graph import router as outlook_router
from app.api.v1 import router as api_router

setup_logging()
app = FastAPI(title="Thread Condenser")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(slack_router)
app.include_router(teams_router)
app.include_router(outlook_router)
app.include_router(api_router)
