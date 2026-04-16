from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class LLMTrace:
    trace_id: str
    timestamp: datetime
    module: str
    prompt: str
    response: str
    model_tier: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMTraceResponse(BaseModel):
    trace_id: str
    timestamp: datetime
    module: str
    model_tier: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GoldenCase(BaseModel):
    case_id: str
    module: str
    input_text: str
    expected_output: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class EvalCaseResult(BaseModel):
    case_id: str
    passed: bool
    latency_ms: int
    actual_output: dict[str, Any]
    expected_output: dict[str, Any]
    notes: str | None = None
    score: float = 0.0


class EvalMetrics(BaseModel):
    accuracy: float = 0.0
    weighted_f1: float = 0.0
    miss_rate: float = 0.0
    conservative_rate: float = 0.0
    plan_validity: float = 0.0
    avg_step_count: float = 0.0
    goal_coverage: float = 0.0
    llm_judge_score: float = 0.0
    avg_latency_ms: float = 0.0
    total_cases: int = 0
    passed_cases: int = 0


class EvalReport(BaseModel):
    eval_id: str
    module: str
    prompt_version: str = "v1"
    generated_at: datetime
    metrics: EvalMetrics
    results: list[EvalCaseResult]


class EvalRunRequest(BaseModel):
    module: str = Field(pattern="^(risk_detector|planner)$")
    prompt_version: str = Field(default="v1", min_length=1, max_length=50)


class EvalCompareResponse(BaseModel):
    eval_id_a: str
    eval_id_b: str
    module: str
    metric_diff: dict[str, float]
