from datetime import datetime
from typing import Dict, Optional
from motor.motor_asyncio import AsyncIOMotorClient

from app.database.base import MongoDBBase


class ChartStorageDB(MongoDBBase):
    def __init__(self, mongo_client: AsyncIOMotorClient):
        super().__init__(mongo_client, "charts_storage")
        self.add_index("id")
        self.add_index("name")
        self.add_index("timestamp")

    async def get_next_sequence_value(self) -> int:
        result = await self.db.counters.find_one_and_update(
            {"_id": "chart_sequence"},
            {"$inc": {"sequence_value": 1}},
            upsert=True,
            return_document=True
        )
        return result["sequence_value"]

    async def save_chart(
        self,
        name: str,
        content: str,
        symbol: str,
        resolution: str,
        timestamp: Optional[int] = None
    ) -> bool:
        try:
            if timestamp is None:
                timestamp = int(datetime.now().timestamp() * 1000)

            id = await self.get_next_sequence_value()

            return await self.update_one(
                query={
                    "name": name
                },
                update={
                    "$set": {
                        "id": id,
                        "content": content,
                        "symbol": symbol,
                        "resolution": resolution,
                        "timestamp": timestamp,
                        "update_time": datetime.now()
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"Error saving chart: {e}")
            return False
        
    async def get_chart(
        self,
        id: int
    ) -> Optional[Dict]:

        return await self.find_one(
            query={
                "id": id
            },
            projection={
                "_id": 0,
                "id": 1,
                "name": 1,
                "content": 1,
                "symbol": 1,
                "timestamp": 1,
                "resolution": 1
            }
        )

    async def get_all_charts(self) -> Optional[Dict]:

        return await self.find_many(
            projection={
                "_id": 0,
                "id": 1,
                "name": 1,
                "content": 1,
                "symbol": 1,
                "timestamp": 1,
                "resolution": 1
            },
            sort=[("timestamp", -1)]
        )

    async def delete_chart(
        self,
        id: int
    ) -> bool:
        return await self.delete_one({
            "id": id
        })