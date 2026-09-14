import logging

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import check_db_connection
from routers import chat, session, verify

logging.basicConfig(level=logging.INFO, format="%(levelname)-5.5s [%(name)s] %(message)s")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session.router)
app.include_router(chat.router)
app.include_router(verify.router)


@app.get("/health")
async def health(response: Response):
    db_ok = await check_db_connection()
    if not db_ok:
        response.status_code = 503
        return {"status": "error", "db": "error"}
    return {"status": "ok", "db": "ok"}
