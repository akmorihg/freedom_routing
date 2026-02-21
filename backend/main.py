from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Freedom Routing Backend")


@app.get("/health", tags=["health"])
def healthcheck():
    return JSONResponse({"status": "ok"})
