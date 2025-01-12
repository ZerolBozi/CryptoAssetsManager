from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.database.base import MongoDBBase
from app.structures.order_structure import Order

class OrderDB(MongoDBBase):
    def __init__(self, mongo_client: AsyncIOMotorClient):
        super().__init__(mongo_client, "orders")
        self.add_index([("exchange", 1), ("symbol", 1)])
        self.add_index([("timestamp", -1)])
        self.add_index([("order_id", 1)], unique=True)

    async def save_order(self, order: Order) -> str:
        return await self.insert_one(order.model_dump())
    
    async def update_order(self, order_id: str, order: Order) -> bool:
        return await self.update_one(
            query={"order_id": order_id},
            update={
                "$set": order.model_dump()
            }
        )
    
    async def update_order_status(self, order_id: str, status: str) -> bool:
        return await self.update_one(
            query={"order_id": order_id},
            update={
                "$set": {"status": status}
            }
        )
    
    async def get_order_by_id(self, order_id: str) -> Optional[Dict]:
        return await self.find_one({"order_id": order_id})
    
    async def find_orders(
        self, 
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        query = {}
        if exchange:
            query["exchange"] = exchange
        if symbol:
            query["symbol"] = symbol
        if status:
            query["status"] = status

        if start_time or end_time:
            query["timestamp"] = {}
            if start_time:
                query["timestamp"]["$gte"] = int(start_time.timestamp() * 1000)
            if end_time:
                query["timestamp"]["$lte"] = int(end_time.timestamp() * 1000)

        cursor = await self.find_many(
            query=query,
            sort=[("timestamp", -1)],
            limit=limit
        )

        orders = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            orders.append(doc)

        return orders
    
    async def find_orders_by_timespan(
        self, 
        days: int,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        
        start_time = end_time - timedelta(days=days)
        
        return await self.find_orders(
            exchange=exchange,
            symbol=symbol,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )