"""AgentCoordinator: integrates the original planner/executor loop with the message-driven multi-agent framework."""

import logging
from typing import Any

from enterprise.agent.framework import (
    AgentMessage,
    ApprovalAgent,
    ExperienceAgent,
    ReviewerAgent,
    RiskAgent,
    TaskOrchestrator,
    agent_registry,
)
from enterprise.rag.embedder import Embedder, EmbeddingProvider
from enterprise.rag.routes import get_rag_chain

from .executor import ExecutorAgent
from .planner import PlannerAgent
from .schemas import CoordinationState, ExecutionResult, FailureStrategy, SubTask, SubTaskStatus, TaskPlan

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """Coordinates the legacy planner/executor loop and the new multi-agent framework."""

    def __init__(
        self,
        planner: PlannerAgent,
        executor: ExecutorAgent,
        audit_callback=None,
        max_replans: int = 3,
        use_framework: bool = True,
    ):
        self.planner = planner
        self.executor = executor
        self.audit_callback = audit_callback
        self.max_replans = max_replans
        self.use_framework = use_framework
        self.orchestrator = self._build_orchestrator() if use_framework else None

    def _build_orchestrator(self) -> TaskOrchestrator:
        rag_chain = getattr(self.planner, "rag_chain", None) or get_rag_chain()
        vector_store = rag_chain.retriever.vector_store if rag_chain else None
        experience_embedder = Embedder(provider=EmbeddingProvider.HASH)

        agent_registry.register(self.planner)
        agent_registry.register(self.executor)
        agent_registry.register(RiskAgent(llm_callable=self.planner.llm_callable, rag_chain=rag_chain))
        agent_registry.register(ApprovalAgent())
        agent_registry.register(ReviewerAgent(llm_callable=self.planner.llm_callable))
        agent_registry.register(ExperienceAgent(vector_store=vector_store, embedder=experience_embedder))
        return TaskOrchestrator(agent_registry)

    async def run(
        self,
        task_id: str,
        org_id: str,
        navigation_goal: str,
        context: dict[str, Any] | None = None,
        resume_from: list[str] | None = None,
    ) -> CoordinationState:
        state = CoordinationState(
            task_id=task_id,
            org_id=org_id,
            navigation_goal=navigation_goal,
            completed_subtasks=resume_from or [],
        )

        if self.use_framework and self.orchestrator is not None:
            framework_result = await self._run_framework(task_id, org_id, navigation_goal, context)
            state.status = "completed" if framework_result.get("success") else "failed"
            state.error_message = framework_result.get("error")
            return state

        try:
            plan = await self.planner.create_plan(navigation_goal, context)
        except Exception as exc:
            logger.error("Coordinator: planning failed for task %s: %s", task_id, exc)
            state.status = "failed"
            state.error_message = f"Planning failed: {exc}"
            return state

        state.current_plan = plan
        logger.info("Coordinator: task %s planned with %d sub-tasks", task_id, len(plan.subtasks))
        completed_subtasks: list[SubTask] = []
        return await self._execute_plan(state, plan, completed_subtasks, context)

    async def _run_framework(
        self,
        task_id: str,
        org_id: str,
        navigation_goal: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if self.orchestrator is None:
            return {"success": False, "error": "Framework orchestrator is not configured"}

        initial_context = {"task_id": task_id, "org_id": org_id, **(context or {})}
        initial_message = AgentMessage(
            type="plan_request",
            sender="coordinator",
            payload={
                "navigation_goal": navigation_goal,
                "goal": navigation_goal,
                "text": navigation_goal,
                "org_id": org_id,
                "task_id": task_id,
            },
            context=initial_context,
        )
        planning_result = await self.orchestrator.run(initial_message, pipeline=[])
        plan_data = planning_result.get("context", {}).get("task_plan")
        if not planning_result.get("success") or not plan_data:
            return planning_result

        task_plan = TaskPlan.model_validate(plan_data)
        completed: list[SubTask] = []

        for subtask in task_plan.subtasks:
            gating_message = AgentMessage(
                type="risk_check",
                sender="coordinator",
                payload={
                    "goal": subtask.goal,
                    "text": subtask.goal,
                    "task_id": task_id,
                    "org_id": org_id,
                    "department_id": initial_context.get("department_id", "dept_it"),
                    "operation_description": subtask.goal,
                },
                context=initial_context,
                trace_id=initial_message.trace_id,
            )
            gating_result = await self.orchestrator.run(gating_message)
            if not gating_result.get("success"):
                return gating_result

            gating_context = gating_result.get("context", {})
            if gating_context.get("approval_required"):
                approval_message = AgentMessage(
                    type="approval_request",
                    sender="coordinator",
                    payload={
                        **gating_context,
                        "task_id": task_id,
                        "org_id": org_id,
                        "goal": subtask.goal,
                        "operation_description": subtask.goal,
                    },
                    context=initial_context,
                    trace_id=initial_message.trace_id,
                )
                approval_result = await self.orchestrator.run(approval_message)
                if not approval_result.get("success"):
                    return approval_result
                approval_context = approval_result.get("context", {})
                if approval_context.get("approval_status") != "approved":
                    return {"success": False, "error": "Approval gate did not pass", "context": approval_context}

            exec_message = AgentMessage(
                type="execute_subtask",
                sender="coordinator",
                payload={
                    "subtask": subtask.model_dump(),
                    "subtask_goal": subtask.goal,
                    "completion_condition": subtask.completion_condition,
                },
                context=initial_context,
                trace_id=initial_message.trace_id,
            )
            exec_response = await self.executor.handle_message(exec_message)
            exec_result_data = exec_response.result.get("execution_result") if exec_response.result else None
            exec_result = ExecutionResult.model_validate(exec_result_data) if exec_result_data else ExecutionResult(
                subtask_id=subtask.subtask_id,
                success=False,
                error_message=exec_response.error,
            )
            if self.audit_callback:
                try:
                    await self.audit_callback(subtask, exec_result)
                except Exception as exc:
                    logger.warning("Coordinator: audit callback failed for subtask %s: %s", subtask.subtask_id, exc)

            if not exec_result.success:
                if subtask.failure_strategy == FailureStrategy.REPLAN:
                    return {"success": False, "error": exec_result.error_message or "Subtask failed and requires replan"}
                if subtask.failure_strategy == FailureStrategy.SKIP:
                    subtask.status = SubTaskStatus.SKIPPED
                    continue
                return {"success": False, "error": exec_result.error_message or "Subtask execution failed"}

            completed.append(subtask)
            review_message = AgentMessage(
                type="review_result",
                sender="coordinator",
                payload={
                    "subtask_goal": subtask.goal,
                    "completion_condition": subtask.completion_condition,
                    "execution_result": exec_result.model_dump(),
                },
                context=initial_context,
                trace_id=initial_message.trace_id,
            )
            await self.orchestrator.run(review_message, pipeline=[])

            experience_message = AgentMessage(
                type="record_experience",
                sender="coordinator",
                payload={
                    "navigation_goal": navigation_goal,
                    "subtask_goal": subtask.goal,
                    "success": exec_result.success,
                    "result_data": exec_result.result_data,
                    "error_message": exec_result.error_message,
                    "duration_ms": exec_result.duration_ms,
                    "org_id": org_id,
                },
                context=initial_context,
                trace_id=initial_message.trace_id,
            )
            await self.orchestrator.run(experience_message, pipeline=[])

        return {
            "success": True,
            "task_plan": task_plan.model_dump(),
            "completed_subtasks": [sub.subtask_id for sub in completed],
        }

    async def _execute_plan(
        self,
        state: CoordinationState,
        plan: TaskPlan,
        completed_subtasks: list[SubTask],
        context: dict[str, Any] | None,
    ) -> CoordinationState:
        for subtask in plan.subtasks:
            if subtask.subtask_id in state.completed_subtasks:
                logger.info("Coordinator: skipping already-completed subtask %s", subtask.subtask_id)
                completed_subtasks.append(subtask)
                continue

            result = await self.executor.execute_subtask(subtask, context)

            if self.audit_callback:
                try:
                    await self.audit_callback(subtask, result)
                except Exception as exc:
                    logger.warning("Coordinator: audit callback failed for subtask %s: %s", subtask.subtask_id, exc)

            if result.success:
                state.completed_subtasks.append(subtask.subtask_id)
                completed_subtasks.append(subtask)
                continue

            outcome = await self._handle_failure(state, plan, subtask, result, completed_subtasks, context)
            if outcome == "aborted":
                return state
            if outcome == "replanned":
                return state

        state.status = "completed"
        logger.info("Coordinator: task %s completed successfully", state.task_id)
        return state

    async def _handle_failure(
        self,
        state: CoordinationState,
        plan: TaskPlan,
        failed_subtask: SubTask,
        result: ExecutionResult,
        completed_subtasks: list[SubTask],
        context: dict[str, Any] | None,
    ) -> str:
        strategy = failed_subtask.failure_strategy

        if strategy == FailureStrategy.SKIP:
            logger.info("Coordinator: skipping failed subtask %s", failed_subtask.subtask_id)
            failed_subtask.status = SubTaskStatus.SKIPPED
            return "continued"

        if strategy == FailureStrategy.ABORT:
            logger.error("Coordinator: aborting task %s at subtask %s", state.task_id, failed_subtask.subtask_id)
            state.status = "failed"
            state.error_message = f"Sub-task {failed_subtask.index} failed: {result.error_message}"
            return "aborted"

        if strategy == FailureStrategy.REPLAN:
            if state.total_replans >= self.max_replans:
                logger.error("Coordinator: max replans (%d) reached for task %s", self.max_replans, state.task_id)
                state.status = "needs_human"
                state.error_message = f"Max replans exceeded. Last failure: {result.error_message}"
                return "aborted"

            state.total_replans += 1
            logger.info("Coordinator: replanning task %s (attempt %d/%d)", state.task_id, state.total_replans, self.max_replans)

            try:
                new_plan = await self.planner.replan(
                    original_goal=state.navigation_goal,
                    completed_subtasks=completed_subtasks,
                    failed_subtask=failed_subtask,
                    failure_reason=result.error_message or "Unknown error",
                    context=context,
                )
            except Exception as exc:
                logger.error("Coordinator: replan failed: %s", exc)
                state.status = "needs_human"
                state.error_message = f"Replan failed: {exc}"
                return "aborted"

            state.current_plan = new_plan
            await self._execute_plan(state, new_plan, completed_subtasks, context)
            return "replanned"

        state.status = "failed"
        state.error_message = f"Sub-task {failed_subtask.index} failed after retries: {result.error_message}"
        return "aborted"
