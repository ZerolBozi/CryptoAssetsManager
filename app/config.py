from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    # Common Settings
    API_CONNECT_TIMEOUT: int = 15000
    ENABLE_RATE_LIMIT: bool = True

    # Binance API
    BINANCE_API_KEY: str
    BINANCE_SECRET: str
    
    # OKX API
    OKX_API_KEY: str
    OKX_SECRET: str
    OKX_PASSWORD: str

    # MEXC API
    MEXC_API_KEY: str
    MEXC_SECRET: str

    # Gate.io API
    GATEIO_API_KEY: str
    GATEIO_SECRET: str

    # API Version
    API_VERSION: str = "v1"

    @property
    def API_PREFIX(self) -> str:
        return f"/api/{self.API_VERSION}"
    
    # App settings
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = True

settings = Settings()