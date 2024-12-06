import time
import asyncio
from decimal import Decimal
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import ccxt.async_support as ccxt

from app.config import settings

@dataclass
class CacheData:
    data: Union[Decimal, Dict]
    timestamp: float

@dataclass
class Balance:
    free: Decimal
    used: Decimal
    total: Decimal
    avg_price: Decimal
    current_price: Decimal
    roi: Decimal
    value_in_usdt: Decimal
    profit_usdt: Decimal

class ExchangeService:
    def __init__(self, price_cache_ttl: int = 60, trade_cache_ttl: int = 600) -> None:
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.price_cache: Dict[str, CacheData] = {}
        self.trade_cache: Dict[str, CacheData] = {}
        self.price_cache_ttl = price_cache_ttl
        self.trade_cache_ttl = trade_cache_ttl

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
            cache_key = f"{exchange.id}_{symbol}"
            now = time.time()

            if (cache_key in self.price_cache and 
                now - self.price_cache[cache_key].timestamp < self.price_cache_ttl):
                return self.price_cache[cache_key].data
            
            ticker = await exchange.fetch_ticker(symbol)
            price = Decimal(ticker.get('last', Decimal(0)))
            self.price_cache[cache_key] = CacheData(price, time.time())
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
            cache_key = f"{exchange.id}_{symbol}"
            now = time.time()

            if (cache_key in self.trade_cache and 
                now - self.trade_cache[cache_key].timestamp < self.trade_cache_ttl):
                return self.trade_cache[cache_key].data
            
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

            self.trade_cache[cache_key] = CacheData(trades, time.time())
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
    
    async def __process_symbol(self, exchange: ccxt.Exchange, symbol: str, balance: dict) -> Optional[Balance]:
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
                    profit_usdt=Decimal('0')
                )
            
            _symbol = f"{symbol}/USDT"

            if not exchange.has['fetchTicker']:
                return None
            
            price_task = self.get_current_price(exchange, _symbol)
            trades_task = self.get_trades(exchange, _symbol)

            current_price, trades = await asyncio.gather(price_task, trades_task)

            if not current_price:
                return None
            
            value_in_usdt: Decimal = total_amount * current_price
                    
            if trades:
                cost = sum([Decimal(str(trade['cost'])) for trade in trades])
                amount = sum([Decimal(str(trade['amount'])) for trade in trades])
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
                profit_usdt=profit_usdt
            )
            
        except Exception as e:
            return None
    
    async def get_spot_balance(self, exchange: ccxt.Exchange) -> Dict[str, Union[Balance, str]]:
        """
        Get spot balance for an exchange.

        Args:
            exchange: ccxt Exchange instance
        
        Returns:
            Dict: Spot balance data
        """
        try:
            if exchange.id == 'okx':
                balance = await self.__get_okx_balance(exchange)
            else:
                balance = await exchange.fetch_balance()

            tasks = [
                self.__process_symbol(exchange, symbol, balance)
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
        
    async def get_spot_assets(self, min_value: Decimal = Decimal('0.1')) -> Dict[str, Union[Balance, str]]:
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
            (name, self.get_spot_balance(exchange))
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