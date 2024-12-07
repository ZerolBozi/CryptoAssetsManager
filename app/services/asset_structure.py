from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, TypeAlias, Union

@dataclass
class Balance:
    free: Decimal
    used: Decimal
    total: Decimal
    avg_price: Decimal
    current_price: Decimal
    roi: Decimal
    value_in_usdt: Decimal
    profit_usdt: Decimal

    def to_dict(self) -> Dict:
        return {
            "free": str(self.free),
            "used": str(self.used),
            "total": str(self.total),
            "avg_price": str(self.avg_price),
            "current_price": str(self.current_price),
            "roi": str(self.roi),
            "value_in_usdt": str(self.value_in_usdt),
            "profit_usdt": str(self.profit_usdt),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Balance':
        return cls(
            free=Decimal(data["free"]),
            used=Decimal(data["used"]),
            total=Decimal(data["total"]),
            avg_price=Decimal(data["avg_price"]),
            current_price=Decimal(data["current_price"]),
            roi=Decimal(data["roi"]),
            value_in_usdt=Decimal(data["value_in_usdt"]),
            profit_usdt=Decimal(data["profit_usdt"])
        )

@dataclass
class AssetSnapshot:
    timestamp: int
    exchanges: Dict[str, Dict[str, Balance]]
    summary: Dict[str, Decimal]
    update_time: int

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "exchanges": {
                exchange_name: {
                    symbol: balance.to_dict() 
                    for symbol, balance in balances.items()
                }
                for exchange_name, balances in self.exchanges.items()
            },
            "summary": {key: str(value) for key, value in self.summary.items()},
            "update_time": self.update_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AssetSnapshot':
        exchange_data = {
            exchange_name: {
                symbol: Balance.from_dict(balance_dict)
                for symbol, balance_dict in balances.items()
            }
            for exchange_name, balances in data["exchanges"].items()
        }
        
        summary_data = {
            key: Decimal(value) for key, value in data["summary"].items()
        }

        return cls(
            timestamp=int(data["timestamp"]),
            exchanges=exchange_data,
            summary=summary_data,
            update_time=int(data["update_time"])
        )

    @classmethod
    def from_spot_assets(cls, spot_assets: Dict, daily_timestamp: int = None, current_timestamp: int = None) -> 'AssetSnapshot':
        if daily_timestamp is None:
            current_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            daily_timestamp = (daily_timestamp // 86400000) * 86400000
            
        return cls(
            timestamp=daily_timestamp,
            exchanges=spot_assets["exchanges"],
            summary=spot_assets["summary"],
            update_time=current_timestamp
        )
    
ExchangeAssets: TypeAlias = Dict[str, Balance]
ExchangeDict: TypeAlias = Dict[str, ExchangeAssets]
SummaryDict: TypeAlias = Dict[str, Decimal]
AssetsData: TypeAlias = Dict[str, Union[ExchangeDict, SummaryDict]]