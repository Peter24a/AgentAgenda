from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db.database import init_db
from app.db.seed import seed_initial_data_if_empty
from app.db.session import init_canonical_db
from app.api.agenda import router as agenda_router
from app.api.proposals import router as proposals_router
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.sync import router as sync_router
from app.api.documents import router as documents_router
from app.api.preparation import router as preparation_router
from app.api.memory import router as memory_router
from app.api.jobs import router as jobs_router
from app.api.device_requests import router as device_requests_router
from app.api.mcp import router as mcp_router
from app.api.status import router as status_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize canonical schema & legacy SQLite
    await init_canonical_db()
    await init_db()
    await seed_initial_data_if_empty()
    yield

app = FastAPI(
    title=settings.app_name,
    description="Backend orquestador para AgentAgenda con inferencia LLM local autohosteada",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agenda_router)
app.include_router(proposals_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(sync_router)
app.include_router(documents_router)
app.include_router(preparation_router)
app.include_router(memory_router)
app.include_router(jobs_router)
app.include_router(device_requests_router)
app.include_router(mcp_router)
app.include_router(status_router)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": settings.app_name,
        "llm_model": settings.llm_model,
        "llm_api_base": settings.llm_api_base
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}
