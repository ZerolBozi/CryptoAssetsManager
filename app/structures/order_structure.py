from pydantic import BaseModel

class Order(BaseModel):
    exchange: str
    order_id: str
    timestamp: int
    status: str
    symbol: str
    order_type: str
    side: str
    price: float
    avg_price: float
    amount: float
    filled: float
    remaining: float
    cost: float
    fee_currency: str
    fee_cost: float

    @classmethod
    def from_response(cls, order: dict) -> "Order":
        return cls(
            exchange=order.get('exchange', ''),
            order_id=order.get('id', ''),
            timestamp=order.get('timestamp', 0),
            status=order.get('status', ''),
            symbol=order.get('symbol', ''),
            order_type=order.get('type', ''),
            side=order.get('side', ''),
            price=order.get('price', 0.0),
            avg_price=order.get('average', 0.0),
            amount=order.get('amount', 0.0),
            filled=order.get('filled', 0.0),
            remaining=order.get('remaining', 0.0),
            cost=order.get('cost', 0.0),
            fee_currency=order.get('fee', {}).get('currency', ''),
            fee_cost=order.get('fee', {}).get('cost', 0.0)
        )