import asyncio
from contextlib import asynccontextmanager

from .trader import run


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(run(), name="quantnifty-trader")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


try:
    from fastapi import FastAPI

    app = FastAPI(
        title="QuantNifty",
        version="1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "quantnifty"}

except ImportError:
    # Keep the local CLI path usable even when web dependencies are absent.
    app = None


if __name__ == "__main__":
    asyncio.run(run())
