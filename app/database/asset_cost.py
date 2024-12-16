import time

from decimal import Decimal
from typing import Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.database.base import MongoDBBase

class AssetCostDB(MongoDBBase):
    def __init__(self, mongo_client: AsyncIOMotorClient):
        super().__init__(mongo_client, "asset_cost")
        self.add_index([("exchange", 1), ("symbol", 1)], unique=True)
        self.add_index("update_time")
        self.add_index("update_by")

    async def get_asset_cost(self, exchange: str, symbol: str) -> Optional[Dict]:
        return await self.find_one(
            query={
                "exchange": exchange,
                "symbol": symbol
            },
            projection={"_id": 0},
        )

    async def update_asset_cost(
        self, 
        exchange: str, 
        symbol: str, 
        avg_price: Decimal,
        update_by: str
    ) -> bool:
        return await self.update_one(
            query={
                "exchange": exchange,
                "symbol": symbol
            },
            update={
                "$set": {
                    "avg_price": str(avg_price),
                    "update_time": int(time.time()),
                    "update_by": update_by
                }
            },
            upsert=True,
        )