import os
import json
import asyncio
from typing import Dict, Set

import ccxt.pro as ccxtpro
from fastapi import WebSocket

class WebSocketService:
    def __init__(self):
        self.exchanges: Dict[str, ccxtpro.Exchange] = {}
        self.subscriptions: Dict[str, Set[str]] = {}
        self.clients: Set[WebSocket] = set()
        self.is_running = False
        self.tasks = []
        self.mapping_data = []

    async def initialize(self):
        """Initialize exchanges and subscriptions"""
        # Read mapping file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(os.path.dirname(current_dir))
        file_path = os.path.join(root_dir, 'app', 'services', 'symbol_exchange_mapping.json')
        
        # Read JSON mapping file
        with open(file_path, 'r') as f:
            self.mapping_data = json.load(f)
            
        self._prepare_subscriptions()
        
        # Initialize exchanges
        exchange_classes = {
            'Binance': ccxtpro.binance,
            'OKX': ccxtpro.okx,
            'MEXC': ccxtpro.mexc,
            'Gate.io': ccxtpro.gateio
        }
        
        # Initialize each exchange with credentials
        for exchange_name, exchange_class in exchange_classes.items():
            if exchange_name in self.mapping_data and self.mapping_data[exchange_name]:  # Check if exchange has symbols
                self.exchanges[exchange_name] = exchange_class({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot'
                    }
                })

    def _prepare_subscriptions(self):
        """Prepare subscription data from JSON"""
        for exchange, symbols in self.mapping_data.items():
            if exchange != 'Upbit':  # Skip Upbit
                self.subscriptions[exchange] = {f"{symbol}/USDT" for symbol in symbols}

    async def start_watching(self):
        """Start watching all subscribed symbols"""
        self.is_running = True
        
        for exchange_name, symbols in self.subscriptions.items():
            exchange = self.exchanges.get(exchange_name)
            if exchange:
                for symbol in symbols:
                    self.tasks.append(
                        asyncio.create_task(
                            self._watch_ohlcv(exchange_name, exchange, symbol)
                        )
                    )

    async def _watch_ohlcv(self, exchange_name: str, exchange: ccxtpro.Exchange, symbol: str):
        """Watch OHLCV data for a symbol"""
        while self.is_running:
            try:
                ohlcv = await exchange.watch_ohlcv(symbol, '1d')
                if ohlcv and self.clients:
                    # Format the data
                    latest_candle = ohlcv[-1]
                    message = {
                        'exchange': exchange_name,
                        'symbol': symbol.split('/')[0],
                        'timestamp': latest_candle[0],
                        'open': latest_candle[1],
                        'high': latest_candle[2],
                        'low': latest_candle[3],
                        'close': latest_candle[4],
                        'volume': latest_candle[5]
                    }
                    
                    # Broadcast to all clients
                    await self.broadcast(message)
                    
            except Exception as e:
                print(f"Error watching {symbol} on {exchange_name}: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying

    async def register_client(self, websocket: WebSocket):
        """Register a new WebSocket client"""
        await websocket.accept()
        self.clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()  # Keep connection alive
        except Exception as e:
            print(f"Client connection error: {str(e)}")
        finally:
            self.clients.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.clients:
            return
            
        for client in self.clients.copy():  # Use copy to avoid modification during iteration
            try:
                await client.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to client: {str(e)}")
                self.clients.remove(client)

    async def stop(self):
        """Stop the WebSocket service"""
        self.is_running = False
        
        # Cancel all watching tasks
        for task in self.tasks:
            task.cancel()
        
        # Close all exchange connections
        for exchange in self.exchanges.values():
            await exchange.close()
            
        # Clear all sets
        self.exchanges.clear()
        self.clients.clear()
        self.tasks.clear()