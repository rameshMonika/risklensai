import logging
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core_service.api.auth import router as auth_router
from core_service.api.investigation import router as investigation_router
from core_service.api.portfolio import router as portfolio_router
from core_service.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("core_service")

app = FastAPI(title="Portfolio Risk Investigator - Core Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def debug_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    body = await request.body()
    logger.info("--> %s %s body=%s", request.method, request.url.path, body[:500])

    try:
        response = await call_next(request)
    except Exception:
        tb = traceback.format_exc()
        logger.error("Unhandled exception on %s %s\n%s", request.method, request.url.path, tb)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "traceback": tb.splitlines()},
        )

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "<-- %s %s %s (%.1fms)", request.method, request.url.path, response.status_code, duration_ms
    )
    return response


app.include_router(auth_router)
app.include_router(portfolio_router)
app.include_router(investigation_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
