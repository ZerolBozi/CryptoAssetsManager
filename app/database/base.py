from typing import List, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.config import settings


class MongoDBBase:
    def __init__(self, mongo_client: AsyncIOMotorClient, collection_name: str):
        self.client = mongo_client
        self.db = self.client[settings.MONGODB_DB_NAME]
        self.collection: AsyncIOMotorCollection = self.db[collection_name]
        self._indexes = []

    def add_index(self, keys, unique=False):
        self._indexes.append((keys, unique))

    async def create_indexes(self):
        for keys, unique in self._indexes:
            await self.collection.create_index(keys, unique=unique)

    async def insert_one(self, document: Dict) -> Optional[str]:
        try:
            result = await self.collection.insert_one(document)
            return str(result.inserted_id) if result.inserted_id else None
        except Exception as e:
            print(f"Error inserting document: {e}")
            return None

    async def insert_many(self, documents: List[Dict]) -> bool:
        try:
            if documents:
                result = await self.collection.insert_many(documents)
                return bool(result.inserted_ids)
            return False
        except Exception as e:
            print(f"Error inserting documents: {e}")
            return False

    async def find_one(
        self, query: Dict = None, projection: Dict = None
    ) -> Optional[Dict]:
        try:
            return await self.collection.find_one(query, projection)
        except Exception as e:
            print(f"Error finding document: {e}")
            return None

    async def find_many(
        self,
        query: Dict = None,
        projection: Dict = None,
        sort: List[tuple] = None,
        limit: int = None,
    ) -> List[Dict]:
        try:
            cursor = self.collection.find(query, projection)
            if sort:
                cursor = cursor.sort(sort)
            if limit:
                cursor = cursor.limit(limit)
            return await cursor.to_list(None)
        except Exception as e:
            print(f"Error finding documents: {e}")
            return []

    async def update_one(self, query: Dict, update: Dict, upsert: bool = False) -> bool:
        try:
            result = await self.collection.update_one(query, update, upsert=upsert)
            return result.modified_count > 0 or (upsert and result.upserted_id)
        except Exception as e:
            print(f"Error updating document: {e}")
            return False

    async def update_many(self, query: Dict, update: Dict, upsert: bool = False) -> int:
        try:
            result = await self.collection.update_many(query, update, upsert=upsert)
            return result.modified_count
        except Exception as e:
            print(f"Error updating documents: {e}")
            return False

    async def delete_one(self, query: Dict) -> bool:
        try:
            result = await self.collection.delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False

    async def delete_many(self, query: Dict) -> int:
        try:
            result = await self.collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            print(f"Error deleting documents: {e}")
            return False

    async def count_documents(self, query: Dict) -> int:
        try:
            return await self.collection.count_documents(query)
        except Exception as e:
            print(f"Error counting documents: {e}")
            return 0

    async def aggregate(self, pipeline: List[Dict]) -> List[Dict]:
        try:
            cursor = self.collection.aggregate(pipeline)
            return await cursor.to_list(None)
        except Exception as e:
            print(f"Error aggregating documents: {e}")
            return []
