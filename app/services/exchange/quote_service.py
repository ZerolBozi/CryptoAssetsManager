import asyncio
from decimal import Decimal
from typing import Dict, Union, List

import ccxt.async_support as ccxt

from app.services.exchange.base_exchange import BaseExchange


class QuoteService(BaseExchange):
    def __init__(self):
        super().__init__()

    def __process_symbol(self, symbol: str, exchange_name: str) -> str:
        if exchange_name in ['okx', 'bitopro']:
            symbol = symbol.replace('USDT', '/USDT')
            symbol = symbol.replace('USDC', '/USDC')
            return symbol
        return symbol

    async def get_price_history(
        self, exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, end: int
    ) -> Dict[str, Union[str, list]]:
        """
        Get price history for a symbol from an exchange.

        Args:
            exchange: ccxt Exchange instance
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            timeframe: Timeframe (e.g. '1d')
            since: Start timestamp (milliseconds)
            end: End timestamp (milliseconds)

        Returns:
            Dict: Price history data (the data including end timestamp)
            {
                "data": [
                    {
                        "timestamp": 1733529600000,
                        "open": 99740.84,
                        "high": 100428.0,
                        "low": 98844.0,
                        "close": 99468.52,
                        "volume": 8793.1234
                    }
                ]
            }
        """
        timeframe_map = {
            "1m": 60000,
            "5m": 300000,
            "15m": 900000,
            "30m": 1800000,
            "1h": 3600000,
            "4h": 14400000,
            "1d": 86400000,
            "1w": 604800000,
        }

        try:
            symbol = self.__process_symbol(symbol, exchange.id)
            adjusted_end = end + timeframe_map[timeframe]
            periods = (adjusted_end - since) // timeframe_map[timeframe]
            chunks = [(periods // 1000) + (1 if periods % 1000 else 0)]
            result = []

            for i in range(chunks[0]):
                current_since = since + (i * 1000 * timeframe_map[timeframe])
                limit = min(1000, periods - (i * 1000))

                ohlcv = await exchange.fetch_ohlcv(
                    symbol, timeframe, current_since, limit=limit
                )

                if not ohlcv:
                    break

                result.extend(
                    [
                        {
                            "timestamp": candle[0],
                            "open": candle[1],
                            "high": candle[2],
                            "low": candle[3],
                            "close": candle[4],
                            "volume": candle[5],
                        }
                        for candle in ohlcv
                    ]
                )

            return {"data": result}

        except Exception as e:
            return {"error": str(e)}
        
    async def get_close_price_from_history(
        self, exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, end: int
    ) -> Dict[int, Decimal]:
        
        try:
            price_history = await self.get_price_history(
                exchange, symbol, timeframe, since, end
            )
            if "error" in price_history:
                return {}

            return {candle["timestamp"]: Decimal(str(candle["close"])) for candle in price_history["data"]}
        except Exception as e:
            print(e)
            return {}

    async def get_last_close_price_from_history(
        self, exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, end: int
    ) -> Decimal:
        """
        Get the last close price for a symbol from price history.

        Args:
            exchange: ccxt Exchange instance
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            timeframe: Timeframe (e.g. '1d')
            since: Start timestamp (milliseconds)
            end: End timestamp (milliseconds)

        Returns:
            Decimal: Last close price
        """
        try:
            price_history = await self.get_price_history(
                exchange, symbol, timeframe, since, end
            )
            if "error" in price_history:
                return Decimal(0)

            return Decimal(str(price_history["data"][-1]["close"]))
        except Exception as e:
            print(e)
            return Decimal(0)

    async def get_current_price(self, exchange: ccxt.Exchange, symbol: str) -> Decimal:
        """
        Get the current price for a symbol from an exchange.

        Args:
            exchange: ccxt Exchange instance
            symbol: Trading pair symbol (e.g. 'BTC/USDT')

        Returns:
            Decimal: Current price
        """
        try:
            ticker = await exchange.fetch_ticker(symbol)
            price = Decimal(ticker.get("last", Decimal(0)))
            return price
        except Exception as e:
            return Decimal(0)

    async def get_current_prices(
        self, exchange: ccxt.Exchange, symbols: List[str]
    ) -> Dict[str, Decimal]:
        """
        Get the current price for symbols from an exchange

        Args:
            exchange: ccxt Exchange instance
            symbols: Trading pair symbol (e.g. ['BTC/USDT', 'ETH/USDT'])

        Returns:
            Dict: Current prices
        """
        try:
            tickers = await exchange.fetch_tickers(symbols)
            prices = {k: Decimal(str(v.get("last", "0"))) for k, v in tickers.items()}
            return prices
        except Exception as e:
            return Decimal(0)
