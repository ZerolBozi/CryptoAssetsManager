import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=5000,
        reload=settings.DEBUG,
        workers=1 
    )