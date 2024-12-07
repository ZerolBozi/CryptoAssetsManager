from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        if cls.client is None:
            raise Exception("Database client not initialized")
        return cls.client

    @classmethod
    async def connect(cls):
        if cls.client is None:
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                maxPoolSize=settings.MONGODB_MAX_CONNECTIONS,
                minPoolSize=settings.MONGODB_MIN_CONNECTIONS
            )
            await cls.client.admin.command('ping')
            print("Connected to MongoDB")

    @classmethod
    async def close(cls):
        if cls.client is not None:
            await cls.client.close()
            cls.client = None
            print("Closed MongoDB connection")