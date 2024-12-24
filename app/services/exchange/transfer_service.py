import re
from typing import Dict, Optional

import ccxt.async_support as ccxt

from app.services.exchange.base_exchange import BaseExchange


class TransferService(BaseExchange):
    def __init__(self):
        super().__init__()

    def __get_exchange_by_name(self, exchange_name: str) -> Optional[ccxt.Exchange]:
        """
        Get exchange instance by name.

        Args:
            exchange_name: Exchange name (e.g. 'binance')

        Returns:
            ccxt.Exchange: Exchange instance
        """
        return self.exchanges.get(exchange_name, None)

    async def get_deposit_networks(self, exchange_name: str, currency: str) -> Dict:
        """
        Get deposit networks for a currency from an exchange.

        Args:
            exchange: ccxt Exchange instance
            currency: currency (e.g. 'BTC')

        Returns:
            Dict: Deposit networks
            {
                "BEP20":{
                    "withdraw":{
                        "fee":0.0,
                        "percentage":"None"
                    },
                    "deposit":{
                        "fee":"None",
                        "percentage":"None"
                    }
                },
                "EOS":{
                    "withdraw":{
                        "fee":1.0,
                        "percentage":"None"
                    },
                    "deposit":{
                        "fee":"None",
                        "percentage":"None"
                    }
                }
            }
        """
        try:
            exchange = self.__get_exchange_by_name(exchange_name)
            data: dict = await exchange.fetch_deposit_withdraw_fee(currency)
            networks = data.get("networks", "")
            if exchange.id == "mexc":
                networks = {
                    re.search(r"\((.*?)\)", k).group(1) if "(" in k else k: v
                    for k, v in networks.items()
                }

            return networks

        except Exception as e:
            print(e)
            return {}

    async def get_deposit_address(
        self, exchange_name: str, currency: str, network: str
    ) -> Dict:
        """
        Get deposit address for a currency from an exchange.

        Args:
            exchange: ccxt Exchange instance
            currency: currency (e.g. 'BTC')
            network: Network (e.g. 'TRC20')

        Returns:
            Dict: Deposit address
            {
                'currency': currency,
                'address': deposit_address,
            }
        """
        try:
            exchange = self.__get_exchange_by_name(exchange_name)
            data: dict = await exchange.fetch_deposit_address(
                currency, params={"network": network}
            )
            return {
                "currency": data.get("currency", ""),
                "address": data.get("address", ""),
            }

        except Exception as e:
            print(e)
            return {}

    async def withdraw(
        self,
        exchange_name: str,
        currency: str,
        amount: float,
        address: str,
        network: str,
    ) -> Dict:
        pass
