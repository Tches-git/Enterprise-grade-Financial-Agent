"""PlannerAgent: decomposes navigation goals into ordered sub-task plans.

Receives a high-level navigation goal and current task context, then
produces a structured TaskPlan with ordered SubTasks. Each sub-task
has a clear goal, completion condition, and failure strategy.

On failure reports from ExecutorAgent, the Planner can generate a
revised plan (replan) for the remaining steps.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from enterprise.agent.framework.base_agent import BaseAgent
from enterprise.agent.framework.message import AgentMessage, AgentResponse
from enterprise.rag.rag_chain import RAGChain

from .schemas import FailureStrategy, FunctionCallPlan, SubTask, TaskPlan

logger = logging.getLogger(__name__)


class PlannerOutput(BaseModel):
    """Schema for LLM-generated plan output."""

    reasoning: str | None = Field(default=None, description="Brief rationale for the plan")
    steps: list[dict[str, Any]] = Field(description="Ordered list of sub-tasks")


PLANNER_SYSTEM_PROMPT = """\
You are a senior financial RPA planning agent.
Your job is to decompose a navigation goal into a sequence of concrete sub-tasks that a browser automation executor can perform step by step.

## Planning principles
1. Think about prerequisite authentication, navigation, data validation, and final confirmation.
2. Prefer plans that are auditable, low-risk, and robust to UI changes.
3. If the goal involves regulated workflows, include explicit review or verification steps.
4. If a step obviously maps to a reusable capability, emit a `function_call` object.

Each sub-task must have:
- "goal": a clear, actionable description of what to do
- "completion_condition": how to verify success
- "failure_strategy": one of "retry", "skip", "abort", "replan"
- "max_retries": integer
- optional "function_call": {"name": string, "arguments": object}

Output ONLY a JSON object with "reasoning" and "steps" fields. No other text.
"""

REPLAN_SYSTEM_PROMPT = """\
You are a senior financial RPA replanning agent.
A previous execution plan failed. You are given the original goal, the steps already completed, the failed step, and the latest context.

## Replanning rules
1. Generate ONLY the remaining steps.
2. Do NOT repeat completed steps.
3. If the failure suggests the path is blocked, choose a different navigation strategy.
4. Return a JSON object with "reasoning" and "steps".
"""


class PlannerAgent(BaseAgent):
    """Decomposes navigation goals into sub-task plans."""

    agent_name = "planner"
    agent_description = "Creates and revises structured browser automation plans"
    capabilities = ["plan_request", "replan_request"]

    def __init__(self, llm_callable=None, rag_chain: RAGChain | None = None):
        super().__init__(llm_callable=llm_callable, rag_chain=rag_chain, model_tier="standard")

    async def create_plan(
        self,
        navigation_goal: str,
        context: dict[str, Any] | None = None,
    ) -> TaskPlan:
        if self.llm_callable:
            return await self._plan_with_llm(navigation_goal, context)
        return self._create_fallback_plan(navigation_goal)

    async def replan(
        self,
        original_goal: str,
        completed_subtasks: list[SubTask],
        failed_subtask: SubTask,
        failure_reason: str,
        context: dict[str, Any] | None = None,
    ) -> TaskPlan:
        if self.llm_callable:
            return await self._replan_with_llm(
                original_goal, completed_subtasks, failed_subtask, failure_reason, context,
            )

        return TaskPlan(
            navigation_goal=original_goal,
            reasoning="Fallback continuation plan after replanning failure.",
            subtasks=[
                SubTask(
                    index=0,
                    goal=f"Continue after failure: {original_goal}",
                    completion_condition="Task goal achieved",
                    failure_strategy=FailureStrategy.ABORT,
                ),
            ],
            is_replan=True,
            replan_reason=failure_reason,
            version=len(completed_subtasks) + 2,
        )

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        try:
            if message.type == "plan_request":
                goal = str(message.payload.get("navigation_goal") or message.payload.get("goal") or "")
                plan = await self.create_plan(goal, message.context)
                return AgentResponse(
                    message_id=message.message_id,
                    agent_name=self.agent_name,
                    success=True,
                    result={"task_plan": plan.model_dump(), "task_plan_model": plan},
                )

            if message.type == "replan_request":
                failed_subtask_payload = message.payload.get("failed_subtask", {})
                completed_subtasks_payload = message.payload.get("completed_subtasks", [])
                plan = await self.replan(
                    original_goal=str(message.payload.get("navigation_goal") or ""),
                    completed_subtasks=[SubTask.model_validate(item) for item in completed_subtasks_payload],
                    failed_subtask=SubTask.model_validate(failed_subtask_payload),
                    failure_reason=str(message.payload.get("failure_reason") or "Unknown error"),
                    context=message.context,
                )
                return AgentResponse(
                    message_id=message.message_id,
                    agent_name=self.agent_name,
                    success=True,
                    result={"task_plan": plan.model_dump(), "task_plan_model": plan},
                )
        except Exception as exc:
            return AgentResponse(
                message_id=message.message_id,
                agent_name=self.agent_name,
                success=False,
                error=str(exc),
            )

        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=False,
            error=f"Unsupported message type: {message.type}",
        )

    async def _plan_with_llm(
        self,
        navigation_goal: str,
        context: dict[str, Any] | None,
    ) -> TaskPlan:
        ctx_str = json.dumps(context) if context else "No additional context."
        examples_section = await self._build_examples_section(
            query=navigation_goal,
            filter_metadata={"type": "workflow_example"},
            heading="Reference successful plans",
        )
        prompt = (
            f"{PLANNER_SYSTEM_PROMPT}\n\n"
            f"## Navigation Goal\n{navigation_goal}\n\n"
            f"## Context\n{ctx_str}\n"
            f"{examples_section}"
        )

        try:
            raw = await self.llm_callable(prompt)
            data = self._load_llm_json(raw)
            return self._build_task_plan(navigation_goal, data)
        except Exception as exc:
            logger.warning("PlannerAgent: LLM planning failed (%s), using fallback", exc)
            return self._create_fallback_plan(navigation_goal)

    async def _replan_with_llm(
        self,
        original_goal: str,
        completed_subtasks: list[SubTask],
        failed_subtask: SubTask,
        failure_reason: str,
        context: dict[str, Any] | None,
    ) -> TaskPlan:
        completed_summary = "\n".join(
            f"- Step {subtask.index}: {subtask.goal} [COMPLETED]"
            for subtask in completed_subtasks
        )
        examples_section = await self._build_examples_section(
            query=f"{original_goal} {failure_reason}",
            filter_metadata={"type": "workflow_example"},
            heading="Reference fallback patterns",
        )
        prompt = (
            f"{REPLAN_SYSTEM_PROMPT}\n\n"
            f"## Original Goal\n{original_goal}\n\n"
            f"## Completed Steps\n{completed_summary or 'None'}\n\n"
            f"## Failed Step\nStep {failed_subtask.index}: {failed_subtask.goal}\n"
            f"Failure reason: {failure_reason}\n\n"
            f"## Context\n{json.dumps(context) if context else 'None'}\n"
            f"{examples_section}"
        )

        try:
            raw = await self.llm_callable(prompt)
            data = self._load_llm_json(raw)
            return self._build_task_plan(
                original_goal,
                data,
                is_replan=True,
                replan_reason=failure_reason,
                index_offset=len(completed_subtasks),
                version=len(completed_subtasks) + 2,
            )
        except Exception as exc:
            logger.warning("PlannerAgent: LLM replan failed (%s), using fallback", exc)
            return TaskPlan(
                navigation_goal=original_goal,
                reasoning="Fallback continuation plan after replanning failure.",
                subtasks=[
                    SubTask(
                        index=len(completed_subtasks),
                        goal=f"Continue after failure: {original_goal}",
                        completion_condition="Task goal achieved",
                        failure_strategy=FailureStrategy.ABORT,
                    ),
                ],
                is_replan=True,
                replan_reason=failure_reason,
                version=len(completed_subtasks) + 2,
            )

    async def _build_examples_section(
        self,
        query: str,
        filter_metadata: dict[str, Any],
        heading: str,
    ) -> str:
        if not self.rag_chain:
            return ""
        rag_context = await self.rag_chain.build_augmented_context(
            query=query,
            filter_metadata=filter_metadata,
            max_context_tokens=1000,
        )
        if not rag_context.augmented_text:
            return ""
        return f"\n\n## {heading}\n{rag_context.augmented_text}\n"

    def _build_task_plan(
        self,
        navigation_goal: str,
        data: dict[str, Any],
        *,
        is_replan: bool = False,
        replan_reason: str | None = None,
        index_offset: int = 0,
        version: int = 1,
    ) -> TaskPlan:
        subtasks: list[SubTask] = []
        for i, step in enumerate(data.get("steps", [])):
            function_call = step.get("function_call")
            subtasks.append(
                SubTask(
                    index=index_offset + i,
                    goal=step.get("goal", f"Step {i + 1}"),
                    completion_condition=step.get("completion_condition", ""),
                    max_retries=step.get("max_retries", 2),
                    failure_strategy=FailureStrategy(step.get("failure_strategy", "replan")),
                    function_call=FunctionCallPlan.model_validate(function_call) if function_call else None,
                )
            )

        plan = TaskPlan(
            navigation_goal=navigation_goal,
            reasoning=data.get("reasoning"),
            subtasks=subtasks,
            is_replan=is_replan,
            replan_reason=replan_reason,
            version=version,
        )
        logger.info(
            "PlannerAgent: created plan with %d sub-tasks for: %s",
            len(subtasks),
            navigation_goal,
        )
        return plan

    @staticmethod
    def _load_llm_json(raw: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        return json.loads(cleaned)

    def _create_fallback_plan(self, navigation_goal: str) -> TaskPlan:
        return TaskPlan(
            navigation_goal=navigation_goal,
            reasoning="Fallback single-step plan generated without LLM.",
            subtasks=[
                SubTask(
                    index=0,
                    goal=navigation_goal,
                    completion_condition="Navigation goal achieved",
                    failure_strategy=FailureStrategy.ABORT,
                    max_retries=3,
                ),
            ],
        )
