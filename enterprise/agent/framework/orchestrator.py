from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from .message import AgentMessage
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


class PipelineStage(BaseModel):
    message_type: str
    required: bool = True
    condition: str | None = None


FINANCIAL_TASK_PIPELINE = [
    PipelineStage(message_type="plan_request", required=True),
    PipelineStage(message_type="risk_check", required=True),
    PipelineStage(message_type="approval_request", required=True, condition="approval_required == True"),
    PipelineStage(message_type="review_result", required=False),
    PipelineStage(message_type="record_experience", required=False),
]


class TaskOrchestrator:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    async def run(self, initial_message: AgentMessage, pipeline: list[PipelineStage] | None = None) -> dict[str, Any]:
        pipeline = pipeline or FINANCIAL_TASK_PIPELINE
        trace_id = initial_message.trace_id
        context = dict(initial_message.context)
        context.update(initial_message.payload)
        results: list[dict[str, Any]] = []

        for stage in pipeline:
            if stage.condition and not self._eval_condition(stage.condition, context):
                logger.info("Skipping stage %s (condition not met)", stage.message_type)
                continue

            agents = self.registry.find_by_capability(stage.message_type)
            if not agents:
                if stage.required:
                    return {"success": False, "error": f"No agent for {stage.message_type}", "results": results, "context": context}
                continue

            agent = agents[0]
            message = AgentMessage(
                type=stage.message_type,
                sender="orchestrator",
                payload=context,
                context=context,
                trace_id=trace_id,
            )

            start = time.monotonic()
            response = await agent.handle_message(message)
            elapsed = int((time.monotonic() - start) * 1000)
            results.append(
                {
                    "stage": stage.message_type,
                    "agent": agent.agent_name,
                    "success": response.success,
                    "duration_ms": elapsed,
                }
            )

            if not response.success and stage.required:
                return {
                    "success": False,
                    "error": f"Stage {stage.message_type} failed: {response.error}",
                    "results": results,
                    "context": context,
                }

            context.update(response.result)
            for next_msg in response.next_messages:
                next_msg.trace_id = trace_id
                next_agents = self.registry.find_by_capability(next_msg.type)
                for next_agent in next_agents:
                    await next_agent.handle_message(next_msg)

        return {"success": True, "context": context, "results": results}

    @staticmethod
    def _eval_condition(expression: str, context: dict[str, Any]) -> bool:
        try:
            return bool(eval(expression, {"__builtins__": {}}, context))
        except Exception:
            return False
