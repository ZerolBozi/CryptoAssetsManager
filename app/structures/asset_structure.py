from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime, timezone

class Asset(BaseModel):
    exchange: str
    symbol: str
    free: Decimal
    used: Decimal
    total: Decimal
    avg_price: Decimal
    current_price: Decimal
    roi: Decimal
    value_in_usdt: Decimal
    profit_usdt: Decimal
    update_time: int

    @classmethod
    def calculate_metrics(cls, 
        exchange: str,
        symbol: str,
        free: Decimal,
        used: Decimal,
        total: Decimal,
        avg_price: Decimal,
        current_price: Decimal
    ) -> "Asset":
        roi = ((current_price - avg_price) / avg_price * Decimal("100")) if avg_price else Decimal("0")
        value_in_usdt = total * current_price
        profit_usdt = (current_price - avg_price) * total

        return cls(
            exchange=exchange,
            symbol=symbol,
            free=free,
            used=used,
            total=total,
            avg_price=avg_price,
            current_price=current_price,
            roi=roi,
            value_in_usdt=value_in_usdt,
            profit_usdt=profit_usdt,
            update_time=int(datetime.now(timezone.utc).timestamp() * 1000)
        )
    
    def model_dump_for_db(self) -> dict:
        data = self.model_dump()
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
        return data
    
class AssetSummary(BaseModel):
    total: Decimal
    profit: Decimal
    initial: Decimal
    roi: Decimal

    @classmethod
    def calculate_summary(cls, total: Decimal, profit: Decimal, initial: Decimal) -> "AssetSummary":
        roi = (profit / initial * Decimal("100")) if initial else Decimal("0")
        return cls(
            total=total,
            profit=profit,
            initial=initial,
            roi=roi
        )
    
    def model_dump_for_db(self) -> dict:
        data = self.model_dump()
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
        return data

class AssetHistory(BaseModel):
    timestamp: int
    update_time: int
    summary: AssetSummary