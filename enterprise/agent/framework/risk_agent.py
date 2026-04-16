from __future__ import annotations

from enterprise.approval.risk_detector import detect_risk
from enterprise.approval.routing import route_approval

from .base_agent import BaseAgent
from .message import AgentMessage, AgentResponse


class RiskAgent(BaseAgent):
    agent_name = "risk"
    agent_description = "Evaluates financial operation risk with RAG-backed compliance context"
    capabilities = ["risk_check"]

    def __init__(self, llm_callable=None, rag_chain=None):
        super().__init__(llm_callable=llm_callable, rag_chain=rag_chain, model_tier="standard")

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        text = str(message.payload.get("text") or message.payload.get("goal") or "")
        page_context = message.payload.get("page_context")
        department_id = str(message.payload.get("department_id") or message.context.get("department_id") or "dept_it")
        assessment = await detect_risk(
            text=text,
            page_context=page_context,
            llm_callable=self.llm_callable,
            rag_chain=self.rag_chain,
        )
        route = route_approval(assessment.risk_level, department_id)
        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=True,
            result={
                "risk_level": assessment.risk_level,
                "risk_reason": assessment.reason,
                "matched_keywords": assessment.matched_keywords,
                "approval_required": route.requires_approval,
                "approver_department_id": route.approver_department_id,
                "approval_route": route.description,
            },
        )
