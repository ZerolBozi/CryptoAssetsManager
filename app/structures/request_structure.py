from typing import Dict, Any
from pydantic import BaseModel, Field

class AssetCostUpdate(BaseModel):
    exchange: str
    symbol: str
    cost: str

class ExchangeAPISettings(BaseModel):
    api_key: str = Field(..., description="API Key for the exchange")
    secret: str = Field(..., description="API Secret for the exchange")

class ExchangeSettingsUpdate(BaseModel):
    exchanges: Dict[str, ExchangeAPISettings]

class ChartSaveRequest(BaseModel):
    name: str = Field(..., description="Chart name")
    symbol: str = Field(..., description="Trading symbol")
    content: str = Field(..., description="Chart configuration content")
    resolution: str = Field(..., description="Chart resolution")