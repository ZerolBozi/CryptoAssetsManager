import re
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, Union

import ccxt.async_support as ccxt

from app.config import settings


@dataclass
class ExchangeCredentials:
    api_key: str
    secret: str
    password: Optional[str] = None
    
    def to_dict(self) -> dict:
        creds = {
            "apiKey": self.api_key,
            "secret": self.secret
        }
        if self.password:
            creds["password"] = self.password
        return creds
    
class ExchangeRegistry:
    def __init__(self):
        self._available_exchanges = self.__get_ccxt_exchanges()
        
    def __get_ccxt_exchanges(self) -> Dict[str, type]:
        return {
            name: getattr(ccxt, name)
            for name in dir(ccxt)
            if (
                isinstance(getattr(ccxt, name), type) 
                and issubclass(getattr(ccxt, name), ccxt.Exchange)
                and name != 'Exchange'
            )
        }
    
    def __detect_exchanges_from_settings(self) -> Dict[str, ExchangeCredentials]:
        exchanges = {}
        settings_dict = settings.model_dump()
        
        exchange_settings = {}
        for key, value in settings_dict.items():
            match = re.match(r'([A-Z]+)_(API_KEY|SECRET|PASSWORD)$', key)
            if match and value:
                exchange_name = match.group(1).lower()
                setting_type = match.group(2)
                
                if exchange_name not in exchange_settings:
                    exchange_settings[exchange_name] = {}
                exchange_settings[exchange_name][setting_type] = value
        
        for exchange_name, config in exchange_settings.items():
            if 'API_KEY' in config and 'SECRET' in config:
                exchanges[exchange_name] = ExchangeCredentials(
                    api_key=config['API_KEY'],
                    secret=config['SECRET'],
                    password=config.get('PASSWORD')
                )
        
        return exchanges

    def create_exchange_instance(self, exchange_name: str, credentials: ExchangeCredentials) -> Optional[ccxt.Exchange]:
        try:
            exchange_class = None
            if hasattr(ccxt, exchange_name):
                exchange_class = getattr(ccxt, exchange_name)
                
            if not exchange_class:
                print(f"Exchange {exchange_name} not found in CCXT")
                return None

            config = {
                **credentials.to_dict(),
                "enableRateLimit": settings.ENABLE_RATE_LIMIT,
                "timeout": settings.API_CONNECT_TIMEOUT
            }
            return exchange_class(config)
            
        except Exception as e:
            print(f"Error creating {exchange_name} instance: {str(e)}")
            return None

    def create_exchange_instances(self) -> Dict[str, ccxt.Exchange]:
        exchanges = {}
        detected_exchanges = self.__detect_exchanges_from_settings()
        
        for exchange_name, credentials in detected_exchanges.items():
            exchange = self.create_exchange_instance(exchange_name, credentials)
            if exchange:
                exchanges[exchange_name] = exchange
        
        return exchanges

class BaseExchange:
    def __init__(self) -> None:
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.registry = ExchangeRegistry()

    async def initialize_exchanges_by_server(self) -> None:
        self.exchanges = self.registry.create_exchange_instances()

    async def initialize_exchanges(self, apis: Dict[str, Dict[str, str]]) -> None:
        current_exchanges = {
            name: instance
            for name, instance in self.exchanges.items()
            if name not in apis.get("exchanges", {})
        }

        self.exchanges = current_exchanges

        for exchange_name, config in apis.get("exchanges", {}).items():
            if not all(config.get(key) for key in ["api_key", "secret"]):
                continue
                
            credentials = ExchangeCredentials(
                api_key=config["api_key"],
                secret=config["secret"],
                password=config.get("password")
            )
            
            exchange = self.registry.create_exchange_instance(exchange_name, credentials)
            if exchange:
                self.exchanges[exchange_name] = exchange

    async def __ping_exchange(self, exchange: ccxt.Exchange) -> bool:
        """
        Ping an exchange to check connection status.
        """
        try:
            # API檢查的部分會很久, 底下這幾種都是檢查的方式, 但是速度很慢, 跟交易所的伺服器有關
            # 測試下來其實不管用什麼方法速度都差不多, 沒有特別快的辦法了
            # await exchange.fetch_deposit_withdraw_fees("BTC")
            await exchange.fetch_balance()
            return True
        except Exception as e:
            print(e)
            return False

    async def ping_exchanges(self) -> Optional[Dict[str, Union[bool, str]]]:
        """
        Ping all exchanges to check connection status.
        """
        if not self.exchanges:
            return None

        try:
            results = await asyncio.gather(
                *[
                    self.__ping_exchange(exchange)
                    for exchange in self.exchanges.values()
                ]
            )
            return {
                name: result for name, result in zip(self.exchanges.keys(), results)
            }
        except Exception as e:
            print(e)
            return None
