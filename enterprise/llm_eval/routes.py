from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from enterprise.auth.dependencies import require_admin, require_any_operator
from enterprise.auth.schemas import UserContext

from .evaluator import Evaluator
from .schemas import EvalCompareResponse, EvalReport, EvalRunRequest, LLMTraceResponse
from .trace_store import report_store, trace_store

router = APIRouter(prefix="/enterprise/eval", tags=["evaluation"])


@router.post("/run", response_model=EvalReport)
async def run_evaluation(
    request: EvalRunRequest,
    user: UserContext = Depends(require_admin),
) -> EvalReport:
    evaluator = Evaluator.from_request(request)
    return await evaluator.run()


@router.get("/reports", response_model=list[EvalReport])
async def list_reports(
    user: UserContext = Depends(require_any_operator),
    module: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[EvalReport]:
    return report_store.list(module=module, limit=limit)


@router.get("/reports/{eval_id}", response_model=EvalReport)
async def get_report(
    eval_id: str,
    user: UserContext = Depends(require_any_operator),
) -> EvalReport:
    report = report_store.get(eval_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Evaluation report not found")
    return report


@router.get("/compare", response_model=EvalCompareResponse)
async def compare_reports(
    eval_id_a: str,
    eval_id_b: str,
    user: UserContext = Depends(require_any_operator),
) -> EvalCompareResponse:
    report_a = report_store.get(eval_id_a)
    report_b = report_store.get(eval_id_b)
    if report_a is None or report_b is None:
        raise HTTPException(status_code=404, detail="One or both evaluation reports were not found")
    if report_a.module != report_b.module:
        raise HTTPException(status_code=400, detail="Reports must belong to the same module")

    metrics_a = report_a.metrics.model_dump()
    metrics_b = report_b.metrics.model_dump()
    shared_keys = set(metrics_a) & set(metrics_b)
    metric_diff = {
        key: round(float(metrics_b[key]) - float(metrics_a[key]), 4)
        for key in shared_keys
        if isinstance(metrics_a[key], (int, float)) and isinstance(metrics_b[key], (int, float))
    }
    return EvalCompareResponse(
        eval_id_a=eval_id_a,
        eval_id_b=eval_id_b,
        module=report_a.module,
        metric_diff=metric_diff,
    )


@router.get("/traces", response_model=list[LLMTraceResponse])
async def list_traces(
    user: UserContext = Depends(require_any_operator),
    module: str | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[LLMTraceResponse]:
    traces = trace_store.list(module=module, limit=limit, hours=hours)
    return [LLMTraceResponse(**trace.__dict__) for trace in traces]


@router.get("/traces/stats")
async def trace_stats(
    user: UserContext = Depends(require_any_operator),
    hours: int = Query(default=24, ge=1, le=168),
) -> dict[str, float | int | dict[str, dict[str, float | int]]]:
    return trace_store.stats(hours=hours)
