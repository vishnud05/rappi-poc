"""Run with: uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000."""

from contextlib import asynccontextmanager
import os

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.agent import MODEL, run_agent
from backend.store import Conflict, NotFound, Store

store = Store(os.getenv("DATABASE_PATH", "data/purchasing.db"))


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    yield


app = FastAPI(title="Buyer Agent API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Conflict)
async def conflict_handler(request: Request, exc: Conflict):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(NotFound)
async def not_found_handler(request: Request, exc: NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Invalid request. Provide a valid scenario_id and no extra fields."})


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1, max_length=100)


@app.get("/api/health")
def health():
    return {"status": "ok", "model": MODEL, "model_configured": bool(os.getenv("NVIDIA_API_KEY"))}


@app.get("/api/scenarios")
def scenarios():
    return store.scenarios()


@app.get("/api/scenarios/{sid}")
def scenario(sid: str):
    return store.scenario(sid)


@app.post("/api/scenarios/{sid}/reset")
def reset(sid: str):
    return store.reset(sid)


@app.post("/api/runs", status_code=202)
def start(body: StartRun, background_tasks: BackgroundTasks):
    run = store.start_run(body.scenario_id, MODEL)
    background_tasks.add_task(run_agent, store, run["id"])
    return run


@app.get("/api/runs/{rid}")
def get_run(rid: str):
    return store.run(rid)
