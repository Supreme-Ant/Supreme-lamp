"""FastAPI web dashboard for monitoring the trading bot."""

import logging
import os
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def create_dashboard(
    portfolio_tracker,
    order_manager,
    risk_manager,
    copy_trader=None,
    signal_follower=None,
    ai_trader=None,
    notifier=None,
) -> FastAPI:
    """Create and configure the FastAPI dashboard application."""

    app = FastAPI(title="Crypto Trading Bot Dashboard", version="1.0.0")

    # Mount static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=TEMPLATE_DIR)

    # ── Dashboard Page ────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    # ── Portfolio API ─────────────────────────────────

    @app.get("/api/portfolio/summary")
    async def portfolio_summary():
        try:
            return portfolio_tracker.get_summary()
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/api/portfolio/positions")
    async def portfolio_positions():
        try:
            return portfolio_tracker.get_open_positions()
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/api/portfolio/history")
    async def portfolio_history(days: int = 30):
        try:
            return portfolio_tracker.get_pnl_history(days=days)
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/api/portfolio/performance")
    async def strategy_performance():
        try:
            return portfolio_tracker.get_strategy_performance()
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Trades API ────────────────────────────────────

    @app.get("/api/trades")
    async def get_trades(limit: int = 50, offset: int = 0):
        try:
            return portfolio_tracker.get_trade_history(limit=limit, offset=offset)
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/api/trades/manual")
    async def manual_trade(request: Request):
        try:
            data = await request.json()
            symbol = data.get("symbol")
            side = data.get("side")
            amount = float(data.get("amount", 0))

            if not symbol or not side or amount <= 0:
                raise HTTPException(400, "symbol, side, and amount are required")

            order = order_manager.place_order(
                symbol=symbol,
                side=side,
                amount=amount,
                strategy="manual",
            )
            return order or {"error": "Order rejected by risk manager"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Risk API ──────────────────────────────────────

    @app.get("/api/risk/status")
    async def risk_status():
        try:
            return risk_manager.get_risk_status()
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Strategies API ────────────────────────────────

    @app.get("/api/strategies/status")
    async def strategies_status():
        result = {}
        if copy_trader:
            result["copy"] = copy_trader.get_status()
        if signal_follower:
            result["signal"] = signal_follower.get_status()
        if ai_trader:
            result["ai"] = ai_trader.get_status()
        return result

    @app.get("/api/strategies/signals")
    async def get_signals():
        if ai_trader:
            return ai_trader.get_latest_signals()
        return []

    @app.post("/api/strategies/{strategy}/start")
    async def start_strategy(strategy: str):
        strat = _get_strategy(strategy)
        if strat:
            strat.start()
            return {"status": "started", "strategy": strategy}
        raise HTTPException(404, f"Strategy '{strategy}' not found")

    @app.post("/api/strategies/{strategy}/stop")
    async def stop_strategy(strategy: str):
        strat = _get_strategy(strategy)
        if strat:
            strat.stop()
            return {"status": "stopped", "strategy": strategy}
        raise HTTPException(404, f"Strategy '{strategy}' not found")

    # ── Copy Trading API ──────────────────────────────

    @app.get("/api/leaders")
    async def get_leaders():
        if copy_trader:
            return copy_trader.get_leaders()
        return []

    @app.post("/api/leaders")
    async def add_leader(request: Request):
        if not copy_trader:
            raise HTTPException(400, "Copy trading not available")
        data = await request.json()
        try:
            leader = copy_trader.add_leader(
                external_id=data["external_id"],
                label=data.get("label"),
                allocation_pct=float(data.get("allocation_pct", 0.1)),
            )
            return {"id": leader.id, "external_id": leader.external_id}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.delete("/api/leaders/{external_id}")
    async def remove_leader(external_id: str):
        if copy_trader:
            copy_trader.remove_leader(external_id)
            return {"status": "removed"}
        raise HTTPException(400, "Copy trading not available")

    # ── Positions API ─────────────────────────────────

    @app.post("/api/positions/{position_id}/close")
    async def close_position(position_id: int):
        try:
            order = order_manager.close_position(position_id)
            if order:
                return order
            raise HTTPException(404, "Position not found or already closed")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── Bot Control API ───────────────────────────────

    @app.get("/api/bot/status")
    async def bot_status():
        return {
            "status": "running",
            "mode": "paper" if order_manager.is_paper else "live",
            "strategies": {
                "copy": copy_trader.is_active if copy_trader else False,
                "signal": signal_follower.is_active if signal_follower else False,
                "ai": ai_trader.is_active if ai_trader else False,
            },
        }

    # ── Helpers ───────────────────────────────────────

    def _get_strategy(name: str):
        strategies = {
            "copy": copy_trader,
            "signal": signal_follower,
            "ai": ai_trader,
        }
        return strategies.get(name)

    return app
