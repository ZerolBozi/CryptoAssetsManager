import asyncio
from typing import Dict, Optional, Union

import ccxt.async_support as ccxt

from app.config import settings


class BaseExchange:
    def __init__(self) -> None:
        self.exchanges: Dict[str, ccxt.Exchange] = {}

    async def initialize_exchanges(self, apis: Dict[str, Dict[str, str]]) -> None:
        """
        apis: Dict[str, Dict[str, str]]
        {
            "exchanges": {
                "binance": {
                    "api_key": "your_api_key",
                    "secret": "your_secret"
                },
                "okx": {
                    "api_key": "your_api_key",
                    "secret": "your_secret",
                    "password": "your_password"
                },
                "mexc": {
                    "api_key": "your_api_key",
                    "secret": "your_secret"
                },
                "gateio": {
                    "api_key": "your_api_key",
                    "secret": "your_secret"
                }
            }
        }
        """
        exchange_classes = {
            "binance": ccxt.binance,
            "okx": ccxt.okx,
            "bybit": ccxt.bybit,
            "bitget": ccxt.bitget,
            "mexc": ccxt.mexc,
            "gateio": ccxt.gateio,
            "bitopro": ccxt.bitopro
        }

        default_config = {
            "enableRateLimit": settings.ENABLE_RATE_LIMIT,
            "timeout": settings.API_CONNECT_TIMEOUT,
        }

        # reset
        self.exchanges = {}

        for exchange_name, exchange_config in apis["exchanges"].items():
            exchange_class = exchange_classes.get(exchange_name)
            if not exchange_class:
                continue

            config = {**exchange_config, **default_config}
            self.exchanges[exchange_name] = exchange_class(config)

    async def initialize_exchanges_by_server(self) -> None:
        exchange_configs = {
            "binance": (
                ccxt.binance,
                {
                    "apiKey": settings.BINANCE_API_KEY,
                    "secret": settings.BINANCE_SECRET,
                },
            ),
            "okx": (
                ccxt.okx,
                {
                    "apiKey": settings.OKX_API_KEY,
                    "secret": settings.OKX_SECRET,
                    "password": settings.OKX_PASSWORD,
                },
            ),
            "bybit": (
                ccxt.bybit,
                {
                    "apiKey": settings.BYBIT_API_KEY,
                    "secret": settings.BYBIT_SECRET,
                }
            ),
            "bitget": (
                ccxt.bitget,
                {
                    "apiKey": settings.BITGET_API_KEY,
                    "secret": settings.BITGET_SECRET,
                    "password": settings.BITGET_PASSWORD,
                }
            ),
            "mexc": (
                ccxt.mexc,
                {
                    "apiKey": settings.MEXC_API_KEY,
                    "secret": settings.MEXC_SECRET,
                },
            ),
            "gateio": (
                ccxt.gateio,
                {
                    "apiKey": settings.GATEIO_API_KEY,
                    "secret": settings.GATEIO_SECRET,
                },
            ),
            "bitopro": (
                ccxt.bitopro,
                {
                    "apiKey": settings.BITOPRO_API_KEY,
                    "secret": settings.BITOPRO_SECRET,
                }
            )
        }

        default_config = {
            "enableRateLimit": settings.ENABLE_RATE_LIMIT,
            "timeout": settings.API_CONNECT_TIMEOUT,
        }

        self.exchanges = {
            name: exchange_class({**config, **default_config})
            for name, (exchange_class, config) in exchange_configs.items()
        }

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
