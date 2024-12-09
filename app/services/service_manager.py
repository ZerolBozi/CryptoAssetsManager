from typing import Optional

from app.database.connection import MongoDB
from app.database.asset_history import AssetHistoryDB
from app.services.currency_service import CurrencyService
from app.services.websocket_service import WebSocketService
from app.services.asset_history_service import AssetHistoryService
from app.services.exchange.base_exchange import BaseExchange
from app.services.exchange.quote_service import QuoteService
from app.services.exchange.wallet_service import WalletService
from app.services.exchange.trading_service import TradingService
from app.services.exchange.transfer_service import TransferService

class ServiceManager:
    _base_exchange: Optional[BaseExchange] = None
    _quote_service: Optional[QuoteService] = None
    _wallet_service: Optional[WalletService] = None
    _trading_service: Optional[TradingService] = None
    _transfer_service: Optional[TransferService] = None
    _asset_history_db: Optional[AssetHistoryDB] = None
    _asset_processor: Optional[AssetHistoryService] = None
    _currency_service: Optional[CurrencyService] = None
    _websocket_service: Optional[WebSocketService] = None

    @classmethod
    def get_base_exchange(cls) -> BaseExchange:
        if cls._base_exchange is None:
            cls._base_exchange = BaseExchange()
        return cls._base_exchange

    @classmethod
    def get_quote_service(cls) -> QuoteService:
        if cls._quote_service is None:
            cls._quote_service = QuoteService()
        return cls._quote_service

    @classmethod
    def get_trading_service(cls) -> TradingService:
        if cls._trading_service is None:
            cls._trading_service = TradingService(cls.get_quote_service())
        return cls._trading_service
    
    @classmethod
    def get_transfer_service(cls) -> TransferService:
        if cls._transfer_service is None:
            cls._transfer_service = TransferService()
        return cls._transfer_service

    @classmethod
    def get_wallet_service(cls) -> WalletService:
        if cls._wallet_service is None:
            cls._wallet_service = WalletService(
                cls.get_quote_service(),
                cls.get_trading_service()
            )
        return cls._wallet_service

    @classmethod
    def get_asset_history_db(cls) -> AssetHistoryDB:
        if cls._asset_history_db is None:
            mongo_client = MongoDB.get_client()
            cls._asset_history_db = AssetHistoryDB(mongo_client)
        return cls._asset_history_db

    @classmethod
    def get_asset_processor(cls) -> AssetHistoryService:
        if cls._asset_processor is None:
            cls._asset_processor = AssetHistoryService(
                cls.get_wallet_service(),
                cls.get_asset_history_db()
            )
        return cls._asset_processor

    @classmethod
    def get_currency_service(cls) -> CurrencyService:
        if cls._currency_service is None:
            cls._currency_service = CurrencyService()
        return cls._currency_service

    @classmethod
    def get_websocket_service(cls) -> WebSocketService:
        if cls._websocket_service is None:
            cls._websocket_service = WebSocketService()
        return cls._websocket_service

    @classmethod
    async def initialize_services(cls):
        try:
            # Initialize all required services
            base_exchange = cls.get_base_exchange()
            await base_exchange.initialize_exchanges_by_server()

            wallet_service = cls.get_wallet_service()
            
            transfer_service = cls.get_transfer_service()
            
            asset_history_db = cls.get_asset_history_db()
            
            # Initialize exchanges in wallet service
            await wallet_service.initialize_exchanges_by_server()

            await transfer_service.initialize_exchanges_by_server()
            
            # Initialize database indexes
            await asset_history_db.create_indexes()
            
            # Initialize websocket service if needed
            websocket_service = cls.get_websocket_service()
            
            print("Services initialized successfully")

        except Exception as e:
            print(f"Failed to initialize services: {str(e)}")
            raise

    @classmethod
    async def cleanup_services(cls):
        try:
            if cls._base_exchange:
                for exchange_name, exchange in cls._base_exchange.exchanges.items():
                    try:
                        await exchange.close()
                        print(f"Closed connection to {exchange_name}")
                    except Exception as e:
                        print(f"Error closing {exchange_name} connection: {str(e)}")

            # Cleanup websocket service
            if cls._websocket_service:
                await cls._websocket_service.stop()

        except Exception as e:
            print(f"Error during cleanup: {str(e)}")