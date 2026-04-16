from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from enterprise.rag.rag_chain import RAGChain

from .message import AgentMessage, AgentResponse

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    agent_name: ClassVar[str]
    agent_description: ClassVar[str]
    capabilities: ClassVar[list[str]]

    def __init__(
        self,
        llm_callable=None,
        rag_chain: RAGChain | None = None,
        model_tier: str = "standard",
    ):
        self.llm_callable = llm_callable
        self.rag_chain = rag_chain
        self.model_tier = model_tier

    @abstractmethod
    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        raise NotImplementedError

    def can_handle(self, message_type: str) -> bool:
        return message_type in self.capabilities

    async def _build_rag_context(
        self,
        query: str,
        filter_metadata: dict[str, Any] | None = None,
        max_context_tokens: int = 1000,
    ) -> str:
        if not self.rag_chain:
            return ""
        try:
            rag_context = await self.rag_chain.build_augmented_context(
                query=query,
                filter_metadata=filter_metadata,
                max_context_tokens=max_context_tokens,
            )
            return rag_context.augmented_text
        except Exception as exc:
            logger.warning("Agent RAG lookup failed", agent=self.agent_name, error=str(exc))
            return ""
