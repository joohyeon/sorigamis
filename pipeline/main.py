from __future__ import annotations
from fastapi import FastAPI
from routers import jobs

app = FastAPI(title="sg-pipeline")
app.include_router(jobs.router)

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
