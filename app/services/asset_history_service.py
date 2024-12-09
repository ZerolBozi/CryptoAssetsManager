from decimal import Decimal
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from app.database.asset_history import AssetHistoryDB
from app.services.exchange.wallet_service import WalletService
from app.structures.asset_structure import AssetSnapshot, AssetsData

class AssetHistoryService:
    def __init__(self, wallet_service: WalletService, asset_history_db: AssetHistoryDB):
        self.wallet_service = wallet_service
        self.quote_service = wallet_service.quote_service
        self.asset_history_db = asset_history_db

    def __convert_to_daily_timestamp(self, timestamp: int) -> int:
        return (timestamp // 86400000) * 86400000
    
    async def get_asset_history(self, period: int) -> List[AssetSnapshot]:
        """
        Get asset history for specified time period, filling gaps with historical price data if needed.
        
        Args:
            period: Time period for history (30d, 90d, 180d, 1y)
            
        Returns:
            List[AssetSnapshot]: List of snapshots for the period
        """      
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=period)
        
        end_timestamp = int(end_time.timestamp() * 1000)
        start_timestamp = int(start_time.timestamp() * 1000)
        
        snapshots = await self.get_snapshots_by_timeframe(start_timestamp, end_timestamp)

        simplified_snapshots = [
            {
                "timestamp": snapshot.timestamp,
                "summary": snapshot.summary
            } for snapshot in snapshots
        ]
        
        if len(simplified_snapshots) >= period:
            return simplified_snapshots
            
        if not simplified_snapshots:
            return []
            
        filled_snapshots = await self.__fill_history_data(
            snapshots,
            start_timestamp,
            end_timestamp
        )
        
        return filled_snapshots

    async def __fill_history_data(
            self,
            existing_snapshots: List[AssetSnapshot],
            start_timestamp: int,
            end_timestamp: int
        ) -> List[AssetSnapshot]:

        filled_snapshots = []
        oldest_snapshot = existing_snapshots[0]
        
        timestamp_data = {}
    
        for exchange_name, assets in oldest_snapshot.exchanges.items():
            exchange = self.wallet_service.exchanges.get(exchange_name)
            if not exchange:
                continue
                
            for symbol, balance in assets.items():
                if symbol == "USDT":
                    continue
                    
                price_history = await self.quote_service.get_price_history(
                    exchange,
                    f"{symbol}/USDT",
                    '1d',
                    start_timestamp,
                    end_timestamp
                )
                
                if 'error' in price_history:
                    continue
                    
                for candle in price_history['data']:
                    timestamp = candle['timestamp']
                    close_price = Decimal(str(candle['close']))
                    
                    existing_snapshot = next(
                        (s for s in existing_snapshots if s.timestamp == timestamp),
                        None
                    )
                    
                    if existing_snapshot:
                        if timestamp not in [s["timestamp"] for s in filled_snapshots]:
                            filled_snapshots.append({
                                "timestamp": existing_snapshot.timestamp,
                                "summary": existing_snapshot.summary
                            })
                        continue

                    if timestamp not in timestamp_data:
                        timestamp_data[timestamp] = {
                            'total': Decimal('0'),
                            'profit': Decimal('0'),
                            'initial': Decimal('0'),
                            'roi': Decimal('0')
                        }

                    value_in_usdt = balance.total * close_price
                    initial_value = balance.total * balance.avg_price
                    profit = value_in_usdt - initial_value

                    timestamp_data[timestamp]['total'] += value_in_usdt
                    timestamp_data[timestamp]['profit'] += profit
                    timestamp_data[timestamp]['initial'] += initial_value

        for timestamp, summary_data in timestamp_data.items():
            if summary_data['initial'] > 0:
                summary_data['roi'] = (summary_data['profit'] / summary_data['initial'] * 100)
            
            snapshot_data = {
                "timestamp": timestamp,
                "summary": summary_data
            }
            
            if timestamp not in [s["timestamp"] for s in filled_snapshots]:
                filled_snapshots.append(snapshot_data)
        
        filled_snapshots.sort(key=lambda x: x["timestamp"])
        
        return filled_snapshots
    
    async def update_daily_snapshot(self, assets: Optional[AssetsData] = None, min_value: Decimal = Decimal('1'), timestamp: int = None) -> Optional[AssetSnapshot]:
        """
        Update or create daily snapshot with provided assets data
        
        Args:
            assets: Assets data from get_spot_assets
                   Format: {
                       'exchanges': {exchange_name: {symbol: Balance}},
                       'summary': {metric: Decimal}
                   }
            
        Returns:
            Optional[AssetSnapshot]: Updated or created snapshot
        """
        try:
            if assets is None:
                assets = await self.wallet_service.get_assets(min_value, timestamp)
                if not assets:
                    return None
            
            # Get current daily timestamp
            current_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            if timestamp is None:
                daily_timestamp = self.__convert_to_daily_timestamp(current_timestamp)
            else:
                daily_timestamp = timestamp
            
            # Create snapshot from assets data
            snapshot = AssetSnapshot.from_spot_assets(assets, daily_timestamp, current_timestamp)
            
            # Update or insert snapshot
            await self.asset_history_db.update_one(
                query={"timestamp": daily_timestamp},
                update={"$set": snapshot.to_dict()},
                upsert=True
            )
            
            return snapshot
            
        except Exception as e:
            print(f"Error updating daily snapshot: {e}")
            return None
        
    async def get_latest_snapshot(self) -> Optional[AssetSnapshot]:
        try:
            snapshot_data = await self.asset_history_db.get_latest_snapshot()
            if not snapshot_data:
                return None
            return AssetSnapshot.from_dict(snapshot_data)
        except Exception as e:
            print(f"Error getting latest snapshot: {e}")
            return None

    async def get_snapshots_by_timeframe(
            self, 
            start_time: int, 
            end_time: int
        ) -> List[AssetSnapshot]:
        """
        Get all snapshots within a timeframe
        
        Args:
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            
        Returns:
            List[AssetSnapshot]: List of snapshots in the timeframe
        """
        try:
            start_timestamp = self.__convert_to_daily_timestamp(start_time)
            end_timestamp = self.__convert_to_daily_timestamp(end_time)

            snapshots_data = await self.asset_history_db.get_snapshots_by_timeframe(
                start_timestamp,
                end_timestamp
            )
            return [AssetSnapshot.from_dict(data) for data in snapshots_data]
        except Exception as e:
            print(f"Error getting snapshots by timeframe: {e}")
            return []