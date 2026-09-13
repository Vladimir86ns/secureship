import logging

import httpx
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from db import check_db_connection
from ollama_client import OllamaResponseError, ask_ollama

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
async def health(response: Response):
    db_ok = await check_db_connection()
    if not db_ok:
        response.status_code = 503
        return {"status": "error", "db": "error"}
    return {"status": "ok", "db": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    try:
        reply = await ask_ollama(payload.message)
    except (httpx.HTTPError, OllamaResponseError) as exc:
        logger.exception("Ollama request failed")
        raise HTTPException(status_code=502, detail="Failed to get a response from the language model") from exc
    return ChatResponse(reply=reply)
