from typing import Dict
from typing import Optional
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

class OpenOrderRequest(BaseModel):
    exchange: str
    symbol: str
    side: str  # buy or sell
    order_type: str  # market or limit
    amount_type: str  # currency or USDT
    amount: float  # cost in quote currency if amount type is USDT (e.g. USDT)
    price: Optional[float] = None  # limit price, optional for market orders

class CancelOrderRequest(BaseModel):
    order_id: str

class CloseOrderRequest(BaseModel):
    exchange: str
    symbol: str
    order_type: str  # market or limit
    price: Optional[float] = None

class TransferRequest(BaseModel):
    from_exchange: str
    to_exchange: str
    currency: str
    from_address: str
    amount: float
    network: str