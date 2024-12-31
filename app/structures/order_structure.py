from pydantic import BaseModel, field_validator

class Order(BaseModel):
    exchange: str = ''
    order_id: str = ''
    timestamp: int = 0
    status: str = ''
    symbol: str = ''
    order_type: str = ''
    side: str = ''
    price: float = 0.0
    avg_price: float = 0.0
    amount: float = 0.0
    filled: float = 0.0
    remaining: float = 0.0
    cost: float = 0.0
    fee_currency: str = ''
    fee_cost: float = 0.0

    @field_validator('*', mode='before')
    @classmethod
    def convert_none_to_default(cls, value):
        if value is None:
            return 0.0 if isinstance(value, (float, type(None))) else ''
        return value

    @classmethod
    def from_response(cls, exchange: str, order: dict) -> "Order":
        if order is None:
            order = {}

        fee = order.get('fee') or {}

        return cls(
            exchange=exchange,
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
            fee_currency=fee.get('currency', ''),
            fee_cost=fee.get('cost', 0.0)
        )