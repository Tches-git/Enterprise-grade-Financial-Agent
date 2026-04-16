from __future__ import annotations

from datetime import datetime
from typing import Any

from enterprise.approval.models import ApprovalStatus
from enterprise.approval.routing import route_approval
from enterprise.approval.routes import _approval_store

from .base_agent import BaseAgent
from .message import AgentMessage, AgentResponse


class ApprovalAgent(BaseAgent):
    agent_name = "approval"
    agent_description = "Creates approval requests for high-risk operations and simulates gating decisions"
    capabilities = ["approval_request"]

    def __init__(self):
        super().__init__(model_tier="none")

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        payload = message.payload
        risk_level = str(payload.get("risk_level", "low"))
        source_department_id = str(payload.get("department_id") or payload.get("source_department_id") or "dept_it")
        route = route_approval(risk_level, source_department_id)

        if not route.requires_approval:
            return AgentResponse(
                message_id=message.message_id,
                agent_name=self.agent_name,
                success=True,
                result={"approval_required": False, "approval_status": "not_required"},
            )

        approval_id = f"apr_framework_{message.trace_id}_{len(_approval_store) + 1}"
        approval_record: dict[str, Any] = {
            "approval_id": approval_id,
            "task_id": payload.get("task_id", message.context.get("task_id", "task_unknown")),
            "organization_id": payload.get("org_id", message.context.get("org_id", "org_unknown")),
            "department_id": source_department_id,
            "business_line_id": payload.get("business_line_id"),
            "risk_level": risk_level,
            "risk_reason": payload.get("risk_reason", "High-risk operation detected"),
            "operation_description": payload.get("operation_description") or payload.get("goal") or payload.get("text"),
            "screenshot_path": None,
            "approver_department_id": route.approver_department_id or source_department_id,
            "status": ApprovalStatus.APPROVED.value,
            "requested_at": datetime.utcnow().isoformat(),
            "timeout_seconds": 3600 if risk_level == "high" else 1800,
            "approver_user_id": "framework_auto_approver",
            "decided_at": datetime.utcnow().isoformat(),
            "decision_note": "Auto-approved in local framework mode",
        }
        _approval_store[approval_id] = approval_record

        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=True,
            result={
                "approval_required": True,
                "approval_status": ApprovalStatus.APPROVED.value,
                "approval_id": approval_id,
                "approval_route": route.description,
            },
        )
