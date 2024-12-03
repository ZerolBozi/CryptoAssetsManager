import os
import re
import json

import requests

def get_symbol_exchange_mapping():
    upbit = Upbit()
    binance = Binance()
    okx = OKX()
    mexc = MEXC()
    gate = Gate()

    # 获取各交易所的symbols
    upbit_symbols = upbit.get_all_symbols()
    binance_symbols = binance.get_all_symbols()
    okx_symbols = okx.get_all_symbols()
    mexc_symbols = mexc.get_all_symbols()
    gate_symbols = gate.get_all_symbols()

    # 优先级排序的交易所映射
    exchange_mapping = {
        "Binance": binance_symbols,
        "OKX": okx_symbols,
        "MEXC": mexc_symbols,
        "Gate.io": gate_symbols,
        "Upbit": upbit_symbols
    }

    # 检查Upbit的币种在其他交易所的情况
    final_mapping = {
        "Binance": [],
        "OKX": [],
        "MEXC": [],
        "Gate.io": [],
        "Upbit": []
    }

    for symbol in upbit_symbols:
        # 按优先级检查各交易所
        if symbol in binance_symbols:
            final_mapping["Binance"].append(symbol)
        elif symbol in okx_symbols:
            final_mapping["OKX"].append(symbol)
        elif symbol in mexc_symbols:
            final_mapping["MEXC"].append(symbol)
        elif symbol in gate_symbols:
            final_mapping["Gate.io"].append(symbol)
        else:
            final_mapping["Upbit"].append(symbol)

    # 保存为JSON文件
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    services_dir = os.path.join(root_dir, 'CryptoAssetsManager', 'app', 'services')
    file_path = os.path.join(services_dir, "symbol_exchange_mapping.json")

    with open(file_path, 'w') as f:
        json.dump(final_mapping, f, indent=2)

    return final_mapping

class Upbit:
    def __init__(self):
        self.base_url = "https://api.upbit.com/v1"
        self.except_symbol = 'USD'
        self.markets = []
        self.krw_markets = []

    def _get_markets(self):
        url = f"{self.base_url}/market/all?isDetails=true"
        response = requests.get(url)
        self.markets = response.json()

    def get_all_symbols(self) -> list:
        """
        get all symbols from krw market
        """
        krw_markets = self.get_krw_markets()
        symbols = [re.sub(r'KRW-', '', market) for market in krw_markets]
        return symbols

    def get_krw_markets(self) -> list:
        if not self.markets:
            self._get_markets()

        _krw_markets = [item for item in self.markets if item['market'].startswith('KRW')]
        _krw_markets = [item['market'] for item in _krw_markets if not (self.except_symbol in item['market'])]

        self.krw_markets = _krw_markets

        return self.krw_markets

    def get_btc_markets(self) -> list:
        if not self.markets:
            self._get_markets()

        _btc_markets = [item for item in self.markets if item['market'].startswith('BTC')]
        _btc_markets = [item for item in _btc_markets if not (self.except_symbol in item['market'])]

        return _btc_markets
    
    def get_day_candles(self, market: str, count: int = 200) -> list:
        """
        [{
            "market": "KRW-BTC",
            "candle_date_time_utc": "2024-12-03T00:00:00",
            "candle_date_time_kst": "2024-12-03T09:00:00",
            "opening_price": 133523000,
            "high_price": 134250000,
            "low_price": 88266000,
            "trade_price": 132090000,
            "timestamp": 1733253596351,
            "candle_acc_trade_price": 2123549244220.4966,
            "candle_acc_trade_volume": 16746.39275317,
            "prev_closing_price": 133535000,
            "change_price": -1445000,
            "change_rate": -0.010821133
        }]
        """
        url = f"{self.base_url}/candles/days?market={market}&count={count}"
        response = requests.get(url)
        return response.json()
    
    def get_week_candles(self, market: str, count: int = 200) -> list:
        """
        [{
            "market": "KRW-BTC",
            "candle_date_time_utc": "2024-12-03T00:00:00",
            "candle_date_time_kst": "2024-12-03T09:00:00",
            "opening_price": 133523000,
            "high_price": 134250000,
            "low_price": 88266000,
            "trade_price": 132090000,
            "timestamp": 1733253596351,
            "candle_acc_trade_price": 2123549244220.4966,
            "candle_acc_trade_volume": 16746.39275317,
            "first_day_of_period": "2024-12-03"
        }]
        """
        url = f"{self.base_url}/candles/weeks?market={market}&count={count}"
        response = requests.get(url)
        return response.json()
    
    def get_ticker_info(self, market: str) -> dict:
        url = f"{self.base_url}/ticker?markets={market}"
        response = requests.get(url)
        return response.json()[0]
    
    def get_current_price(self, market: str) -> float:
        return self.get_ticker_info(market)['trade_price']
    
    def get_day_amount(self, market: str) -> float:
        return self.get_ticker_info(market)['acc_trade_price_24h']
    
class Binance:
    def __init__(self):
        self.base_url = "https://api.binance.com/api/v3"
        self.markets = []
        self.usdt_markets = []
    
    def _get_markets(self):
        url = f"{self.base_url}/exchangeInfo"
        response = requests.get(url)
        self.markets = response.json()['symbols']

    def get_all_symbols(self) -> list:
        """
        get all symbols from usdt market
        """
        usdt_markets = self.get_usdt_markets()
        symbols = [re.search(r'(\w+)USDT', s).group(1) for s in usdt_markets]
        return symbols
    
    def get_usdt_markets(self) -> list:
        if not self.markets:
            self._get_markets()
        
        _usdt_markets = [item['symbol'] for item in self.markets if item['symbol'].endswith('USDT')]
        
        self.usdt_markets = _usdt_markets
        
        return self.usdt_markets
    
    def get_day_candles(self, symbol: str, limit: int = 200) -> list:
        """
        Get daily candles for a symbol
        """
        url = f"{self.base_url}/klines"
        params = {
            "symbol": symbol,
            "interval": "1d",
            "limit": limit
        }
        response = requests.get(url, params=params)
        candles = response.json()
        
        return candles
    
    def get_week_candles(self, symbol: str, limit: int = 200) -> list:
        """
        Get weekly candles for a symbol
        """
        url = f"{self.base_url}/klines"
        params = {
            "symbol": symbol,
            "interval": "1w",
            "limit": limit
        }
        response = requests.get(url, params=params)
        candles = response.json()
        
        return candles
    
class OKX:
    def __init__(self):
        self.base_url = "https://www.okx.com/api/v5"
        self.markets = []
        self.usdt_markets = []
    
    def _get_markets(self):
        url = f"{self.base_url}/public/instruments?instType=SPOT"
        response = requests.get(url)
        self.markets = response.json()
    
    def get_all_symbols(self) -> list:
        """
        get all symbols from usdt market
        """
        usdt_markets = self.get_usdt_markets()
        symbols = [re.search(r'(\w+)-USDT', s).group(1) for s in usdt_markets]
        return symbols
    
    def get_usdt_markets(self) -> list:
        if not self.markets:
            self._get_markets()
        
        _usdt_markets = [item['instId'] for item in self.markets['data'] if item["quoteCcy"] == "USDT"]
        
        self.usdt_markets = _usdt_markets
        
        return self.usdt_markets
    
    def get_day_candles(self, symbol: str, limit: int = 200) -> list:
        """
        Get daily candles for a symbol
        """
        url = f"{self.base_url}/market/candles?instId={symbol}&bar=1Dutc&limit={limit}"
        response = requests.get(url)
        candles = response.json()
        
        return candles
    
    def get_week_candles(self, symbol: str, limit: int = 200) -> list:
        """
        Get weekly candles for a symbol
        """
        url = f"{self.base_url}/market/candles?instId={symbol}&bar=1Wutc&limit={limit}"
        response = requests.get(url)
        candles = response.json()
        
        return candles
    
class MEXC:
    def __init__(self):
        self.base_url = "https://api.mexc.com/api/v3"
        self.markets = []
        self.usdt_markets = []
    
    def _get_markets(self):
        url = f"{self.base_url}/exchangeInfo"
        response = requests.get(url)
        self.markets = response.json()
    
    def get_all_symbols(self) -> list:
        """
        get all symbols from usdt market
        """
        usdt_markets = self.get_usdt_markets()
        symbols = [re.search(r'(\w+)USDT', s).group(1) for s in usdt_markets]
        return symbols
    
    def get_usdt_markets(self) -> list:
        if not self.markets:
            self._get_markets()
        
        _usdt_markets = [symbol["symbol"] for symbol in self.markets["symbols"] if symbol["quoteAsset"] == "USDT" and symbol["status"] == "1"]
        
        self.usdt_markets = _usdt_markets
        
        return self.usdt_markets
    
class Gate:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"
        self.markets = []
        self.usdt_markets = []
    
    def _get_markets(self):
        url = f"{self.base_url}/spot/currency_pairs"
        response = requests.get(url)
        self.markets = response.json()
    
    def get_all_symbols(self) -> list:
        """
        get all symbols from usdt market
        """
        usdt_markets = self.get_usdt_markets()
        symbols = [re.search(r'(\w+)_USDT', s).group(1) for s in usdt_markets]
        return symbols
    
    def get_usdt_markets(self) -> list:
        if not self.markets:
            self._get_markets()
        
        _usdt_markets = [item["id"] for item in self.markets if item["quote"] == "USDT" and item["trade_status"] == "tradable"]
        
        self.usdt_markets = _usdt_markets
        
        return self.usdt_markets
    
if __name__ == "__main__":
    get_symbol_exchange_mapping()