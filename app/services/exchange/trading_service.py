from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

import ccxt.async_support as ccxt

from app.services.exchange.base_exchange import BaseExchange
from app.services.exchange.quote_service import QuoteService


class TradingService(BaseExchange):
    def __init__(self, quote_service: QuoteService):
        super().__init__()
        self.quote_service = quote_service

    async def place_order(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float = None,
    ) -> Dict:
        """
        Place an order on an exchange.

        Args:
            exchange: ccxt Exchange instance
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            amount: Order amount
            price: Order price (required for limit order)

        Returns:
            Dict: Order response from exchange
            {
                'id':                '12345-67890:09876/54321', // string
                'clientOrderId':     'abcdef-ghijklmnop-qrstuvwxyz', // a user-defined clientOrderId, if any
                'datetime':          '2017-08-17 12:42:48.000', // ISO8601 datetime of 'timestamp' with milliseconds
                'timestamp':          1502962946216, // order placing/opening Unix timestamp in milliseconds
                'lastTradeTimestamp': 1502962956216, // Unix timestamp of the most recent trade on this order
                'status':      'open',        // 'open', 'closed', 'canceled', 'expired', 'rejected'
                'symbol':      'ETH/BTC',     // symbol
                'type':        'limit',       // 'market', 'limit'
                'timeInForce': 'GTC',         // 'GTC', 'IOC', 'FOK', 'PO'
                'side':        'buy',         // 'buy', 'sell'
                'price':        0.06917684,   // float price in quote currency (may be empty for market orders)
                'average':      0.06917684,   // float average filling price
                'amount':       1.5,          // ordered amount of base currency
                'filled':       1.1,          // filled amount of base currency
                'remaining':    0.4,          // remaining amount to fill
                'cost':         0.076094524,  // 'filled' * 'price' (filling price used where available)
                'trades':     [ ... ],        // a list of order trades/executions
                'fee': {                      // fee info, if available
                    'currency': 'BTC',        // which currency the fee is (usually quote)
                    'cost': 0.0009,           // the fee amount in that currency
                    'rate': 0.002,            // the fee rate (if available)
                },
                'info': { ... },              // the original unparsed order structure as is
            }
        """
        try:
            if side not in ["buy", "sell"]:
                raise ValueError("Side must be 'buy' or 'sell'")

            if order_type not in ["market", "limit"]:
                raise ValueError("Order type must be 'market' or 'limit'")

            if (order_type == "limit") and (price is None):
                raise ValueError("Price is required for limit orders")

            order_params = {
                "symbol": symbol,
                "type": order_type,
                "side": side,
                "amount": amount,
            }

            if order_type == "limit":
                order_params["price"] = price

            response = await exchange.create_order(**order_params)
            return response

        except Exception as e:
            raise Exception(f"Failed to place order: {str(e)}")

    async def place_order_with_cost(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        side: str,
        order_type: str,
        cost: float,
        price: float = None,
    ) -> Dict:
        """
        Place an order on an exchange with cost.

        Args:
            exchange: ccxt Exchange instance
            symbol: Trading pair symbol (e.g. 'BTC/USDT')
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            cost: Order cost
            price: Order price (required for limit order)

        Returns:
            Dict: Order response from exchange
        """
        try:
            if price is None:
                current_price = await self.quote_service.get_current_price(
                    exchange, symbol
                )
                if not current_price:
                    raise ValueError("Failed to get current price")
                _price = float(current_price)
            else:
                _price = price

            amount = Decimal(str(cost / _price))
            rounded_amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            return await self.place_order(
                exchange=exchange,
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=float(rounded_amount),
                price=_price if order_type == "limit" else None,
            )

        except Exception as e:
            print(e)
            return {}

    async def get_trade_history(
        self, exchange: ccxt.Exchange, symbol: str
    ) -> List[Dict]:
        """
        Get recent trades for a symbol from an exchange. (Use fetchMyTrades)

        Args:
            exchange: ccxt Exchange instance
            symbol: Trading pair symbol (e.g. 'BTC/USDT')

        Returns:
            List[Dict]: List of trade data
        """
        try:
            if not exchange.has["fetchMyTrades"]:
                return []

            symbol_alternatives = {
                "RENDER/USDT": "RNDR/USDT",
                "FET/USDT": "OCEAN/USDT",
                "OCEAN/USDT": "AGIX/USDT",
            }

            trades = await exchange.fetch_my_trades(symbol)
            if (not trades) and (symbol in symbol_alternatives):
                trades = await exchange.fetch_my_trades(symbol_alternatives[symbol])

            return trades

        except Exception as e:
            print(e)
            return []
