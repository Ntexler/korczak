"""Korczak AI — FastAPI Application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.api.chat import router as chat_router
from backend.api.graph import router as graph_router
from backend.api.health import router as health_router
from backend.api.features import router as features_router
from backend.api.library import router as library_router
from backend.api.highlights import router as highlights_router
from backend.api.reading import router as reading_router
from backend.api.syllabus import router as syllabus_router
from backend.api.community import router as community_router
from backend.api.connection_feedback import router as connections_router
from backend.api.translation import router as translation_router
from backend.api.researcher import router as researcher_router
from backend.api.summaries import router as summaries_router
from backend.api.timeline import router as timeline_router
from backend.api.upload import router as upload_router
from backend.api.courses import router as courses_router
from backend.api.briefings import router as briefings_router
from backend.api.obsidian import router as obsidian_router
from backend.api.active_learning import router as learning_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting {settings.app_name}")
    yield
    # Shutdown
    print(f"Shutting down {settings.app_name}")


app = FastAPI(
    title=settings.app_name,
    description="AI Knowledge Navigator",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(graph_router, prefix="/api/graph", tags=["graph"])
app.include_router(features_router, prefix="/api/features", tags=["features"])
app.include_router(library_router, prefix="/api/library", tags=["library"])
app.include_router(highlights_router, prefix="/api/highlights", tags=["highlights"])
app.include_router(reading_router, prefix="/api/reading", tags=["reading"])
app.include_router(syllabus_router, prefix="/api/syllabus", tags=["syllabus"])
app.include_router(community_router, prefix="/api/community", tags=["community"])
app.include_router(connections_router, prefix="/api/connections", tags=["connections"])
app.include_router(translation_router, prefix="/api/translation", tags=["translation"])
app.include_router(researcher_router, prefix="/api/researchers", tags=["researchers"])
app.include_router(summaries_router, prefix="/api/social", tags=["social"])
app.include_router(timeline_router, prefix="/api/timeline", tags=["timeline"])
app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(courses_router, prefix="/api/courses", tags=["courses"])
app.include_router(briefings_router, prefix="/api/briefings", tags=["briefings"])
app.include_router(obsidian_router, prefix="/api/obsidian", tags=["obsidian"])
app.include_router(learning_router, prefix="/api/learning", tags=["learning"])
