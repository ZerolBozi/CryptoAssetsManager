from pydantic import BaseModel
from typing import Dict, List, Union

class BaseDataResponse(BaseModel):
    """Base response structure for data queries"""
    status: str
    data: Union[Dict, List, None] = None

class BaseResponse(BaseDataResponse):
    """Extended response structure with message field"""
    message: str

class ExchangeStatusResponse(BaseResponse):
    """Response structure for exchange status"""
    data: Dict[str, bool]

class AssetHistoryResponse(BaseResponse):
    """Response structure for asset history"""
    data: List[Dict]