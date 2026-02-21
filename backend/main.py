import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.interfaces.api.static_files import static_router

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(filename)-10s %(message)s",
    handlers=[logging.StreamHandler()],
)

app = FastAPI(title="Freedom Routing Backend")

app.include_router(static_router)


@app.get("/health", tags=["health"])
def healthcheck():
    return JSONResponse({"status": "ok"})
