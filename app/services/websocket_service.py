import asyncio
from typing import Dict, Set, Optional

import ccxt.pro as ccxtpro
from fastapi import WebSocket


class WebSocketService:
    def __init__(self):
        # self.subscriptions[data_type][exchange][symbol] = set(websockets)
        self.subscriptions: Dict[str, Dict[str, Dict[str, Set[WebSocket]]]] ={
            'ticker': {},
            'ohlcv': {},
            'aggTrade': {}
        }
        self.exchanges_config = {
            "binance": ccxtpro.binance,
            "okx": ccxtpro.okx,
            "bybit": ccxtpro.bybit,
            "bitget": ccxtpro.bitget,
            "mexc": ccxtpro.mexc,
            "gateio": ccxtpro.gateio,
            "bitopro": ccxtpro.bitopro
        }
        self.exchanges: Dict[str, ccxtpro.Exchange] = {}
        self.tasks = set()

    def get_exchange(self, exchange_name: str) -> Optional[ccxtpro.Exchange]:
        if exchange_name not in self.exchanges:
            if exchange_name in self.exchanges_config:
                self.exchanges[exchange_name] = self.exchanges_config[exchange_name]()
            else:
                return None
        return self.exchanges[exchange_name]

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    async def disconnect(self, websocket: WebSocket):
        for data_type in self.subscriptions:
            for exchange_id in list(self.subscriptions[data_type].keys()):
                for symbol in list(self.subscriptions[data_type][exchange_id].keys()):
                    if websocket in self.subscriptions[data_type][exchange_id][symbol]:
                        await self.unsubscribe(exchange_id, symbol, websocket, data_type)

    async def subscribe(
            self, 
            exchange_name: str, 
            symbol: str, 
            websocket: WebSocket, 
            data_type: str, 
            timeframe: str = '1m'
        ) -> str:

        if data_type not in ['ticker', 'ohlcv', 'aggTrade']:
            raise ValueError("Invalid data_type. Must be 'ticker', 'ohlcv' or 'aggTrade'")
        
        exchange = self.get_exchange(exchange_name)
        if not exchange:
            raise ValueError(f"Unsupported exchange: {exchange_name}")
        
        if exchange_name not in self.subscriptions[data_type]:
            self.subscriptions[data_type][exchange_name] = {}

        if symbol not in self.subscriptions[data_type][exchange_name]:
            self.subscriptions[data_type][exchange_name][symbol] = set()
            
            if data_type == 'ticker':
                task = asyncio.create_task(self.ticker_loop(exchange_name, symbol))
            elif data_type == 'ohlcv':
                task = asyncio.create_task(self.ohlcv_loop(exchange_name, symbol, timeframe))
            elif data_type == 'aggTrade':
                task = asyncio.create_task(self.aggTrade_loop(exchange_name, symbol))
            
            task.set_name(f"{exchange_name}_{data_type}_{symbol}_{timeframe if data_type == 'ohlcv' else ''}")
            self.tasks.add(task)
        
        self.subscriptions[data_type][exchange_name][symbol].add(websocket)
        return f"/ws/{exchange_name}/{data_type}/{symbol}"
    
    async def unsubscribe(
            self, 
            exchange_name: str,
            symbol: str, 
            websocket: WebSocket, 
            data_type: str = 'ticker'
        ) -> None:
        if (exchange_name in self.subscriptions[data_type] and 
            symbol in self.subscriptions[data_type][exchange_name]):
            
            self.subscriptions[data_type][exchange_name][symbol].remove(websocket)
            
            if not self.subscriptions[data_type][exchange_name][symbol]:
                del self.subscriptions[data_type][exchange_name][symbol]
                
                if not self.subscriptions[data_type][exchange_name]:
                    del self.subscriptions[data_type][exchange_name]
                
                for task in self.tasks:
                    if task.get_name().startswith(f"{exchange_name}_{data_type}_{symbol}"):
                        task.cancel()
                        self.tasks.remove(task)
                        break

    async def ticker_loop(self, exchange_name: str, symbol: str):
        exchange = self.get_exchange(exchange_name)
        try:
            while True:
                if (exchange_name not in self.subscriptions['ticker'] or 
                    symbol not in self.subscriptions['ticker'][exchange_name]):
                    break
                    
                ticker = await exchange.watch_ticker(symbol)
                message = {
                    "type": "ticker",
                    "exchange": exchange_name,
                    "symbol": symbol,
                    "bid": ticker['bid'],
                    "ask": ticker['ask'],
                    "last": ticker['last'],
                    "timestamp": ticker['timestamp']
                }
                
                websockets = self.subscriptions['ticker'][exchange_name][symbol].copy()
                for websocket in websockets:
                    try:
                        await websocket.send_json(message)
                    except Exception:
                        await self.unsubscribe(exchange_name, symbol, websocket, 'ticker')
                        
        except Exception as e:
            print(f"Error in {exchange_name} ticker loop for {symbol}: {str(e)}")
        finally:
            if (exchange_name in self.subscriptions['ticker'] and 
                symbol in self.subscriptions['ticker'][exchange_name]):
                del self.subscriptions['ticker'][exchange_name][symbol]

    async def ohlcv_loop(self, exchange_name: str, symbol: str, timeframe: str):
        exchange = self.get_exchange(exchange_name)
        try:
            while True:
                if (exchange_name not in self.subscriptions['ohlcv'] or 
                    symbol not in self.subscriptions['ohlcv'][exchange_name]):
                    break
                    
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe)
                if ohlcv:
                    last_candle = ohlcv[-1]
                    message = {
                        "type": "ohlcv",
                        "exchange": exchange_name,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "timestamp": last_candle[0],
                        "open": last_candle[1],
                        "high": last_candle[2],
                        "low": last_candle[3],
                        "close": last_candle[4],
                        "volume": last_candle[5]
                    }
                    
                    websockets = self.subscriptions['ohlcv'][exchange_name][symbol].copy()
                    for websocket in websockets:
                        try:
                            await websocket.send_json(message)
                        except Exception:
                            await self.unsubscribe(exchange_name, symbol, websocket, 'ohlcv')
                        
        except Exception as e:
            print(f"Error in {exchange_name} ohlcv loop for {symbol}: {str(e)}")
        finally:
            if (exchange_name in self.subscriptions['ohlcv'] and 
                symbol in self.subscriptions['ohlcv'][exchange_name]):
                del self.subscriptions['ohlcv'][exchange_name][symbol]

    async def aggTrade_loop(self, exchange_name: str, symbol: str):
        exchange = self.get_exchange(exchange_name)
        try:
            while True:
                if (exchange_name not in self.subscriptions['aggTrade'] or 
                    symbol not in self.subscriptions['aggTrade'][exchange_name]):
                    break
                    
                trades = await exchange.watch_trades(symbol)
                if trades and len(trades) > 0:
                    latest_trade = trades[-1]
                    message = {
                        "type": "aggTrade",
                        "exchange": exchange_name,
                        "symbol": symbol,
                        "price": float(latest_trade['price']),
                        "quantity": float(latest_trade['amount']),
                        "timestamp": latest_trade['timestamp']
                    }
                    
                    websockets_to_remove = set()
                    websockets = self.subscriptions['aggTrade'][exchange_name][symbol].copy()
                    for websocket in websockets:
                        try:
                            await websocket.send_json(message)
                        except Exception as e:
                            print(f"Error sending message to client: {str(e)}")
                            websockets_to_remove.add(websocket)
                    
                    for ws in websockets_to_remove:
                        await self.unsubscribe(exchange_name, symbol, ws, 'aggTrade')
                        
        except Exception as e:
            print(f"Error in {exchange_name} aggTrade loop for {symbol}: {str(e)}")
        finally:
            if (exchange_name in self.subscriptions['aggTrade'] and 
                symbol in self.subscriptions['aggTrade'][exchange_name]):
                del self.subscriptions['aggTrade'][exchange_name][symbol]

    async def close(self):
        for exchange_id, exchange in self.exchanges.items():
            try:
                await exchange.close()
            except Exception as e:
                print(f"Error closing {exchange_id} exchange: {e}")
        self.exchanges.clear()