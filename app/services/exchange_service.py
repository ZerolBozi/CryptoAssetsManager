import asyncio
from decimal import Decimal
from typing import Dict, List, Optional, Union

import ccxt.async_support as ccxt

from app.config import settings
from app.services.asset_structure import Balance, AssetsData

class ExchangeService:
    def __init__(self) -> None:
        self.exchanges: Dict[str, ccxt.Exchange] = {}

    async def initialize_exchanges(self, apis: dict) -> None:
        """
        apis: dict
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
            'binance': ccxt.binance,
            'okx': ccxt.okx,
            'mexc': ccxt.mexc,
            'gateio': ccxt.gateio
        }

        default_config = {
            'enableRateLimit': settings.ENABLE_RATE_LIMIT,
            'timeout': settings.API_CONNECT_TIMEOUT
        }

        # reset
        self.exchanges = {}

        for exchange_name, exchange_config in apis['exchanges'].items():
            exchange_class = exchange_classes.get(exchange_name)
            if not exchange_class:
                continue

            config = {**exchange_config, **default_config}
            self.exchanges[exchange_name] = exchange_class(config)

    async def initialize_exchanges_by_server(self) -> None:
        """
        Initialize exchange connections.
        """
        exchange_configs = {
            'binance': (ccxt.binance, {
                'apiKey': settings.BINANCE_API_KEY,
                'secret': settings.BINANCE_SECRET,
            }),
            'okx': (ccxt.okx, {
                'apiKey': settings.OKX_API_KEY,
                'secret': settings.OKX_SECRET,
                'password': settings.OKX_PASSWORD,
            }),
            'mexc': (ccxt.mexc, {
                'apiKey': settings.MEXC_API_KEY,
                'secret': settings.MEXC_SECRET,
            }),
            'gateio': (ccxt.gateio, {
                'apiKey': settings.GATEIO_API_KEY,
                'secret': settings.GATEIO_SECRET,
            })
        }

        default_config = {
            'enableRateLimit': settings.ENABLE_RATE_LIMIT,
            'timeout': settings.API_CONNECT_TIMEOUT
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
            await exchange.fetch_balance()
            return True
        except Exception as e:
            return False

    async def ping_exchanges(self) -> Optional[Dict[str, Union[bool, str]]]:
        """
        Ping all exchanges to check connection status.
        """
        if not self.exchanges:
            return None
        
        try:
            results = await asyncio.gather(
                *[self.__ping_exchange(exchange) for exchange in self.exchanges.values()]
            )
            return {name: result for name, result in zip(self.exchanges.keys(), results)}
        except Exception as e:
            return None
        
    async def get_price_history(self, exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, end: int) -> Dict:
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
        """
        timeframe_map = {
            '1m': 60000,
            '5m': 300000,
            '15m': 900000,
            '30m': 1800000,
            '1h': 3600000,
            '4h': 14400000,
            '1d': 86400000,
            '1w': 604800000
        }

        try:
            adjusted_end = end + timeframe_map[timeframe]
            periods = (adjusted_end - since) // timeframe_map[timeframe]
            chunks = [(periods // 1000) + (1 if periods % 1000 else 0)]  
            result = []

            for i in range(chunks[0]):
                current_since = since + (i * 1000 * timeframe_map[timeframe])
                limit = min(1000, periods - (i * 1000))
                
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, current_since, limit=limit)
                
                if not ohlcv:
                    break
                    
                result.extend([{
                    "timestamp": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5]
                } for candle in ohlcv])

            return {"data": result}
            
        except Exception as e:
            return {"error": str(e)}
        
    async def __get_close_price_history(self, exchange: ccxt.Exchange, symbol: str, timeframe: str, since: int, end: int) -> Decimal:
        try:
            price_history = await self.get_price_history(exchange, symbol, timeframe, since, end)
            if 'error' in price_history:
                return Decimal(0)

            return Decimal(price_history['data'][-1]['close'])
        except Exception as e:
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
            price = Decimal(ticker.get('last', Decimal(0)))
            return price
        except Exception as e:
            return Decimal(0)

    async def get_trades(self, exchange: ccxt.Exchange, symbol: str) -> List[Dict]:
        """
        Get recent trades for a symbol from an exchange.

        Args:
            exchange: ccxt Exchange instance
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
        
        Returns:
            List[Dict]: List of trade data
        """
        try:           
            if not exchange.has['fetchMyTrades']:
                return []
            
            symbol_alternatives = {
                "RENDER/USDT": "RNDR/USDT",
                "FET/USDT": "OCEAN/USDT", 
                "OCEAN/USDT": "AGIX/USDT"
            }
            
            trades = await exchange.fetch_my_trades(symbol)
            if (not trades) and (symbol in symbol_alternatives):
                trades = await exchange.fetch_my_trades(symbol_alternatives[symbol])

            return trades
                
        except Exception as e:
            return []
        
    async def __get_okx_balance(self, exchange:ccxt.Exchange) -> dict:
        trading_balance = await exchange.fetch_balance({'type': 'trading'})
        funding_balance = await exchange.fetch_balance({'type': 'funding'})

        balance = {
            'total': {},
            'free': {},
            'used': {}
        }

        all_cryptos = set(list(trading_balance.keys()) + list(funding_balance.keys()))
        for crypto in all_cryptos:
            for balance_type in ['total', 'free', 'used']:
                trading_amount = float(trading_balance.get(balance_type, {}).get(crypto, 0))
                funding_amount = float(funding_balance.get(balance_type, {}).get(crypto, 0))
                balance[balance_type][crypto] = trading_amount + funding_amount
        
        return balance
    
    async def __process_symbol(self, exchange: ccxt.Exchange, symbol: str, balance: dict, timestamp: int = None) -> Optional[Balance]:
        try:
            total_amount = Decimal(str(balance['total'][symbol]))

            if total_amount <= Decimal('0'):
                return None

            if symbol == "USDT":
                return Balance(
                    free=Decimal(balance['free'][symbol]),
                    used=Decimal(balance['used'][symbol]),
                    total=total_amount,
                    avg_price=Decimal('1'),
                    current_price=Decimal('1'),
                    roi=Decimal('0'),
                    value_in_usdt=total_amount,
                    profit_usdt=Decimal('0'),
                )
            
            _symbol = f"{symbol}/USDT"

            if not exchange.has['fetchTicker']:
                return None
            
            if timestamp is None:
                price_task = self.get_current_price(exchange, _symbol)
            else:
                price_task = self.__get_close_price_history(exchange, _symbol, '1d', timestamp, timestamp)

            trades_task = self.get_trades(exchange, _symbol)

            current_price, trades = await asyncio.gather(price_task, trades_task)

            if (not current_price) or (not trades):
                return None
            
            value_in_usdt: Decimal = total_amount * current_price
            cost = Decimal('0')
            amount = Decimal('0')
            avg_price = Decimal('0')

            if trades:
                for trade in trades:
                    if trade['side'] == "buy":
                        cost += Decimal(str(trade['cost']))
                        amount += Decimal(str(trade['amount']))
                    else:
                        cost -= Decimal(str(trade['cost']))
                        amount -= Decimal(str(trade['amount']))

                avg_price = cost / amount if amount else current_price
            else:
                avg_price = current_price

            roi = (((current_price - avg_price) / avg_price) * Decimal('100')) if avg_price else Decimal('0')
            
            profit_usdt = (current_price - avg_price) * total_amount

            return Balance(
                free=Decimal(balance['free'][symbol]),
                used=Decimal(balance['used'][symbol]),
                total=total_amount,
                avg_price=avg_price,
                current_price=current_price,
                roi=roi,
                value_in_usdt=value_in_usdt,
                profit_usdt=profit_usdt,
            )
            
        except Exception as e:
            return None
    
    async def get_spot_balance(self, exchange: ccxt.Exchange, timestamp: int = None) -> Dict[str, Union[Balance, str]]:
        """
        Get spot balance for an exchange.

        Args:
            exchange: ccxt Exchange instance
            timestamp: Timestamp (milliseconds)

        Returns:
            Dict: Spot balance data
        """
        try:
            if exchange.id == 'okx':
                balance = await self.__get_okx_balance(exchange)
            else:
                balance = await exchange.fetch_balance()

            tasks = [
                self.__process_symbol(exchange, symbol, balance, timestamp)
                for symbol in balance['total'].keys()
            ]
            
            results = await asyncio.gather(*tasks)

            return {
                symbol: result 
                for symbol, result in zip(balance['total'].keys(), results) 
                if result is not None
            }
        
        except Exception as e:
            return {"error": str(e)}
        
    async def get_spot_assets(self, min_value: Decimal = Decimal('0.1'), timestamp: int = None) -> AssetsData:
        """
        Get spot assets from all exchanges.

        Args:
            min_value: Minimum value threshold in USDT
        
        Returns:
            Dict: Spot assets data
        """
        if not self.exchanges:
            return {}

        tasks = [
            (name, self.get_spot_balance(exchange, timestamp))
            for name, exchange in self.exchanges.items()
        ]

        results = await asyncio.gather(*(task[1] for task in tasks))
        exchanges_data = {}

        assets_summary = {
            'total': Decimal('0'),
            'profit': Decimal('0'),
            'initial': Decimal('0'),
            'roi': Decimal('0')
        }

        for exchange_name, result in zip([t[0] for t in tasks], results):
            if 'error' in result:
                continue

            filtered_result = {}

            for symbol, balance in result.items():
                if (balance.value_in_usdt >= min_value) and (symbol != 'USDT'):
                    filtered_result[symbol] = balance
                assets_summary['total'] += balance.value_in_usdt
                assets_summary['profit'] += balance.profit_usdt
                assets_summary['initial'] += balance.total * balance.avg_price

            exchanges_data[exchange_name] = filtered_result

        assets_summary['roi'] = ((assets_summary['profit'] / assets_summary['initial']) * Decimal('100')) if assets_summary['initial'] else Decimal('0')

        return {
            'exchanges': exchanges_data,
            'summary': assets_summary,
        }