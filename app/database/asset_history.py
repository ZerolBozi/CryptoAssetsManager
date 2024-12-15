from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from .base import MongoDBBase


class AssetHistoryDB(MongoDBBase):
    def __init__(self, mongo_client: AsyncIOMotorClient):
        super().__init__(mongo_client, "asset_history")
        self.add_index("timestamp", unique=True)
        self.add_index("update_time")

    async def get_latest_snapshot(self) -> Optional[Dict]:
        return await self.find_one(
            projection={"_id": 0},
        )

    async def get_snapshots_by_timeframe(
        self, start_time: int, end_time: int
    ) -> List[Dict]:
        return await self.find_many(
            query={"timestamp": {"$gte": start_time, "$lte": end_time}},
            projection={"_id": 0},
        )
