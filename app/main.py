import asyncio
from contextlib import asynccontextmanager
from datetime import date

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
    from fastapi import FastAPI, HTTPException
    from .daily_reports import write_daily_report

    app = FastAPI(
        title="QuantNifty",
        version="1.1",
        lifespan=lifespan,
        description="PAPER trading monitor and read-only daily audit reports.",
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "quantnifty"}

    @app.get("/reports/{trading_date}")
    async def daily_report(trading_date: str):
        """Generate/read a local daily report. Keep the forwarded Codespace port private."""
        try:
            day = date.fromisoformat(trading_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must use YYYY-MM-DD")
        if day > date.today():
            raise HTTPException(status_code=400, detail="Future reports are not available")
        return write_daily_report(day)

except ImportError:
    # Keep the local CLI path usable when web dependencies are absent.
    app = None


if __name__ == "__main__":
    asyncio.run(run())
