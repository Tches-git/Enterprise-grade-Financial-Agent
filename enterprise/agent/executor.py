"""ExecutorAgent: executes individual sub-tasks from a plan.

Reuses Skyvern's perception-action loop at the sub-task granularity.
Each sub-task execution returns a structured result to the coordinator.
"""

import logging
import time
from datetime import datetime
from typing import Any

from enterprise.agent.framework.base_agent import BaseAgent
from enterprise.agent.framework.message import AgentMessage, AgentResponse

from .schemas import ExecutionResult, SubTask, SubTaskStatus

logger = logging.getLogger(__name__)


class ExecutorAgent(BaseAgent):
    """Executes sub-tasks from PlannerAgent plans."""

    agent_name = "executor"
    agent_description = "Executes subtasks and reports structured browser-action results"
    capabilities = ["execute_subtask"]

    def __init__(self, action_handler=None):
        super().__init__(model_tier="none")
        self.action_handler = action_handler

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        try:
            subtask_payload = message.payload.get("subtask")
            if subtask_payload:
                subtask = SubTask.model_validate(subtask_payload)
            else:
                subtask = SubTask(
                    index=int(message.payload.get("index", 0)),
                    goal=str(message.payload.get("subtask_goal") or message.payload.get("goal") or "Execute task"),
                    completion_condition=str(message.payload.get("completion_condition") or "Task completed"),
                    max_retries=int(message.payload.get("max_retries", 2)),
                )
            result = await self.execute_subtask(subtask, message.context)
            return AgentResponse(
                message_id=message.message_id,
                agent_name=self.agent_name,
                success=result.success,
                result={"execution_result": result.model_dump(), "execution_result_model": result},
                error=result.error_message,
            )
        except Exception as exc:
            return AgentResponse(
                message_id=message.message_id,
                agent_name=self.agent_name,
                success=False,
                error=str(exc),
            )

    async def execute_subtask(
        self,
        subtask: SubTask,
        context: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        subtask.status = SubTaskStatus.RUNNING
        subtask.started_at = datetime.utcnow()

        start = time.monotonic()
        last_error = None

        for attempt in range(subtask.max_retries + 1):
            try:
                if self.action_handler:
                    handler_result = await self.action_handler(
                        subtask.goal, context or {},
                    )
                else:
                    handler_result = self._simulate_execution(subtask)

                elapsed = int((time.monotonic() - start) * 1000)

                if handler_result.get("success", False):
                    subtask.status = SubTaskStatus.COMPLETED
                    subtask.completed_at = datetime.utcnow()
                    subtask.result_data = handler_result.get("data")

                    logger.info(
                        "ExecutorAgent: subtask %s completed in %dms (attempt %d)",
                        subtask.subtask_id, elapsed, attempt + 1,
                    )
                    return ExecutionResult(
                        subtask_id=subtask.subtask_id,
                        success=True,
                        result_data=handler_result.get("data"),
                        screenshot_key=handler_result.get("screenshot_key"),
                        page_url=handler_result.get("page_url"),
                        duration_ms=elapsed,
                    )

                last_error = handler_result.get("error", "Unknown error")
                logger.warning(
                    "ExecutorAgent: subtask %s attempt %d failed: %s",
                    subtask.subtask_id, attempt + 1, last_error,
                )

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "ExecutorAgent: subtask %s attempt %d exception: %s",
                    subtask.subtask_id, attempt + 1, exc,
                )

            if attempt < subtask.max_retries:
                logger.info(
                    "ExecutorAgent: retrying subtask %s (%d/%d)",
                    subtask.subtask_id, attempt + 2, subtask.max_retries + 1,
                )

        elapsed = int((time.monotonic() - start) * 1000)
        subtask.status = SubTaskStatus.FAILED
        subtask.completed_at = datetime.utcnow()
        subtask.error_message = last_error

        logger.error(
            "ExecutorAgent: subtask %s failed after %d attempts: %s",
            subtask.subtask_id, subtask.max_retries + 1, last_error,
        )
        return ExecutionResult(
            subtask_id=subtask.subtask_id,
            success=False,
            error_message=last_error,
            duration_ms=elapsed,
        )

    def _simulate_execution(self, subtask: SubTask) -> dict:
        return {
            "success": True,
            "data": {"goal": subtask.goal, "simulated": True},
        }
