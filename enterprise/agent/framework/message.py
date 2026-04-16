from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    type: str = Field(description="Message type used for routing")
    sender: str = Field(description="Sender agent name")
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:8]}")


class AgentResponse(BaseModel):
    message_id: str
    agent_name: str
    success: bool = True
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    next_messages: list[AgentMessage] = Field(default_factory=list)
