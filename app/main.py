from datetime import datetime
from typing import Dict, Union, Optional
from contextlib import asynccontextmanager

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query, WebSocket

from app.config import settings
from app.services.exchange_service import ExchangeService
from app.services.currency_service import CurrencyService
from app.services.websocket_service import WebSocketService

service = ExchangeService()
service.price_cache_ttl = 30
service.trade_cache_ttl = 600

currency_service = CurrencyService()

ws_service = WebSocketService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for handling startup and shutdown events.
    Initializes exchanges when the application starts.
    """
    try:
        # Startup
        await service.initialize_exchanges()
        print("Exchanges initialized successfully")
    except Exception as e:
        print(f"Failed to initialize exchanges: {str(e)}")
    
    yield
    
    # Shutdown
    for exchange_name, exchange in service.exchanges.items():
        try:
            await exchange.close()
            print(f"Closed connection to {exchange_name}")
        except Exception as e:
            print(f"Error closing {exchange_name} connection: {str(e)}")

    await ws_service.stop()

app = FastAPI(
    title="Crypto Asset Manager",
    description="Manage crypto assets across multiple exchanges",
    version=settings.API_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get(f"{settings.API_PREFIX}/initialize")
async def initialize_exchanges() -> Dict[str, str]:
    """
    Reinitialize all exchange connections.
    Returns:
        Dict with status message
    """
    try:
        await service.initialize_exchanges()
        return {"status": "success", "message": "Exchanges initialized successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize exchanges: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/ping")
async def ping_exchanges() -> Dict[str, Union[Dict[str, Union[bool, str]], str]]:
    """
    Quickly check connection status for all exchanges.
    """
    try:
        results = await service.ping_exchanges()
        return {
            "status": "success",
            "data": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to ping exchanges: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/assets")
async def get_assets(
        min_value_threshold: Optional[float] = Query(default=0.1, description="Minimum value threshold in USDT")
    ) -> Dict[str, Union[Dict, str]]:
    """
    Get all spot assets from all exchanges.
    Parameters:
        min_value_threshold: Minimum value threshold in USDT (default: 0.1)
    Returns:
        Dict with assets data from all exchanges
    """
    try:
        assets = await service.get_all_spot_assets(min_value_threshold=min_value_threshold)
        return {
            "status": "success",
            "data": assets
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch assets: {str(e)}"
        )
    
@app.get(f"{settings.API_PREFIX}/exchange_rate/usdt_twd")
async def get_usdt_twd_rate():
    """Get USDT to TWD exchange rate from MAX"""
    rate = await currency_service.get_usdt_twd_rate()
    if rate:
        return {
            "rate": rate,
            "timestamp": datetime.now().isoformat()
        }
    raise HTTPException(
        status_code=503, 
        detail="Could not fetch exchange rate"
    )
    
@app.get(f"{settings.API_PREFIX}/ping_ws")
async def ping_websocket() -> Dict[str, str]:
    """
    Check if WebSocket service is running.
    """
    try:
        if ws_service.is_running:
            return {
                "status": "success",
                "message": "WebSocket service is running"
            }
        else:
            return {
                "status": "inactive",
                "message": "WebSocket service is not running"
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error checking WebSocket status: {str(e)}"
        )

@app.post(f"{settings.API_PREFIX}/connect_ws")
async def connect_websocket() -> Dict[str, str]:
    """
    Initialize and start WebSocket service.
    """
    try:
        if not ws_service.is_running:
            await ws_service.initialize()
            await ws_service.start_watching()
            return {
                "status": "success",
                "message": "WebSocket service started successfully"
            }
        return {
            "status": "success",
            "message": "WebSocket service is already running"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start WebSocket service: {str(e)}"
        )
    
@app.post(f"{settings.API_PREFIX}/disconnect_ws")
async def disconnect_websocket() -> Dict[str, str]:
    """
    Stop WebSocket service and disconnect all clients.
    """
    try:
        if ws_service.is_running:
            await ws_service.stop()
            return {
                "status": "success",
                "message": "WebSocket service stopped successfully"
            }
        return {
            "status": "success",
            "message": "WebSocket service is already stopped"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop WebSocket service: {str(e)}"
        )

@app.websocket("/ws/klines")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for kline data streaming
    """
    if not ws_service.is_running:
        await websocket.close(code=1000, reason="WebSocket service is not running")
        return
        
    await ws_service.register_client(websocket)

# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    return {
        "status": "error",
        "message": str(exc),
        "path": request.url.path
    }