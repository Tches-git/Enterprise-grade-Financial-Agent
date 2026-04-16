from __future__ import annotations

from datetime import datetime

from enterprise.rag.schemas import DocumentChunk

from .base_agent import BaseAgent
from .message import AgentMessage, AgentResponse


class ExperienceAgent(BaseAgent):
    agent_name = "experience"
    agent_description = "Records execution experiences to vector store for future retrieval"
    capabilities = ["record_experience"]

    def __init__(self, vector_store=None, embedder=None):
        super().__init__(model_tier="none")
        self.vector_store = vector_store
        self.embedder = embedder

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        if not self.vector_store or not self.embedder:
            return AgentResponse(
                message_id=message.message_id,
                agent_name=self.agent_name,
                success=False,
                error="Experience store is not configured",
            )

        payload = message.payload
        summary = (
            f"Navigation goal: {payload.get('navigation_goal', '')}\n"
            f"Subtask goal: {payload.get('subtask_goal', '')}\n"
            f"Success: {payload.get('success', False)}\n"
            f"Duration: {payload.get('duration_ms', 0)}ms\n"
            f"Result: {payload.get('result_data')}\n"
            f"Error: {payload.get('error_message')}"
        )
        chunk = DocumentChunk(
            chunk_id=f"exp_{message.message_id}",
            content=summary,
            metadata={
                "source_file": f"experience_{payload.get('org_id', 'unknown')}.md",
                "type": "workflow_example",
                "created_at": datetime.utcnow().isoformat(),
                "success": payload.get("success", False),
            },
            token_count=max(1, len(summary) // 4),
        )
        embeddings = await self.embedder.embed_texts([chunk.content])
        self.vector_store.add_chunks([chunk], embeddings)
        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=True,
            result={"experience_recorded": True, "chunk_id": chunk.chunk_id},
        )
