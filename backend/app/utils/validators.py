"""
Input validation models using Pydantic.
Prevents invalid data from reaching the application.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re


class PageViewRequest(BaseModel):
    """Validation for page view tracking requests."""
    visitor_id: str = Field(..., min_length=1, max_length=100)
    page: str = Field(..., min_length=1, max_length=200)
    referrer: Optional[str] = Field(None, max_length=500)
    user_agent: Optional[str] = Field(None, max_length=500)

    @field_validator('visitor_id')
    @classmethod
    def validate_visitor_id(cls, v):
        """Only allow alphanumeric characters and hyphens."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Invalid visitor_id format - only alphanumeric, underscore, and hyphen allowed')
        return v

    @field_validator('page')
    @classmethod
    def validate_page(cls, v):
        """Only allow valid URL path characters."""
        if not re.match(r'^[a-zA-Z0-9/_.-]+$', v):
            raise ValueError('Invalid page format - only URL-safe characters allowed')
        return v


class ChatMessageRequest(BaseModel):
    """Validation for chat message requests."""
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = Field(None, max_length=100)

    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        """Ensure message is not just whitespace."""
        if not v.strip():
            raise ValueError('Message cannot be empty or just whitespace')
        return v.strip()

    @field_validator('conversation_id')
    @classmethod
    def validate_conversation_id(cls, v):
        """Validate conversation ID format if provided."""
        if v is not None and not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Invalid conversation_id format')
        return v


class AnalyticsSummaryRequest(BaseModel):
    """Validation for analytics summary query parameters."""
    days: int = Field(default=30, ge=1, le=365)
