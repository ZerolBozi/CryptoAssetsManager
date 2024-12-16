from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.database.base import MongoDBBase


class AssetDB(MongoDBBase):
    def __init__(self, mongo_client: AsyncIOMotorClient):
        super().__init__(mongo_client, "asset")
        self.add_index([("exchange", 1), ("symbol", 1)], unique=True)
        self.add_index("update_time")

    async def get_all_assets(self) -> Optional[List[Dict]]:
        return await self.find_many(
            projection={"_id": 0},
        )
    
    async def get_asset_by_time_diff(self, time_diff: int) -> Optional[Dict]:
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        return await self.find_one(
            query={"update_time": {"$gt": current_time - time_diff}},
            projection={"_id": 0},
        )
    
    async def update_asset(self, exchange: str, symbol: str, data: Dict) -> bool:
        return await self.update_one(
            query={
                "exchange": exchange,
                "symbol": symbol
            },
            update={
                "$set": data
            },
            upsert=True,
        )
    
    async def update_avg_price(self, exchange: str, symbol: str, avg_price: Decimal) -> bool:
        return await self.update_one(
            query={
                "exchange": exchange,
                "symbol": symbol
            },
            update={
                "$set": {
                    "avg_price": str(avg_price),
                    "update_time": int(datetime.now(timezone.utc).timestamp() * 1000)
                }
            },
            upsert=False
        )