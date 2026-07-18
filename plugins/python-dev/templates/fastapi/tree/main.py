"""Composition root — the only module that imports concrete adapters.

Wiring happens in the lifespan context manager; dependencies are exposed
via app.state getters (per worker).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.health.router import router as health_router
from config import Config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.config = Config.from_env()
    # Wire concrete adapters here and expose them via app.state.
    yield


app = FastAPI(title="{{name}}", lifespan=lifespan)
app.include_router(health_router)


if __name__ == "__main__":
    import uvicorn

    config = Config.from_env()
    uvicorn.run("main:app", host=config.host, port=config.port)
