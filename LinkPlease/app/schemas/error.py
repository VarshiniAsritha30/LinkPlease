"""Structured error response schema for consistent API error formatting."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response body returned by all API exception handlers."""

    detail: str
    code: str = "error"

    model_config = {"json_schema_extra": {"example": {"detail": "Job not found", "code": "not_found"}}}
