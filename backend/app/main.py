import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import strava, profile, records, goals, ai, plans, chat, auth
from app.db.database import engine, Base
from app.db.migrations import ensure_schema
from app.db.seed import seed_master
import app.models  # noqa

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    seed_master()
    yield


app = FastAPI(title="Goggins Trainer API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(strava.router)
app.include_router(profile.router)
app.include_router(records.router)
app.include_router(goals.router)
app.include_router(ai.router)
app.include_router(plans.router)
app.include_router(chat.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Servir el frontend React — debe ir al final
STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        return FileResponse(STATIC_DIR / "index.html")
