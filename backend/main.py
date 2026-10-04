import logging

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from db import check_db_connection
from routers import admin, chat, session, verify
from services.admin import AdminError

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
app.include_router(admin.router)


@app.exception_handler(AdminError)
async def admin_error(request: Request, exc: AdminError) -> JSONResponse:
    detail = {"error": exc.error, "error_description": exc.description, **exc.extra}
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.get("/health")
async def health(response: Response):
    db_ok = await check_db_connection()
    if not db_ok:
        response.status_code = 503
        return {"status": "error", "db": "error"}
    return {"status": "ok", "db": "ok"}
