from typing import Dict, Union, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.exchange_service import ExchangeService

service = ExchangeService()
service.price_cache_ttl = 30
service.trade_cache_ttl = 600

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

# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    return {
        "status": "error",
        "message": str(exc),
        "path": request.url.path
    }