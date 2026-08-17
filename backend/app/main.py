import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_hikes import router as hikes_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Swiss Hike Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hikes_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
