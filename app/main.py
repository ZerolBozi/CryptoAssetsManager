import os
import json
from decimal import Decimal
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import settings
from app.database.connection import MongoDB
from app.services.service_manager import ServiceManager
from app.structures.response_structure import BaseResponse, BaseDataResponse
from app.structures.request_structure import (
    AssetCostUpdate, ExchangeSettingsUpdate, ChartSaveRequest, 
    OpenOrderRequest, TransferRequest
)
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
                "secret": settings.secret,
                "password": settings.password if hasattr(settings, 'password') else None
            } for exchange, settings in data.exchanges.items()
            if settings.api_key and settings.secret
        }

        await base_exchange.initialize_exchanges(apis)

        results = await base_exchange.ping_exchanges()

        if results:
            return BaseResponse(
                status="success",
                message="API keys set successfully"
            )
        
        failed_exchanges = [name for name, result in results.items() if not result]

        if failed_exchanges:
            return BaseResponse(
                status="error",
                message=f"Failed to connect to exchanges: {', '.join(failed_exchanges)}"
            )
        else:
            return BaseResponse(
                status="error",
                message="Failed to connect to any exchanges"
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


@app.get(f"{settings.API_PREFIX}/exchanges/list")
async def list_exchanges() -> BaseDataResponse:
    """
    List all available exchanges.
    Returns:
        Dict with exchange names and status
    """
    try:
        base_exchange = ServiceManager.get_base_exchange()
        exchanges = base_exchange.exchanges.keys()
        return BaseDataResponse(
            status="success",
            data=exchanges
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list exchanges: {str(e)}"
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


@app.get(f"{settings.API_PREFIX}/orders")
async def get_orders(
        exchange: Optional[str] = Query(default=None, description="Exchange name"),
        symbol: Optional[str] = Query(default=None, description="Trading pair symbol"),
        status: Optional[str] = Query(default=None, description="Order status"),
        limit: Optional[int] = Query(default=20, description="Limit number of orders to fetch")
    ) -> BaseDataResponse:
    """
    Get open orders from all exchanges.
    Returns:
        Dict with open orders data
    """
    try:
        order_db = ServiceManager.get_order_db()
        orders = await order_db.find_orders(
            exchange=exchange,
            symbol=symbol,
            status=status,
            limit=limit
        )
        
        return BaseDataResponse(
            status="success",
            data=orders
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch open orders: {str(e)}"
        )
    

@app.post(f"{settings.API_PREFIX}/orders")
async def create_order(data: OpenOrderRequest) -> BaseDataResponse | BaseResponse:
    """
    Open a trading position
    
    Parameters:
        exchange: Exchange name (e.g. 'binance')
        symbol: Trading pair symbol (e.g. 'BTC/USDT')
        side: Order side ('buy' or 'sell')
        order_type: Order type ('market' or 'limit')
        cost: Order amount in quote currency (e.g. USDT)
        price: Limit price (optional, required for limit orders)
        
    Returns:
        BaseDataResponse with order details
    """
    try:
        order_db = ServiceManager.get_order_db()
        trading_service = ServiceManager.get_trading_service()
        exchange = trading_service.exchanges.get(data.exchange)
        
        if not exchange:
            return BaseResponse(
                status="error",
                message=f"Exchange {data.exchange} not found"
            )

        order = await trading_service.place_order_with_cost(
            exchange=exchange,
            symbol=data.symbol,
            side=data.side,
            order_type=data.order_type,
            cost=data.cost,
            price=data.price
        )
        
        if isinstance(order, str):
            return BaseResponse(
                status="error",
                message=order
            )
            
        await order_db.save_order(order)

        if order:
            return BaseDataResponse(
                status="success",
                data=order.model_dump()
            )
        return BaseResponse(
            status="error",
            message="Failed to place order"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to place order: {str(e)}"
        )
    
@app.post(f"{settings.API_PREFIX}/orders/cancel")
async def cancel_order(order_id: str) -> BaseResponse:
    """
    Cancel an open order
    
    Parameters:
        order_id: Order ID
    
    Returns:
        BaseResponse with status and message
    """
    try:
        order_db = ServiceManager.get_order_db()
        trading_service = ServiceManager.get_trading_service()
        order = await order_db.get_order_by_id(order_id)
        
        if not order:
            return BaseResponse(
                status="error",
                message="Order not found"
            )
        
        exchange = trading_service.exchanges.get(order.get('exchange', ''))
        symbol = order.get('symbol', '')
        
        if (not exchange) or (not symbol):
            return BaseResponse(
                status="error",
                message=f"Exchange or symbol not found"
            )
        
        new_order = await trading_service.cancel_order(exchange, symbol, order_id)
        success = await order_db.update_order(order_id, new_order)
        
        if success:
            return BaseResponse(
                status="success",
                message="Order cancelled successfully"
            )
        
        return BaseResponse(
            status="error",
            message="Failed to cancel order"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel order: {str(e)}"
        )
    

@app.post(f"{settings.API_PREFIX}/transfer")
async def transfer_between_exchange(data: TransferRequest) -> BaseDataResponse | BaseResponse:
    """
    Transfer funds between exchanges.
    
    Parameters:
        from_exchange: Exchange name to transfer from (e.g. 'binance')
        to_exchange: Exchange name to transfer to (e.g. 'kucoin')
        currency: Currency to transfer (e.g. 'BTC')
        amount: Amount to transfer
        network: Network for transfer (e.g. 'TRC20')
    
    Returns:
        BaseDataResponse with transfer details
    """
    try:
        transaction_db = ServiceManager.get_transaction_db()
        transfer_service = ServiceManager.get_transfer_service()
        transaction = await transfer_service.transfer_between_exchange(
            from_exchange_name=data.from_exchange,
            to_exchange_name=data.to_exchange,
            currency=data.currency,
            amount=data.amount,
            network=data.network
        )
        if transaction:
            await transaction_db.save_transaction(transaction)
            return BaseDataResponse(
                status="success",
                data=transaction.model_dump()
            )
        else:
            return BaseResponse(
                status="error",
                message="Failed to transfer funds"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to transfer funds: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/networks/common")
async def get_common_networks(
    from_exchange: str = Query(..., description="Source exchange"),
    to_exchange: str = Query(..., description="Destination exchange"),
    currency: str = Query(..., description="Currency symbol"),
) -> BaseDataResponse:
    """
    Get common networks between two exchanges for a specific symbol.
    
    Parameters:
        from_exchange: Source exchange name (e.g. 'binance')
        to_exchange: Destination exchange name (e.g. 'kucoin')
        symbol: Currency symbol (e.g. 'BTC')
        
    Returns:
        List of common networks supported by both exchanges
    """
    try:
        transfer_service = ServiceManager.get_transfer_service()
        networks = await transfer_service.get_common_networks(
            from_exchange, 
            to_exchange, 
            currency
        )
        
        return BaseDataResponse(
            status="success",
            data=networks
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get common networks: {str(e)}"
        )

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
        networks = await transfer_service.get_deposit_networks(exchange, symbol)
        if networks:
            return BaseDataResponse(
                status="success",
                data=networks
            )
        else:
            return BaseResponse(
                status="error",
                message="Exchange not found or Symbol not supported"
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
    
@app.get(f"{settings.API_PREFIX}/charts/latest")
async def get_latest_chart() -> BaseDataResponse:
    try:
        chart_storage_db = ServiceManager.get_chart_storage_db()
        chart = await chart_storage_db.get_latest_chart()

        if not chart:
            return BaseDataResponse(
                status="error",
                data=None
            )

        return BaseDataResponse(
            status="success",
            data=chart
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get latest chart: {str(e)}"
        )
    
@app.post(f"{settings.API_PREFIX}/charts/save")
async def save_chart(data: ChartSaveRequest) -> BaseResponse:
    try:
        chart_storage_db = ServiceManager.get_chart_storage_db()
        success = await chart_storage_db.save_chart(
            name=data.name,
            content=data.content,
            symbol=data.symbol,
            resolution=data.resolution
        )

        if success:
            return BaseResponse(
                status="success",
                message="Chart saved successfully"
            )
        return BaseResponse(
            status="error",
            message="Failed to save chart"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to save chart: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/charts/load")
async def load_chart(
    id: int = Query(..., description="Chart id")
) -> BaseDataResponse:
    try:
        chart_storage_db = ServiceManager.get_chart_storage_db()
        chart = await chart_storage_db.get_chart(
            id=id
        )

        if not chart:
            return BaseDataResponse(
                status="error",
                data=None
            )

        return BaseDataResponse(
            status="success",
            data=chart
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to load chart: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/charts/list")
async def list_charts() -> BaseDataResponse:
    """
    List all saved charts
    """
    try:
        chart_storage_db = ServiceManager.get_chart_storage_db()
        charts = await chart_storage_db.get_all_charts()

        return BaseDataResponse(
            status="success",
            data=charts
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to list charts: {str(e)}"
        )

@app.delete(f"{settings.API_PREFIX}/charts/delete")
async def delete_chart(
    id: int = Query(..., description="Chart id")
) -> BaseResponse:
    """
    Delete chart configuration
    """
    try:
        chart_storage_db = ServiceManager.get_chart_storage_db()
        success = await chart_storage_db.delete_chart(id=id)

        if success:
            return BaseResponse(
                status="success",
                message="Chart deleted successfully"
            )
        return BaseResponse(
            status="error",
            message="Failed to delete chart"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to delete chart: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/quotes/symbols")
async def get_symbols(
    min_value: Optional[float] = Query(
        default=1, description="Minimum value threshold in USDT"
    )
) -> BaseDataResponse:
    try:
        trading_symbols = []
        
        asset_db = ServiceManager.get_asset_db()
        assets = await asset_db.get_all_assets()
        
        for asset in assets:
            if Decimal(asset.get("value_in_usdt", "0")) >= min_value and (asset['symbol'] != "USDT" and asset['symbol'] != "USDC"):
                symbol = f"{asset['symbol']}USDT"
                trading_symbols.append({
                    "symbol": symbol,
                    "full_name": f"{asset['exchange'].upper()}:{symbol}",
                    "description": f"{asset['symbol']} / Tether",
                    "exchange": asset['exchange'].upper(),
                    "type": "balance"
                })
        
        try:
            possible_paths = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "symbol_exchange_mapping.json"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                            "CryptoAssetsManager", 
                            "symbol_exchange_mapping.json"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            "symbol_exchange_mapping.json")
            ]

            file_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    file_path = path
                    break

            with open(file_path, "r") as f:
                mapping_data = json.load(f)
                
            for exchange, symbols in mapping_data.items():
                if exchange == "Upbit":
                    continue

                for symbol in symbols:
                    symbol_with_usdt = f"{symbol}USDT"
                    existing = next(
                        (item for item in trading_symbols 
                         if item["symbol"] == symbol_with_usdt and 
                         item["exchange"] == exchange.upper()),
                        None
                    )
                    
                    if not existing:
                        trading_symbols.append({
                            "symbol": symbol_with_usdt,
                            "full_name": f"{exchange.upper()}:{symbol_with_usdt}",
                            "description": f"{symbol} / Tether",
                            "exchange": exchange.upper(),
                            "type": "watch list"
                        })
        
        except FileNotFoundError:
            print("Symbol mapping file not found")
            
        return BaseDataResponse(
            status="success",
            data=trading_symbols
        )
        
    except Exception as e:
        print(f"Error getting trading symbols: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get trading symbols: {str(e)}"
        )
    
@app.get(f"{settings.API_PREFIX}/quotes/history")
async def get_quote_history(
    symbol: str = Query(..., description="Trading pair symbol"),
    exchange: str = Query(..., description="Exchange name"),
    timeframe: str = Query(..., description="Timeframe"),
    since: int = Query(..., description="Start timestamp in milliseconds"),
    end: int = Query(..., description="End timestamp in milliseconds"),
) -> BaseDataResponse:
    """
    Get historical price data for a symbol from an exchange.
    Parameters:
        symbol: Trading pair symbol (e.g. 'BTC/USDT')
        exchange: Exchange name (e.g. 'binance')
        timeframe: Timeframe (e.g. '1d')
        since: Start timestamp (milliseconds)
        end: End timestamp (milliseconds)
    Returns:
        Dict with historical price data
    """
    try:
        quote_service = ServiceManager.get_quote_service()
        exchange = quote_service.exchanges.get(exchange)
        history = await quote_service.get_price_history(
            exchange, symbol, timeframe, since, end
        )

        return BaseDataResponse(
            status="success",
            data=history['data']
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get quote history: {str(e)}"
        )

@app.get(f"{settings.API_PREFIX}/quotes/latest")
async def get_latest_quote(
    symbol: str = Query(..., description="Trading pair symbol"),
    exchange: str = Query(..., description="Exchange name")
) -> BaseDataResponse:
    """
    Get latest price data for a symbol from an exchange.
    Parameters:
        symbol: Trading pair symbol (e.g. 'BTC/USDT')
        exchange: Exchange name (e.g. 'binance')
    Returns:
        Dict with latest price data
    """
    try:
        quote_service = ServiceManager.get_quote_service()
        exchange = quote_service.exchanges.get(exchange)
        latest = await quote_service.get_current_price(exchange, symbol)

        return BaseDataResponse(
            status="success",
            data=latest
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get latest quote: {str(e)}"
        )

@app.websocket("/ws/quotes/{data_type}/{exchange}/{symbol}")
async def websocket_endpoint(
    websocket: WebSocket,
    data_type: str,
    exchange: str, 
    symbol: str,
    timeframe: str = Query(default="1m")
) -> None:
    websocket_service = ServiceManager.get_websocket_service()
    try:
        await websocket_service.connect(websocket)
        
        await websocket_service.subscribe(
            exchange_name=exchange,
            symbol=symbol, 
            websocket=websocket,
            data_type=data_type,
            timeframe=timeframe
        )
        
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
            
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        
    finally:
        await websocket_service.disconnect(websocket)

# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    return {"status": "error", "message": str(exc), "path": request.url.path}
