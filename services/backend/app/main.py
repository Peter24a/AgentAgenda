from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db.database import init_db
from app.db.seed import seed_initial_data_if_empty
from app.api.agenda import router as agenda_router
from app.api.proposals import router as proposals_router
from app.api.chat import router as chat_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and seed initial items
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
