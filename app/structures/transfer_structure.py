from pydantic import BaseModel

class Transaction(BaseModel):
    from_exchange: str
    to_exchange: str
    transaction_id: str
    chain_tx_id: str
    timestamp: int
    transaction_type: str
    from_tag: str
    to_tag: str
    from_address: str
    to_address: str
    amount: float
    currency: str
    status: str
    fee_currency: str
    fee_cost: float

    @classmethod
    def from_response(
        cls, 
        from_exchange: str, 
        to_exchange: str,
        from_tag: str,
        from_address: str,
        response: dict
    ) -> "Transaction":
        return cls(
            from_exchange=from_exchange,
            to_exchange=to_exchange,
            transaction_id=response.get("id", ""),
            chain_tx_id=response.get("chain_tx_id", ""),
            timestamp=response.get("timestamp", 0),
            transaction_type=response.get("type", ""),
            from_tag=from_tag,
            to_tag=response.get("tagTo", response.get("tag", "")),
            from_address=from_address,
            to_address=response.get("addressTo", response.get("address", "")),
            amount=response.get("amount", 0.0),
            currency=response.get("currency", ""),
            status=response.get("status", ""),
            fee_currency=response.get("fee", {}).get("currency", ""),
            fee_cost=response.get("fee", {}).get("cost", 0.0)
        )