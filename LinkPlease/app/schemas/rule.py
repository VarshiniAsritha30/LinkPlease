from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RuleCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100, description="Keyword to match in comments")
    dm_message: str = Field(..., min_length=1, max_length=2000, description="Message to send via DM")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "keyword": "PRICE",
            "dm_message": "Here's the price list: https://example.com/pricing"
        }
    })


class RuleResponse(BaseModel):
    rule_id: str
    keyword: str
    dm_message: str
    active: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
