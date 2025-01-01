import re
from typing import Dict, Optional

import ccxt.async_support as ccxt

from app.services.exchange.base_exchange import BaseExchange
from app.structures.transfer_structure import Transaction


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
    
    async def get_common_networks(self, from_exchange: str, to_exchange: str, currency: str) -> Dict:
        """
        Returns:
            Dict: Common networks between exchanges
            {
                "VET": {
                    "binance": {
                        "withdraw": {
                            "fee": 3,
                            "percentage": null
                        },
                        "deposit": {
                            "fee": null,
                            "percentage": null
                        }
                    },
                    "mexc": {
                        "withdraw": {
                            "fee": 30,
                            "percentage": null
                        },
                        "deposit": {
                            "fee": null,
                            "percentage": null
                        }
                    }
                }
            }
        """
        try:
            source_networks = await self.get_deposit_networks(from_exchange, currency)
            destination_networks = await self.get_deposit_networks(to_exchange, currency)

            if (not source_networks) or (not destination_networks):
                return {}

            common_networks = {}

            for network in source_networks:
                if network in destination_networks:
                    common_networks[network] = {
                        from_exchange: source_networks[network],
                        to_exchange: destination_networks[network]
                    }

            return common_networks
        
        except Exception as e:
            print(e)
            return {}

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
            if not exchange:
                raise ValueError(f"Exchange {exchange_name} not found")
            
            data: dict = await exchange.fetch_deposit_withdraw_fee(currency)

            if data is None:
                return {}

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
            if not exchange:
                raise ValueError(f"Exchange {exchange_name} not found")
            
            data: dict = await exchange.fetch_deposit_address(
                currency, params={"network": network}
            )
            return {
                "currency": data.get("currency", ""),
                "address": data.get("address", ""),
                "tag": data.get("tag", ""),
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
        tag: Optional[str] = None
    ) -> dict:
        """
        Withdraw funds from an exchange.

        Args:
            exchange_name: Exchange name (e.g. 'binance')
            currency: Currency to withdraw (e.g. 'BTC')
            amount: Amount to withdraw 
            address: Withdrawal address
            network: Network for withdrawal (e.g. 'TRC20')
            tag: Tag for withdrawal (e.g. '12345')

        Returns:
            Dict: Withdrawal response
        """
        try:
            exchange = self.__get_exchange_by_name(exchange_name)
            if not exchange:
                raise ValueError(f"Exchange {exchange_name} not found")
                
            response = await exchange.withdraw(
                code=currency,
                amount=amount,
                address=address,
                tag=tag,
                params={"network": network}
            )
            
            return response
            
        except Exception as e:
            print(f"Withdrawal error: {str(e)}")
            return {}
        
    async def transfer_between_exchange(
        self,
        from_exchange_name: str,
        to_exchange_name: str,
        currency: str,
        amount: float,
        network: str,
    ) -> Transaction:
        """
        Transfer funds between exchanges.

        Args:
            from_exchange_name: Exchange name to transfer from (e.g. 'binance')
            to_exchange_name: Exchange name to transfer to (e.g. 'kucoin')
            currency: Currency to transfer (e.g. 'BTC')
            amount: Amount to transfer
            network: Network for transfer (e.g. 'TRC20')

        Returns:
            TransferTransaction: Transfer response
        """
        try:
            withdraw_address = await self.get_deposit_address(
                exchange_name=from_exchange_name,
                currency=currency,
                network=network
            )

            deposit_address = await self.get_deposit_address(
                exchange_name=to_exchange_name,
                currency=currency,
                network=network
            )
            
            if not deposit_address.get("address"):
                return {"success": False}
                
            withdraw = await self.withdraw(
                exchange_name=from_exchange_name,
                currency=currency,
                amount=amount,
                address=deposit_address["address"],
                network=network,
                tag=deposit_address.get("tag", None)
            )
            
            transaction = Transaction.from_response(
                from_exchange_name, 
                to_exchange_name,
                from_tag=withdraw_address.get("tag", ""),
                from_address=withdraw_address.get("address", ""),
                response=withdraw
            )

            return transaction
            
        except Exception as e:
            print(f"Transfer error: {str(e)}")
            return {}