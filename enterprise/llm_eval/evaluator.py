from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Awaitable, Callable

from enterprise.agent.planner import PlannerAgent
from enterprise.approval.risk_detector import detect_risk
from enterprise.rag.routes import get_rag_chain

from .golden_set import get_default_golden_set
from .metrics import build_eval_metrics, llm_as_judge
from .schemas import EvalCaseResult, EvalReport, EvalRunRequest, GoldenCase
from .trace_store import report_store


class Evaluator:
    def __init__(
        self,
        module: str,
        llm_callable: Callable[[str], Awaitable[str | dict]] | None = None,
        judge_callable: Callable[[str], Awaitable[str | dict]] | None = None,
        prompt_version: str = "v1",
    ):
        self.module = module
        self.llm_callable = llm_callable
        self.judge_callable = judge_callable
        self.prompt_version = prompt_version
        self.golden_set = [case for case in get_default_golden_set() if case.module == module]

    @classmethod
    def from_request(cls, request: EvalRunRequest) -> "Evaluator":
        return cls(module=request.module, prompt_version=request.prompt_version)

    async def run(self) -> EvalReport:
        results: list[EvalCaseResult] = []
        judge_scores: list[float] = []

        for case in self.golden_set:
            started = time.monotonic()
            actual_output = await self._execute_case(case)
            latency_ms = int((time.monotonic() - started) * 1000)
            passed, notes = self._evaluate_case(case, actual_output)
            score = await llm_as_judge(case.input_text, case.expected_output, actual_output, self.judge_callable)
            judge_scores.append(score)
            results.append(
                EvalCaseResult(
                    case_id=case.case_id,
                    passed=passed,
                    latency_ms=latency_ms,
                    actual_output=actual_output,
                    expected_output={**case.expected_output, "input_text": case.input_text},
                    notes=notes,
                    score=score,
                )
            )

        report = EvalReport(
            eval_id=f"eval_{uuid.uuid4().hex[:12]}",
            module=self.module,
            prompt_version=self.prompt_version,
            generated_at=datetime.utcnow(),
            metrics=build_eval_metrics(self.module, results, judge_scores),
            results=results,
        )
        report_store.add(report)
        return report

    async def _execute_case(self, case: GoldenCase) -> dict:
        if case.module == "risk_detector":
            result = await detect_risk(
                case.input_text,
                llm_callable=self.llm_callable,
                rag_chain=get_rag_chain(),
            )
            return {"risk_level": result.risk_level, "reason": result.reason}

        if case.module == "planner":
            planner = PlannerAgent(llm_callable=self.llm_callable, rag_chain=get_rag_chain())
            plan = await planner.create_plan(case.input_text, context={"source": "golden_set"})
            return {
                "step_count": len(plan.subtasks),
                "steps": [subtask.goal for subtask in plan.subtasks],
                "reasoning": plan.reasoning,
            }

        return {}

    def _evaluate_case(self, case: GoldenCase, actual_output: dict) -> tuple[bool, str | None]:
        if case.module == "risk_detector":
            expected_level = case.expected_output.get("risk_level")
            actual_level = actual_output.get("risk_level")
            if expected_level != actual_level:
                return False, f"expected={expected_level}, actual={actual_level}"
            reason_contains = case.expected_output.get("reason_contains")
            if reason_contains and reason_contains not in str(actual_output.get("reason", "")):
                return False, f"reason missing keyword: {reason_contains}"
            return True, None

        if case.module == "planner":
            min_steps = int(case.expected_output.get("min_steps", 1))
            actual_steps = int(actual_output.get("step_count", 0))
            if actual_steps < min_steps:
                return False, f"expected at least {min_steps} steps, got {actual_steps}"
            steps_text = " ".join(str(step) for step in actual_output.get("steps", []))
            for keyword in case.expected_output.get("must_include", []):
                if keyword not in steps_text:
                    return False, f"missing required keyword: {keyword}"
            return True, None

        return False, "unsupported module"
