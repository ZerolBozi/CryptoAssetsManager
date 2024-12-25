from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.database.base import MongoDBBase
from app.structures.transfer_structure import Transaction

class TransferDB(MongoDBBase):
    def __init__(self, mongo_client: AsyncIOMotorClient):
        super().__init__(mongo_client, "transfers")
        self.add_index([("from_exchange", 1), ("to_exchange", 1), ("currency", 1)])
        self.add_index([("timestamp", -1)])
        self.add_index([("from_exchange", 1), ("transaction_id", 1)], unique=True)
        self.add_index([("chain_tx_id", 1)])

    async def save_transaction(self, transaction: Transaction) -> str:
        return await self.insert_one(transaction.model_dump())
    
    async def update_transaction(
        self, 
        from_exchange: str, 
        transaction_id: str, 
        transaction: Transaction
    ) -> bool:
        return await self.update_one(
            query={
                "from_exchange": from_exchange, 
                "transaction_id": transaction_id
            },
            update={
                "$set": transaction.model_dump()
            }
        )
    
    async def update_transaction_status(
        self, 
        from_exchange: str, 
        transaction_id: str, 
        status: str
    ) -> bool:
        return await self.update_one(
            query={
                "from_exchange": from_exchange, 
                "transaction_id": transaction_id
            },
            update={
                "$set": {"status": status}
            }
        )
    
    async def get_transaction(self, tx_id: str) -> Optional[Dict]:
        return await self.find_one({"tx_id": tx_id})
    
    async def find_transactions(
        self, 
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        query = {}
        if exchange:
            query["exchange"] = exchange
        if symbol:
            query["symbol"] = symbol
            
        return await self.find_many(
            query=query,
            sort=[("timestamp", -1)],
            limit=limit
        )