from __future__ import annotations
from fastapi import FastAPI
from routers import jobs, skills, modes

app = FastAPI(title="sg-pipeline")
app.include_router(jobs.router)
app.include_router(skills.router)
app.include_router(modes.router)

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
