from __future__ import annotations

from .base_agent import BaseAgent
from .message import AgentMessage, AgentResponse


class ReviewerAgent(BaseAgent):
    agent_name = "reviewer"
    agent_description = "Reviews execution quality and optionally performs semantic validation"
    capabilities = ["review_result"]

    def __init__(self, llm_callable=None):
        super().__init__(llm_callable=llm_callable, model_tier="light")

    async def handle_message(self, message: AgentMessage) -> AgentResponse:
        goal = str(message.payload.get("subtask_goal", ""))
        completion_condition = str(message.payload.get("completion_condition", ""))
        exec_result = message.payload.get("execution_result", {})
        duration = int(exec_result.get("duration_ms", 0) or 0)
        issues: list[str] = []
        score = 1.0

        if not exec_result.get("success", False):
            issues.append("Execution reported failure")
            score -= 0.5
        if not exec_result.get("result_data"):
            issues.append("No result data returned")
            score -= 0.2
        if duration > 30000:
            issues.append(f"Unusually long execution: {duration}ms")
            score -= 0.1

        if self.llm_callable and exec_result.get("success"):
            llm_score = await self._llm_review(goal, completion_condition, exec_result)
            score = score * 0.6 + llm_score * 0.4

        score = max(0.0, min(1.0, score))
        return AgentResponse(
            message_id=message.message_id,
            agent_name=self.agent_name,
            success=True,
            result={
                "review_passed": score >= 0.6 and not any("failure" in issue.lower() for issue in issues),
                "quality_score": round(score, 2),
                "issues": issues,
            },
        )

    async def _llm_review(self, goal: str, condition: str, result: dict) -> float:
        prompt = f"""Review this task execution result:
- Goal: {goal}
- Expected completion condition: {condition}
- Actual result: {result}

Score the quality from 0 to 10. Respond with just the number."""
        try:
            raw = await self.llm_callable(prompt)
            return min(10, max(0, float(str(raw).strip()))) / 10.0
        except Exception:
            return 0.5
