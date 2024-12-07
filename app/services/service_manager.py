from typing import Optional

from app.database.connection import MongoDB
from app.database.asset_history import AssetHistoryDB
from app.services.exchange_service import ExchangeService
from app.services.asset_history_processor import AssetHistoryProcessor
from app.services.currency_service import CurrencyService
from app.services.websocket_service import WebSocketService

class ServiceManager:
    _exchange_service: Optional[ExchangeService] = None
    _asset_history_db: Optional[AssetHistoryDB] = None
    _asset_processor: Optional[AssetHistoryProcessor] = None
    _currency_service: Optional[CurrencyService] = None
    _websocket_service: Optional[WebSocketService] = None

    @classmethod
    def get_exchange_service(cls) -> ExchangeService:
        if cls._exchange_service is None:
            cls._exchange_service = ExchangeService()
        return cls._exchange_service

    @classmethod
    def get_asset_history_db(cls) -> AssetHistoryDB:
        if cls._asset_history_db is None:
            mongo_client = MongoDB.get_client()
            cls._asset_history_db = AssetHistoryDB(mongo_client)
        return cls._asset_history_db

    @classmethod
    def get_asset_processor(cls) -> AssetHistoryProcessor:
        if cls._asset_processor is None:
            cls._asset_processor = AssetHistoryProcessor(
                cls.get_exchange_service(),
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
    async def initialize_all(cls):
        try:
            # Initialize exchange service
            exchange_service = cls.get_exchange_service()
            asset_history_db = cls.get_asset_history_db()
            await exchange_service.initialize_exchanges_by_server()
            await asset_history_db.create_indexes()
            print("Exchanges initialized successfully")

        except Exception as e:
            print(f"Failed to initialize services: {str(e)}")
            raise

    @classmethod
    async def cleanup_all(cls):
        try:
            # Cleanup exchange service
            if cls._exchange_service:
                for exchange_name, exchange in cls._exchange_service.exchanges.items():
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