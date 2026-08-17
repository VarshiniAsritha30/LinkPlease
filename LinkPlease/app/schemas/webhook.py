from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class UserInfo(BaseModel):
    user_id: str
    username: Optional[str] = None


class CommentData(BaseModel):
    comment_id: str
    post_id: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None
    from_user: Optional[UserInfo] = Field(None, alias="from")

    model_config = ConfigDict(populate_by_name=True)


class WebhookPayload(BaseModel):
    event_id: str
    event_type: str
    sent_at: Optional[str] = None
    data: CommentData

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "event_id": "evt_01J8ZQ4K2N7RXA",
            "event_type": "comment.created",
            "sent_at": "2026-08-10T09:14:22.481Z",
            "data": {
                "comment_id": "cmt_9f2a7c",
                "post_id": "post_44de1b",
                "text": "PRICE please 🙏",
                "created_at": "2026-08-10T09:14:21.900Z",
                "from": {
                    "user_id": "usr_3b91fe",
                    "username": "arjun.shoots"
                }
            }
        }
    })


class WebhookResponse(BaseModel):
    status: str
    message: str
    event_id: str
