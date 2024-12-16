from decimal import Decimal
from contextlib import asynccontextmanager
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query, WebSocket
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import settings
from app.database.connection import MongoDB
from app.services.service_manager import ServiceManager
from app.structures.response_structure import BaseResponse, BaseDataResponse
from app.structures.request_structure import AssetCostUpdate, ExchangeSettingsUpdate

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
            try:
                yesterday = datetime.now(timezone.utc) - timedelta(days=1)
                yesterday_timestamp = int(yesterday.timestamp() * 1000)
                yesterday_timestamp = (yesterday_timestamp // 86400000) * 86400000
                
                asset_history_service = ServiceManager.get_asset_history_service()
                success = await asset_history_service.update_daily_snapshot(timestamp=yesterday_timestamp)
                
                if success:
                    print(f"Successfully updated asset history for {yesterday.date()}")
                else:
                    print(f"Failed to update asset history for {yesterday.date()}")
            except Exception as e:
                print(f"Error in daily asset update: {e}")

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


@app.post(f"{settings.API_PREFIX}/exchanges/settings")
async def update_exchange_settings(data: ExchangeSettingsUpdate) -> BaseResponse:
    """
    Set API keys and secrets for exchanges.
    Parameters:
        apis: Dict with exchange names as keys and API keys/secrets as values

    Returns:
        BaseResponse(status, message)
    """
    try:
        base_exchange = ServiceManager.get_base_exchange()

        apis = {
            exchange: {
                "apiKey": settings.api_key,
                "secret": settings.secret
            } for exchange, settings in data.exchanges.items()
        }

        await base_exchange.initialize_exchanges(apis)
        results = await base_exchange.ping_exchanges()

        failed_exchanges = [name for name, result in results.items() if not result]

        if failed_exchanges:
            return BaseResponse(
                status="error",
                message=f"Failed to connect to exchanges: {', '.join(failed_exchanges)}"
            )

        return BaseResponse(
            status="success",
            message="API keys set successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set API keys: {str(e)}")


@app.get(f"{settings.API_PREFIX}/exchanges/initialize")
async def initialize_exchanges() -> BaseResponse:
    """
    Reinitialize all exchange connections.
    Returns:
        BaseResponse(status, message)
    """
    try:
        base_exchange = ServiceManager.get_base_exchange()
        await base_exchange.initialize_exchanges_by_server()
        return BaseResponse(
            status="success", 
            message="Exchanges initialized successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to initialize exchanges: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/exchanges/status")
async def ping_exchanges() -> BaseDataResponse:
    """
    Quickly check connection status for all exchanges.
    """
    try:
        base_exchange = ServiceManager.get_base_exchange()
        results = await base_exchange.ping_exchanges()
        return BaseDataResponse(
            status="success",
            data=results
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to ping exchanges: {str(e)}"
        )


@app.post(f"{settings.API_PREFIX}/assets/cost")
async def update_asset_cost(data: AssetCostUpdate) -> BaseResponse:
    """
    Update asset cost for a specific exchange and symbol.
    
    Parameters:
        exchange: Exchange name (e.g. 'binance')
        symbol: Trading pair symbol (e.g. 'BTC')
        cost: Asset cost as string to maintain precision
    
    Returns:
        BaseResponse(status, message)
    """
    try:
        asset_cost_db = ServiceManager.get_asset_cost_db()
        success = await asset_cost_db.update_asset_cost(
            exchange=data.exchange,
            symbol=data.symbol,
            avg_price=Decimal(data.cost),
            update_by="Client"
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update asset cost"
            )

        asset_db = ServiceManager.get_asset_db()
        success = await asset_db.update_avg_price(
            exchange=data.exchange,
            symbol=data.symbol,
            avg_price=Decimal(data.cost)
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update asset cost in assets"
            )
        
        return BaseResponse(
            status="success",
            message="Asset cost updated successfully"
        )
        
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid cost value"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to update asset cost: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/assets/history")
async def get_asset_history(
    period: int = Query(
        default=30,
        description="Time period for history in days (1-730)",
        ge=1,
        le=730,
    ),
) -> BaseDataResponse:
    """
    Get asset history for specified time period.

    Parameters:
        period: Time period for history in days (1-730)

    Returns:
        BaseDataResponse(status, data)
    """
    try:
        asset_history_service = ServiceManager.get_asset_history_service()
        history_data = await asset_history_service.get_asset_history(period)

        if not history_data:
            return BaseDataResponse(
                status="error",
                data=[]
            )

        return BaseDataResponse(
            status="success",
            data=history_data
        )
    except Exception as e:
        print(f"Error fetching asset history: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch asset history: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/assets")
async def get_assets(
    min_value: Optional[float] = Query(
        default=1, description="Minimum value threshold in USDT"
    ),
) -> BaseDataResponse:
    """
    Get all spot assets from all exchanges.
    Parameters:
        min_value_threshold: Minimum value threshold in USDT (default: 1)
    Returns:
        Dict with assets data from all exchanges
    """
    try:
        asset_db = ServiceManager.get_asset_db()
        recent_asset = await asset_db.get_asset_by_time_diff(CACHE_TTL)

        if recent_asset:
            assets = await asset_db.get_all_assets()
            exchanges_data = {}
            for asset in assets:
                if Decimal(asset["value_in_usdt"]) < min_value:
                    continue
                exchange = asset["exchange"]
                if exchange not in exchanges_data:
                    exchanges_data[exchange] = {}
                exchanges_data[exchange][asset["symbol"]] = asset

            asset_history_db = ServiceManager.get_asset_history_db()
            summary = await asset_history_db.get_latest_snapshot()

            return BaseDataResponse(
                status="success",
                data={
                    "exchanges": exchanges_data,
                    "summary": summary
                }
            )
        
        wallet_service = ServiceManager.get_wallet_service()
        assets = await wallet_service.get_assets(Decimal(min_value))
        
        return BaseDataResponse(
            status="success",
            data=assets
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch assets: {str(e)}")


@app.get(f"{settings.API_PREFIX}/rates/usdt-twd")
async def get_usdt_twd_rate() -> BaseDataResponse:
    """Get USDT to TWD exchange rate from MAX"""
    try:
        base_exchange = ServiceManager.get_base_exchange()
        quote_service = ServiceManager.get_quote_service()
        rate = await quote_service.get_current_price(base_exchange.exchanges['bitopro'], "USDT/TWD")
        if rate:
            return BaseDataResponse(
                status="success",
                data={"rate": rate, "timestamp": datetime.now().isoformat()}
            )
        return BaseResponse(
            status="error",
            message="Could not fetch exchange rate"
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Could not fetch exchange rate: {str(e)}")


@app.get(f"{settings.API_PREFIX}/deposits/networks")
async def get_deposit_networks(exchange: str, symbol: str) -> BaseDataResponse | BaseResponse:
    """
    Get deposit networks for a symbol from an exchange.
    Parameters:
        exchange: Exchange name, lowercase (e.g. 'binance')
        symbol: Trading pair symbol (e.g. 'BTC')
    Returns:
        BaseDataResponse(status, data) | BaseResponse(status, message)
    """
    try:
        transfer_service = ServiceManager.get_transfer_service()
        _exchange = transfer_service.exchanges.get(exchange, None)
        if _exchange is not None:
            networks = await transfer_service.get_deposit_networks(_exchange, symbol)
            return BaseDataResponse(
                status="success",
                data=networks
            )
        return BaseResponse(
            status="error",
            message="Exchange not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get deposit networks: {str(e)}"
        )


@app.get(f"{settings.API_PREFIX}/deposits/address")
async def get_deposit_address(exchange: str, symbol: str, network: str) -> BaseDataResponse:
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
        return BaseDataResponse(
            status="success",
            data=address
        )
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
