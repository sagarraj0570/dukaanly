"""
Pydantic v2 schemas for the Dukaanly AI subsystem.
"""

import enum
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ChatRole(str, enum.Enum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    name: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LLMCompletionRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1)
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4096)
    response_format: Optional[Dict[str, Any]] = None
    stop: Optional[List[str]] = None
    user_id: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class LLMCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"ai-{uuid.uuid4().hex[:12]}")
    model: str
    provider: str
    text: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    finish_reason: str = "stop"

    model_config = ConfigDict(extra="ignore")


class AIStatusResponse(BaseModel):
    enabled: bool
    provider: str
    model: str
    features: Dict[str, bool]
    circuit_breaker_open: bool = False
    details: Optional[str] = None
    api_key_configured: bool = False
    active_endpoint: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class AIConnectionTestResponse(BaseModel):
    provider: str
    model: str
    api_key_configured: bool
    connection_successful: bool
    latency_ms: float = 0.0
    error_category: Optional[str] = None
    circuit_breaker_open: bool = False
    cached: bool = False

    model_config = ConfigDict(extra="ignore")

