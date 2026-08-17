from pydantic import BaseModel, ConfigDict


class StatsResponse(BaseModel):
    sent: int
    failed: int
    queued: int
    duplicates_blocked: int

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "sent": 142,
            "failed": 3,
            "queued": 8,
            "duplicates_blocked": 57
        }
    })
