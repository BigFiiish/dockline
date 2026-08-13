from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dockline.agent import Agent
from dockline.client import ClearbayClient, ClearbayError
from dockline.config import CLEARBAY_BASE_URL, OPENAI_API_KEY, TENANTS
from dockline.evalrun import run_evals
from dockline.score import load_cases

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Dockline", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_agent = Agent()


class ChatIn(BaseModel):
    tenant: str = "acme"
    message: str = Field(min_length=1, max_length=2000)


class EvalIn(BaseModel):
    ids: list[str] | None = None
    base_url: str | None = None


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "UP", "clearbay": CLEARBAY_BASE_URL, "llm": bool(OPENAI_API_KEY)}


@app.get("/api/meta")
async def meta():
    return {
        "clearbay": CLEARBAY_BASE_URL,
        "llm": bool(OPENAI_API_KEY),
        "tenants": {key: {"label": spec["label"], "role": spec["role"]} for key, spec in TENANTS.items()},
        "cases": len(load_cases()),
    }


@app.get("/api/cases")
async def cases():
    rows = load_cases()
    return {"count": len(rows), "items": rows}


@app.post("/api/chat")
async def chat(body: ChatIn):
    if body.tenant not in TENANTS:
        raise HTTPException(400, "unknown tenant")
    try:
        return await _agent.run(body.tenant, body.message)
    except ClearbayError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/evals")
async def evals(body: EvalIn):
    try:
        return await run_evals(body.base_url, body.ids)
    except ClearbayError as exc:
        raise HTTPException(502, str(exc)) from exc


def main() -> None:
    import uvicorn

    uvicorn.run("dockline.web:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
