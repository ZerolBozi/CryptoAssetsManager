from contextlib import asynccontextmanager
from typing import Dict, Union, Optional, List
from datetime import datetime, timezone, timedelta

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query, WebSocket
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import settings
from app.database.connection import MongoDB
from app.services.service_manager import ServiceManager
from app.structures.asset_structure import AssetSnapshot

# 快取週期
CACHE_TTL = 60000


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for handling startup and shutdown events.
    Initializes exchanges when the application starts.
    """
    try:
        # Startup
        await MongoDB.connect()
        await ServiceManager.initialize_services()

        scheduler = AsyncIOScheduler()

        async def update_daily_assets():
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            yesterday_timestamp = int(yesterday.timestamp() * 1000)
            yesterday_timestamp = (yesterday_timestamp // 86400000) * 86400000
            asset_processor = ServiceManager.get_asset_processor()
            await asset_processor.update_daily_snapshot(timestamp=yesterday_timestamp)

        scheduler.add_job(update_daily_assets, "cron", hour=0, minute=0, timezone="UTC")

        scheduler.add_listener(
            lambda event: print(
                f"Job executed: {event.job_id}, executed at {event.scheduled_run_time}"
            ),
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        scheduler.start()
        print("Daily asset update scheduler started")

    except Exception as e:
        print(f"Failed to initialize exchanges: {str(e)}")

    yield

    # Shutdown
    scheduler.shutdown()
    await ServiceManager.cleanup_services()


app = FastAPI(
    title="Crypto Asset Manager",
    description="Manage crypto assets across multiple exchanges",
    version=settings.API_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.post(f"{settings.API_PREFIX}/update_exchange_settings")
async def update_exchange_settings(apis: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """
    Set API keys and secrets for exchanges.
    Parameters:
        apis: Dict with exchange names as keys and API keys/secrets as values

    Returns:
        Dict with status message
    """
    try:
        base_exchange = ServiceManager.get_base_exchange()
        await base_exchange.initialize_exchnages(apis)
        results = await base_exchange.ping_exchanges()

        failed_exchanges = [name for name, result in results.items() if not result]

        if failed_exchanges:
            return {
                "status": "error",
                "message": f"Failed to connect to exchanges: {', '.join(failed_exchanges)}",
            }

        return {"status": "success", "message": "API keys set successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set API keys: {str(e)}")


@app.get(f"{settings.API_PREFIX}/initialize")
async def initialize_exchanges() -> Dict[str, str]:
    """
    Reinitialize all exchange connections.
    Returns:
        Dict with status message
    """
    try:
        base_exchange = ServiceManager.get_base_exchange()
        await base_exchange.initialize_exchanges_by_server()
        return {"status": "success", "message": "Exchanges initialized successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to initialize exchanges: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/ping")
async def ping_exchanges() -> Dict[str, Union[Dict[str, Union[bool, str]], str]]:
    """
    Quickly check connection status for all exchanges.
    """
    try:
        base_exchange = ServiceManager.get_base_exchange()
        results = await base_exchange.ping_exchanges()
        return {"status": "success", "data": results}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to ping exchanges: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/asset_history")
async def get_asset_history(
    period: int = Query(
        default=30,
        description="Time period for history (30, 90, 180, 365)",
        ge=30,
        le=365,
        values=[30, 90, 180, 365],
    ),
) -> Dict[str, Union[str, List[Dict]]]:
    """
    Get asset history for specified time period.

    Parameters:
        period: Time period for history (30, 90, 180, 365)

    Returns:
        Dict containing status and history data
    """
    try:
        asset_processor = ServiceManager.get_asset_processor()
        history_data = await asset_processor.get_asset_history(period)

        return {"status": "success", "data": history_data}
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch asset history: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/assets")
async def get_assets(
    min_value: Optional[float] = Query(
        default=1, description="Minimum value threshold in USDT"
    ),
) -> Dict[str, Union[Dict, str]]:
    """
    Get all spot assets from all exchanges.
    Parameters:
        min_value_threshold: Minimum value threshold in USDT (default: 1)
    Returns:
        Dict with assets data from all exchanges
    """
    try:
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        asset_processor = ServiceManager.get_asset_processor()
        snapshot_data: AssetSnapshot = await asset_processor.get_latest_snapshot()

        if (snapshot_data) and (current_time - snapshot_data.update_time < CACHE_TTL):
            return {"status": "success", "data": snapshot_data.to_dict()}

        wallet_service = ServiceManager.get_wallet_service()
        assets = await wallet_service.get_assets(min_value=min_value)

        await asset_processor.update_daily_snapshot(assets=assets)

        return {"status": "success", "data": assets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch assets: {str(e)}")


@app.get(f"{settings.API_PREFIX}/exchange_rate/usdt_twd")
async def get_usdt_twd_rate():
    """Get USDT to TWD exchange rate from MAX"""
    try:
        currency_service = ServiceManager.get_currency_service()
        rate = await currency_service.get_usdt_twd_rate()
        if rate:
            return {
                "status": "success",
                "data": {"rate": rate, "timestamp": datetime.now().isoformat()},
            }
        return {"status": "error", "data": {}}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Could not fetch exchange rate")


@app.get(f"{settings.API_PREFIX}/deposit_networks")
async def get_deposit_networks(exchange: str, symbol: str) -> Dict:
    """
    Get deposit networks for a symbol from an exchange.
    Parameters:
        exchange: Exchange name, lowercase (e.g. 'binance')
        symbol: Trading pair symbol (e.g. 'BTC')
    Returns:
        Dict with deposit networks
    """
    try:
        transfer_service = ServiceManager.get_transfer_service()
        _exchange = transfer_service.exchanges.get(exchange, None)
        if _exchange is not None:
            networks = await transfer_service.get_deposit_networks(_exchange, symbol)
            return {"status": "success", "data": networks}
        return {"status": "error", "message": "Exchange not found"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get deposit networks: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/deposit_address")
async def get_deposit_address(exchange: str, symbol: str, network: str) -> Dict:
    """
    Get deposit address for a symbol from an exchange.
    Parameters:
        exchange: Exchange name, lowercase (e.g. 'binance') ['binance', 'okx', 'mexc', 'gateio']
        symbol: Trading pair symbol (e.g. 'BTC')
        network: Network (e.g. 'TRC20')
    Returns:
        Dict with deposit address
    """
    try:
        transfer_service = ServiceManager.get_transfer_service()
        address = await transfer_service.get_deposit_address(exchange, symbol, network)
        return {"status": "success", "data": address}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get deposit address: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/ping_ws")
async def ping_websocket() -> Dict[str, str]:
    """
    Check if WebSocket service is running.
    """
    try:
        ws_service = ServiceManager.get_websocket_service()
        if ws_service.is_running:
            return {"status": "success", "message": "WebSocket service is running"}
        else:
            return {"status": "inactive", "message": "WebSocket service is not running"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error checking WebSocket status: {str(e)}"
        )


@app.post(f"{settings.API_PREFIX}/connect_ws")
async def connect_websocket() -> Dict[str, str]:
    """
    Initialize and start WebSocket service.
    """
    try:
        ws_service = ServiceManager.get_websocket_service()
        if not ws_service.is_running:
            await ws_service.initialize()
            await ws_service.start_watching()
            return {
                "status": "success",
                "message": "WebSocket service started successfully",
            }
        return {"status": "success", "message": "WebSocket service is already running"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start WebSocket service: {str(e)}"
        )


@app.post(f"{settings.API_PREFIX}/disconnect_ws")
async def disconnect_websocket() -> Dict[str, str]:
    """
    Stop WebSocket service and disconnect all clients.
    """
    try:
        ws_service = ServiceManager.get_websocket_service()
        if ws_service.is_running:
            await ws_service.stop()
            return {
                "status": "success",
                "message": "WebSocket service stopped successfully",
            }
        return {"status": "success", "message": "WebSocket service is already stopped"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop WebSocket service: {str(e)}"
        )


@app.websocket("/ws/klines")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for kline data streaming
    """
    ws_service = ServiceManager.get_websocket_service()
    if not ws_service.is_running:
        await websocket.close(code=1000, reason="WebSocket service is not running")
        return

    await ws_service.register_client(websocket)


# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    return {"status": "error", "message": str(exc), "path": request.url.path}
