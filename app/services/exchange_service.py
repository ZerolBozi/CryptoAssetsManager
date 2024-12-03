import time
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Optional, TypedDict, Union, List

import ccxt.async_support as ccxt

from app.config import settings

class PositionInfo(TypedDict):
    avg_price: float
    error: Optional[str]

class BalanceInfo(TypedDict):
    free: float
    used: float
    total: float
    avg_price: float
    current_price: float
    roi: float
    value_in_usdt: float

class CacheData(TypedDict):
    data: dict
    timestamp: float

class ExchangeService:
    def __init__(self) -> None:
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.price_cache: Dict[str, CacheData] = {}  # 價格緩存
        self.trade_cache: Dict[str, CacheData] = {}  # 交易歷史緩存
        self.price_cache_ttl = 10  # 價格緩存10秒
        self.trade_cache_ttl = 300  # 交易歷史緩存5分鐘

    async def initialize_exchanges(self) -> None:
        """Initialize exchange connections with API configurations."""
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

    async def _fast_ping_exchange(self, exchange: ccxt.Exchange) -> bool:
        """Fast ping method for different exchanges."""
        try:
            await exchange.fetchTime()
            return True
        except Exception as e:
            print(f"Ping failed for {exchange.id}: {str(e)}")
            return False

    async def ping_exchanges(self) -> Dict[str, Union[bool, str]]:
        """Test connectivity to all exchanges with fast methods."""
        if not self.exchanges:
            await self.initialize_exchanges()
        
        async def ping_with_timeout(name: str, exchange: ccxt.Exchange) -> tuple[str, Union[bool, str]]:
            try:
                result = await asyncio.wait_for(
                    self._fast_ping_exchange(exchange),
                    timeout=5
                )
                return name, result
            except asyncio.TimeoutError:
                return name, "Timeout after 5 seconds"
            except Exception as e:
                return name, str(e)

        tasks = [
            ping_with_timeout(name, exchange)
            for name, exchange in self.exchanges.items()
        ]
        results = await asyncio.gather(*tasks)
        
        return dict(results)

    async def _get_cached_price(self, exchange: ccxt.Exchange, symbol: str) -> float:
        """Get cached price or fetch new price if cache expired."""
        try:
            cache_key = f"{exchange.id}_{symbol}"
            now = time.time()
            
            if (cache_key in self.price_cache and 
                now - self.price_cache[cache_key]['timestamp'] < self.price_cache_ttl):
                return self.price_cache[cache_key]['data']
                
            price = await self._get_current_price(exchange, symbol)
            self.price_cache[cache_key] = {
                'data': price,
                'timestamp': now
            }
            return price
        except Exception as e:
            return 0.0

    async def _get_current_price(self, exchange: ccxt.Exchange, symbol: str) -> float:
        """Get current market price for a symbol."""
        try:
            ticker = await exchange.fetch_ticker(symbol)
            return float(ticker['last']) if ticker.get('last') else 0.0
        except Exception:
            return 0.0

    async def _get_cached_trades(self, exchange: ccxt.Exchange, symbol: str) -> List[dict]:
        """Get cached trades or fetch new trades if cache expired."""
        try:
            cache_key = f"{exchange.id}_{symbol}"
            now = time.time()
            
            if (cache_key in self.trade_cache and 
                now - self.trade_cache[cache_key]['timestamp'] < self.trade_cache_ttl):
                return self.trade_cache[cache_key]['data']
                
            if not exchange.has['fetchMyTrades']:
                return []
                
            trades = await exchange.fetch_my_trades(symbol)
            self.trade_cache[cache_key] = {
                'data': trades,
                'timestamp': now
            }
            return trades
        except Exception:
            return []

    async def _get_okx_balance(self, exchange: ccxt.Exchange) -> dict:
        """Get combined trading and funding balance for OKX."""
        trading_balance = await exchange.fetch_balance({'type': 'trading'})
        funding_balance = await exchange.fetch_balance({'type': 'funding'})
        
        balance = {
            'total': {},
            'free': {},
            'used': {}
        }
        
        all_currencies = set(list(trading_balance['total'].keys()) + list(funding_balance['total'].keys()))
        for currency in all_currencies:
            for balance_type in ['total', 'free', 'used']:
                trading_amount = float(trading_balance.get(balance_type, {}).get(currency, 0))
                funding_amount = float(funding_balance.get(balance_type, {}).get(currency, 0))
                balance[balance_type][currency] = trading_amount + funding_amount
        
        return balance

    async def _process_currency(
            self, 
            exchange: ccxt.Exchange, 
            currency: str, 
            balance: dict,
            min_value_threshold: float = 0.1
        ) -> Optional[Dict]:
        """Process single currency balance and related data."""
        try:
            # 跳過 USDT 的處理
            if currency == 'USDT':
                total_amount = float(balance['total'][currency])
                if total_amount <= 0:
                    return None
                    
                return {
                    'free': float(balance['free'][currency]),
                    'used': float(balance['used'][currency]),
                    'total': total_amount,
                    'avg_price': 1.0,
                    'current_price': 1.0,
                    'roi': 0.0,
                    'value_in_usdt': total_amount,
                    'profit_usdt': 0.0
                }

            if float(balance['total'][currency]) <= 0:
                return None

            symbol = f"{currency}/USDT"
            
            # 檢查交易對是否存在
            try:
                if not exchange.has['fetchTicker']:
                    return None
                    
                markets = await exchange.load_markets()
                if symbol not in markets:
                    return None
            except Exception as e:
                print(f"Error checking market {symbol} on {exchange.id}: {str(e)}")
                return None

            # 並行獲取價格和交易歷史
            price_task = self._get_cached_price(exchange, symbol)
            trades_task = self._get_cached_trades(exchange, symbol)
            
            current_price, trades = await asyncio.gather(price_task, trades_task)
            
            if not current_price:
                return None
                
            amount = float(balance['total'][currency])
            value_in_usdt = amount * current_price
            
            if value_in_usdt < min_value_threshold:
                return None
                
            # 計算平均價格
            if trades:
                total_cost = sum(trade['cost'] for trade in trades)
                total_amount = sum(trade['amount'] for trade in trades)
                avg_price = float(Decimal(str(total_cost)) / Decimal(str(total_amount))) if total_amount else current_price
            else:
                avg_price = current_price  # 如果沒有交易歷史，使用當前價格
                
            roi = ((current_price - avg_price) / avg_price * 100) if avg_price else 0
            
            # 計算收益（USDT）
            profit_usdt = (current_price - avg_price) * amount
            
            return {
                'free': float(balance['free'][currency]),
                'used': float(balance['used'][currency]),
                'total': amount,
                'avg_price': avg_price,
                'current_price': current_price,
                'roi': roi,
                'value_in_usdt': value_in_usdt,
                'profit_usdt': profit_usdt  # 添加 USDT 收益
            }
        except Exception as e:
            print(f"Error processing {currency} on {exchange.id}: {str(e)}")
            return None
        
    async def get_spot_balance(
            self, 
            exchange: ccxt.Exchange,
            min_value_threshold: float = 0.1
        ) -> Dict[str, Union[BalanceInfo, str]]:
        """Get spot balance with optimized parallel processing."""
        try:
            if exchange.id == 'okx':
                balance = await self._get_okx_balance(exchange)
            else:
                balance = await exchange.fetch_balance()
            
            # 並行處理所有幣種
            tasks = [
                self._process_currency(exchange, currency, balance, min_value_threshold)
                for currency in balance['total'].keys()
            ]
            
            results = await asyncio.gather(*tasks)
            
            # 過濾掉 None 值並組織結果
            return {
                currency: result 
                for currency, result in zip(balance['total'].keys(), results) 
                if result is not None
            }
            
        except Exception as e:
            return {'error': str(e)}

    async def get_all_spot_assets(
            self,
            min_value_threshold: float = 0.1
        ) -> Dict[str, Dict[str, Union[BalanceInfo, str]]]:
        """Get spot assets from all exchanges in parallel."""
        if not self.exchanges:
            await self.initialize_exchanges()

        async def process_exchange(name: str, exchange: ccxt.Exchange) -> tuple[str, dict]:
            try:
                balance = await self.get_spot_balance(exchange, min_value_threshold)
                return name, balance
            except Exception as e:
                return name, {'error': str(e)}
            finally:
                await exchange.close()

        # 並行處理所有交易所
        tasks = [
            process_exchange(name, exchange)
            for name, exchange in self.exchanges.items()
        ]
        
        results = await asyncio.gather(*tasks)
        return dict(results)