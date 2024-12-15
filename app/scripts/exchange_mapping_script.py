import os
import re
import json
from abc import ABC, abstractmethod

import requests


class BaseExchange(ABC):
    def __init__(self):
        self.markets = []
        self.quote_markets = []

    @abstractmethod
    def _get_markets(self):
        pass

    @abstractmethod
    def get_quote_markets(self) -> list:
        pass

    def get_all_symbols(self) -> list:
        """Get all symbols from quote currency market"""
        quote_markets = self.get_quote_markets()
        return self._extract_symbols(quote_markets)

    @abstractmethod
    def _extract_symbols(self, markets: list) -> list:
        """Extract base symbols from market pairs"""
        pass


class Upbit(BaseExchange):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.upbit.com/v1"
        self.except_symbol = "USD"

    def _get_markets(self):
        url = f"{self.base_url}/market/all?isDetails=true"
        response = requests.get(url)
        self.markets = response.json()

    def get_quote_markets(self) -> list:
        """Get KRW markets"""
        if not self.markets:
            self._get_markets()

        self.quote_markets = [
            item["market"]
            for item in self.markets
            if item["market"].startswith("KRW")
            and self.except_symbol not in item["market"]
        ]
        return self.quote_markets

    def _extract_symbols(self, markets: list) -> list:
        return [re.sub(r"KRW-", "", market) for market in markets]

    def get_day_candles(self, market: str, count: int = 200) -> list:
        url = f"{self.base_url}/candles/days?market={market}&count={count}"
        response = requests.get(url)
        return response.json()

    def get_week_candles(self, market: str, count: int = 200) -> list:
        url = f"{self.base_url}/candles/weeks?market={market}&count={count}"
        response = requests.get(url)
        return response.json()

    def get_ticker_info(self, market: str) -> dict:
        url = f"{self.base_url}/ticker?markets={market}"
        response = requests.get(url)
        return response.json()[0]

    def get_current_price(self, market: str) -> float:
        return self.get_ticker_info(market)["trade_price"]

    def get_day_amount(self, market: str) -> float:
        return self.get_ticker_info(market)["acc_trade_price_24h"]


class USDTExchange(BaseExchange):
    """Base class for exchanges using USDT as quote currency"""

    def get_quote_markets(self) -> list:
        if not self.markets:
            self._get_markets()
        return self.quote_markets


class Binance(USDTExchange):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.binance.com/api/v3"

    def _get_markets(self):
        url = f"{self.base_url}/exchangeInfo"
        response = requests.get(url)
        self.markets = response.json()["symbols"]
        self.quote_markets = [
            item["symbol"] for item in self.markets if item["symbol"].endswith("USDT")
        ]

    def _extract_symbols(self, markets: list) -> list:
        return [re.search(r"(\w+)USDT", s).group(1) for s in markets]


class OKX(USDTExchange):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.okx.com/api/v5"

    def _get_markets(self):
        url = f"{self.base_url}/public/instruments?instType=SPOT"
        response = requests.get(url)
        self.markets = response.json()
        self.quote_markets = [
            item["instId"]
            for item in self.markets["data"]
            if item["quoteCcy"] == "USDT"
        ]

    def _extract_symbols(self, markets: list) -> list:
        return [re.search(r"(\w+)-USDT", s).group(1) for s in markets]


class Bybit(USDTExchange):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.bybit.com/v5"

    def _get_markets(self):
        url = f"{self.base_url}/market/instruments-info?category=spot"
        response = requests.get(url)
        self.markets = response.json()
        self.quote_markets = [
            item["symbol"]
            for item in self.markets["result"]["list"]
            if item["quoteCoin"] == "USDT"
        ]

    def _extract_symbols(self, markets: list) -> list:
        return [re.search(r"(\w+)USDT", s).group(1) for s in markets]


class Bitget(USDTExchange):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.bitget.com/api/v2"

    def _get_markets(self):
        url = f"{self.base_url}/spot/public/symbols"
        response = requests.get(url)
        self.markets = response.json()
        self.quote_markets = [
            item["symbol"]
            for item in self.markets["data"]
            if item["quoteCoin"] == "USDT"
        ]

    def _extract_symbols(self, markets: list) -> list:
        return [re.search(r"(\w+)USDT", s).group(1) for s in markets]


class MEXC(USDTExchange):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.mexc.com/api/v3"

    def _get_markets(self):
        url = f"{self.base_url}/exchangeInfo"
        response = requests.get(url)
        self.markets = response.json()
        self.quote_markets = [
            symbol["symbol"]
            for symbol in self.markets["symbols"]
            if symbol["quoteAsset"] == "USDT" and symbol["status"] == "1"
        ]

    def _extract_symbols(self, markets: list) -> list:
        return [re.search(r"(\w+)USDT", s).group(1) for s in markets]


class Gate(USDTExchange):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.gateio.ws/api/v4"

    def _get_markets(self):
        url = f"{self.base_url}/spot/currency_pairs"
        response = requests.get(url)
        self.markets = response.json()
        self.quote_markets = [
            item["id"]
            for item in self.markets
            if item["quote"] == "USDT" and item["trade_status"] == "tradable"
        ]

    def _extract_symbols(self, markets: list) -> list:
        return [re.search(r"(\w+)_USDT", s).group(1) for s in markets]


def make_symbol_exchange_mapping() -> dict:
    exchanges = {
        "Binance": Binance(),
        "OKX": OKX(),
        "Bybit": Bybit(),
        "Bitget": Bitget(),
        "MEXC": MEXC(),
        "Gate.io": Gate(),
        "Upbit": Upbit(),
    }

    # Get all symbols for each exchange
    exchange_symbols = {
        name: exchange.get_all_symbols() for name, exchange in exchanges.items()
    }

    # Initialize final mapping
    final_mapping = {name: [] for name in exchanges.keys()}

    # Map symbols to exchanges
    upbit_symbols = exchange_symbols["Upbit"]
    for symbol in upbit_symbols:
        mapped = False
        for exchange_name, symbols in exchange_symbols.items():
            if exchange_name != "Upbit" and symbol in symbols:
                final_mapping[exchange_name].append(symbol)
                mapped = True
                break
        if not mapped:
            final_mapping["Upbit"].append(symbol)

    # Save to file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    services_dir = os.path.join(root_dir, "CryptoAssetsManager")
    file_path = os.path.join(services_dir, "symbol_exchange_mapping.json")

    with open(file_path, "w") as f:
        json.dump(final_mapping, f, indent=2)

    return final_mapping


if __name__ == "__main__":
    make_symbol_exchange_mapping()
