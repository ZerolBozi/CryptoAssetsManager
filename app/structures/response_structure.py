from pydantic import BaseModel
from typing import Dict, List, Union

class BaseDataResponse(BaseModel):
    status: str
    data: Union[Dict, List, None] = None

class BaseResponse(BaseModel):
    status: str
    message: str = ""