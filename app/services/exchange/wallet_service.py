import asyncio
from decimal import Decimal
from typing import Dict, Optional, Union

import ccxt.async_support as ccxt

from app.database.asset import AssetDB
from app.database.asset_cost import AssetCostDB
from app.database.asset_history import AssetHistoryDB
from app.structures.asset_structure import Asset, AssetSummary
from app.services.exchange.base_exchange import BaseExchange
from app.services.exchange.quote_service import QuoteService
from app.services.exchange.trading_service import TradingService


class WalletService(BaseExchange):
    def __init__(
            self, 
            quote_service: QuoteService, 
            trading_service: TradingService,
            asset_db: AssetDB,
            asset_cost_db: AssetCostDB,
            asset_history_db: AssetHistoryDB
        ) -> None:
        super().__init__()
        self.quote_service = quote_service
        self.trading_service = trading_service
        self.asset_db = asset_db
        self.asset_cost_db = asset_cost_db
        self.asset_history_db = asset_history_db

    async def __process_symbol(
        self, 
        exchange: ccxt.Exchange, 
        symbol: str, 
        balance: dict, 
        timestamp: int = None
    ) -> Optional[Asset]:
        try:
            total_amount = Decimal(str(balance["total"][symbol]))

            if total_amount <= Decimal("0"):
                return None

            asset: Optional[Asset] = None

            if symbol in ["USDT", "USDC"]:
                asset = Asset.calculate_metrics(
                    exchange=exchange.id,
                    symbol=symbol,
                    free=Decimal(balance["free"][symbol]),
                    used=Decimal(balance["used"][symbol]),
                    total=total_amount,
                    avg_price=Decimal("1"),
                    current_price=Decimal("1")
                )

            else:
                _symbol = f"{symbol}/USDT"
                asset_cost = await self.asset_cost_db.get_asset_cost(
                    exchange=exchange.id,
                    symbol=symbol
                )
                
                if timestamp is None:
                    current_price = await self.quote_service.get_current_price_decimal(exchange, _symbol)
                else:
                    current_price = await self.quote_service.get_last_close_price_from_history(
                        exchange, _symbol, "1d", timestamp, timestamp
                    )

                if asset_cost is not None:
                    avg_price = Decimal(str(asset_cost["avg_price"]))
                else:
                    trades = await self.trading_service.get_trade_history(exchange, _symbol)

                    if trades:
                        cost = Decimal("0")
                        amount = Decimal("0")
                        for trade in trades:
                            if trade["side"] == "buy":
                                cost += Decimal(str(trade["cost"]))
                                amount += Decimal(str(trade["amount"]))
                            else:
                                cost -= Decimal(str(trade["cost"]))
                                amount -= Decimal(str(trade["amount"]))
                        avg_price = cost / amount if amount else current_price
                    else:
                        avg_price = current_price

                    await self.asset_cost_db.update_asset_cost(
                        exchange=exchange.id,
                        symbol=symbol,
                        avg_price=avg_price,
                        update_by="Server"
                    )

                asset = Asset.calculate_metrics(
                    exchange=exchange.id,
                    symbol=symbol,
                    free=Decimal(balance["free"][symbol]),
                    used=Decimal(balance["used"][symbol]),
                    total=total_amount,
                    avg_price=avg_price,
                    current_price=current_price
                )

            if asset:
                await self.asset_db.update_asset(
                    exchange=exchange.id,
                    symbol=symbol,
                    data=asset.model_dump_for_db()
                )

            return asset
        except Exception as e:
            print(e)
            return None

    async def __get_okx_balance(self, exchange: ccxt.Exchange) -> dict:
        trading_balance = await exchange.fetch_balance({"type": "trading"})
        funding_balance = await exchange.fetch_balance({"type": "funding"})

        balance = {"total": {}, "free": {}, "used": {}}

        all_cryptos = set(list(trading_balance.keys()) + list(funding_balance.keys()))
        for crypto in all_cryptos:
            for balance_type in ["total", "free", "used"]:
                trading_amount = float(
                    trading_balance.get(balance_type, {}).get(crypto, 0)
                )
                funding_amount = float(
                    funding_balance.get(balance_type, {}).get(crypto, 0)
                )
                balance[balance_type][crypto] = trading_amount + funding_amount

        return balance

    async def get_balance(
        self, exchange: ccxt.Exchange, timestamp: int = None
    ) -> Dict[str, Union[Asset, str]]:
        """
        Get spot balance from an exchange.

        Args:
            exchange: ccxt Exchange instance
            timestamp: Timestamp (milliseconds)

        Returns:
            Dict: Spot balance data
        """
        try:
            if exchange.id == "okx":
                balance = await self.__get_okx_balance(exchange)
            else:
                balance = await exchange.fetch_balance()

            tasks = [
                self.__process_symbol(exchange, symbol, balance, timestamp)
                for symbol in balance["total"].keys()
            ]

            results = await asyncio.gather(*tasks)

            return {
                symbol: result
                for symbol, result in zip(balance["total"].keys(), results)
                if result is not None
            }

        except Exception as e:
            return {"error": str(e)}

    async def get_assets(
        self, min_value: Decimal = Decimal("1"), timestamp: int = None
    ) -> Dict[str, Union[Dict[str, Asset], AssetSummary]]:
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

            total = Decimal("0")
            profit = Decimal("0")
            initial = Decimal("0")


            for exchange_name, result in zip([t[0] for t in tasks], results):
                if "error" in result:
                    continue

                filtered_result = {}

                for symbol, balance in result.items():
                    if (balance.value_in_usdt >= min_value) or (symbol in ["USDT", "USDC"]):
                        filtered_result[symbol] = balance.model_dump()
                    total += balance.value_in_usdt
                    profit += balance.profit_usdt
                    initial += balance.total * balance.avg_price

                exchanges_data[exchange_name] = filtered_result

            summary = AssetSummary.calculate_summary(
                total=total,
                profit=profit,
                initial=initial
            )

            await self.asset_history_db.update_history(summary.model_dump_for_db())

            return {
                "exchanges": exchanges_data,
                "summary": summary.model_dump(),
            }

        except Exception as e:
            return {"error": str(e)}
