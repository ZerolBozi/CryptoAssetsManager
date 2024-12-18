import asyncio
from decimal import Decimal
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

from app.database.asset import AssetDB
from app.database.asset_history import AssetHistoryDB
from app.services.exchange.wallet_service import WalletService
from app.structures.asset_structure import AssetSummary


class AssetHistoryService:
    def __init__(
        self,
        wallet_service: WalletService,
        asset_db: AssetDB,
        asset_history_db: AssetHistoryDB,
    ) -> None:
        self.wallet_service = wallet_service
        self.quote_service = wallet_service.quote_service
        self.asset_db = asset_db
        self.asset_history_db = asset_history_db

    def __convert_to_daily_timestamp(self, timestamp: int) -> int:
        return (timestamp // 86400000) * 86400000
    
    async def get_current_assets(self, min_value: Decimal = Decimal("1")) -> Optional[Dict]:
        recent_asset = await self.asset_db.get_asset_by_time_diff(3600000)

        if recent_asset:
            assets = await self.asset_db.get_all_assets()
            if assets:
                exchanges_data = {}
                total = Decimal("0")
                profit = Decimal("0")
                initial = Decimal("0")

                for asset in assets:
                    if Decimal(asset["value_in_usdt"]) < min_value:
                        continue
                    exchange = asset["exchange"]
                    if exchange not in exchanges_data:
                        exchanges_data[exchange] = {}
                    exchanges_data[exchange][asset["symbol"]] = asset
                    
                    total += Decimal(asset["value_in_usdt"])
                    profit += Decimal(asset["profit_usdt"])
                    initial += Decimal(asset["total"]) * Decimal(asset["avg_price"])

                summary = AssetSummary.calculate_summary(
                    total=total,
                    profit=profit,
                    initial=initial
                )

                return {
                    "exchanges": exchanges_data,
                    "summary": summary.model_dump()
                }

        return await self.wallet_service.get_assets(min_value)

    async def get_asset_history(self, period: int) -> List[Dict]:
        """
        Get asset history for specified time period, filling gaps with historical price data if needed.

        Args:
            period: Time period for history (30, 90, 180, 365)

        Returns:
            List[AssetSnapshot]: List of snapshots for the period
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=period)

        end_timestamp = self.__convert_to_daily_timestamp(int(end_time.timestamp() * 1000))
        start_timestamp = self.__convert_to_daily_timestamp(int(start_time.timestamp() * 1000))

        snapshots = await self.asset_history_db.get_snapshots_by_timeframe(
            start_timestamp, end_timestamp, limit=period
        )

        if len(snapshots) >= period:
            return snapshots
        
        current_assets = await self.get_current_assets()
        if not current_assets or "error" in current_assets:
            return snapshots

        existing_timestamps = {s["timestamp"] for s in snapshots}
        missing_timestamps = []

        curr_timestamp = start_timestamp
        while curr_timestamp <= end_timestamp:
            if curr_timestamp not in existing_timestamps:
                missing_timestamps.append(curr_timestamp)
            curr_timestamp += 86400000
            
        if not missing_timestamps:
            return snapshots
        
        assets_info = []
        usdt_total = Decimal("0")

        for exchange_name, assets in current_assets["exchanges"].items():
            exchange = self.wallet_service.exchanges.get(exchange_name)
            if not exchange:
                continue

            for symbol, asset in assets.items():
                if symbol == "USDT":
                    usdt_total += Decimal(str(asset["value_in_usdt"]))
                    continue
                    
                assets_info.append({
                    "exchange": exchange,
                    "exchange_name": exchange_name,
                    "symbol": symbol,
                    "total": Decimal(str(asset["total"])),
                    "avg_price": Decimal(str(asset["avg_price"]))
                })

        price_tasks = [
            self.quote_service.get_close_price_from_history(
                asset["exchange"],
                f"{asset['symbol']}/USDT",
                "1d",
                min(missing_timestamps),
                max(missing_timestamps)
            )
            for asset in assets_info
        ]

        price_results = await asyncio.gather(*price_tasks)

        price_maps = {
            f"{asset['exchange_name']}:{asset['symbol']}": prices
            for asset, prices in zip(assets_info, price_results)
            if prices
        }
        
        filled_snapshots = []
        for timestamp in sorted(missing_timestamps):
            try:
                total = usdt_total
                profit = Decimal("0")
                initial = Decimal("0")

                for asset in assets_info:
                    price_map = price_maps.get(f"{asset['exchange_name']}:{asset['symbol']}", {})
                    historical_price = price_map.get(timestamp)
                    
                    if not historical_price:
                        continue

                    value_in_usdt = asset["total"] * historical_price
                    initial_value = asset["total"] * asset["avg_price"]
                    asset_profit = value_in_usdt - initial_value

                    total += value_in_usdt
                    profit += asset_profit
                    initial += initial_value

                if initial > 0:
                    summary = AssetSummary.calculate_summary(
                        total=total,
                        profit=profit,
                        initial=initial
                    )

                    snapshot = {
                        "timestamp": timestamp,
                        "update_time": int(datetime.now(timezone.utc).timestamp() * 1000),
                        **summary.model_dump_for_db()
                    }
                    
                    await self.asset_history_db.update_history(snapshot)
                    filled_snapshots.append(snapshot)

            except Exception as e:
                print(f"Error calculating snapshot for timestamp {timestamp}: {e}")
                continue

        all_snapshots = snapshots + filled_snapshots
        all_snapshots.sort(key=lambda x: x["timestamp"])

        return all_snapshots

    async def update_daily_snapshot(self, timestamp: Optional[int] = None) -> bool:
        try:
            if timestamp is None:
                timestamp = self.__convert_to_daily_timestamp(int(datetime.now(timezone.utc).timestamp() * 1000))

            assets = await self.wallet_service.get_assets(timestamp=timestamp)
            
            return (assets) or ("error" not in assets)

        except Exception as e:
            print(f"Error updating daily snapshot: {e}")
            return False
