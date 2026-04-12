from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import strava
from app.db.database import engine, Base
import app.models  # noqa: registra todos los modelos antes del create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crea las tablas si no existen (idempotente)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Goggins Trainer API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strava.router)


@app.get("/health")
def health():
    return {"status": "ok"}
