from typing import Optional
from datetime import datetime, timedelta

import aiohttp


class CurrencyService:
    def __init__(self):
        self.cache = None
        self.last_update = None
        self.cache_duration = timedelta(minutes=5)
        self.api_url = (
            "https://max-api.maicoin.com/api/v3/trades?market=usdttwd&limit=1"
        )

    async def get_usdt_twd_rate(self) -> Optional[float]:
        """Get USDT to TWD exchange rate from MAX Exchange"""
        if self._should_update_cache():
            await self._update_cache()
        return self.cache

    def _should_update_cache(self) -> bool:
        if self.cache is None or self.last_update is None:
            return True
        return datetime.now() - self.last_update > self.cache_duration

    async def _update_cache(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and isinstance(data, list) and len(data) > 0:
                            self.cache = float(data[0]["price"])
                            self.last_update = datetime.now()
        except Exception as e:
            print(f"Error updating MAX exchange rate: {str(e)}")
