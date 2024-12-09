import asyncio
from decimal import Decimal
from typing import Dict, Optional, Union

import ccxt.async_support as ccxt

from app.structures.asset_structure import Balance, AssetsData
from app.services.exchange.base_exchange import BaseExchange
from app.services.exchange.quote_service import QuoteService
from app.services.exchange.trading_service import TradingService

class WalletService(BaseExchange):
    def __init__(self, quote_service: QuoteService, trading_service: TradingService):
        super().__init__()
        self.quote_service = quote_service
        self.trading_service = trading_service

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
                price_task = self.quote_service.get_current_price(exchange, _symbol)
            else:
                price_task = self.quote_service.get_last_close_price_from_history(exchange, _symbol, '1d', timestamp, timestamp)

            trades_task = self.trading_service.get_trade_history(exchange, _symbol)

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

    async def get_balance(self, exchange: ccxt.Exchange, timestamp: int = None) -> Dict[str, Union[Balance, str]]:
        """
        Get spot balance from an exchange.

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
        
    async def get_assets(self, min_value: Decimal = Decimal('1'), timestamp: int = None) -> AssetsData:
        """
        Get assets data from all exchanges.

        Args:
            min_value: Minimum value threshold in USDT
            timestamp: Timestamp (milliseconds)

        Returns:
            AssetsData: Assets data with exchanges and summary information
        """
        try:
            if not self.exchanges:
                return {}

            tasks = [
                (name, self.get_balance(exchange, timestamp))
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
                    if (balance.value_in_usdt >= min_value) or (symbol == 'USDT'):
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

        except Exception as e:
            return {"error": str(e)}
        
       