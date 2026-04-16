from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Iterable

from .schemas import EvalReport, LLMTrace


class TraceStore:
    def __init__(self, max_items: int = 500):
        self._items: deque[LLMTrace] = deque(maxlen=max_items)

    def add(self, trace: LLMTrace) -> None:
        self._items.appendleft(trace)

    def list(self, module: str | None = None, limit: int = 50, hours: int | None = None) -> list[LLMTrace]:
        items: Iterable[LLMTrace] = self._items
        if module:
            items = [item for item in items if item.module == module]
        if hours is not None:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            items = [item for item in items if item.timestamp >= cutoff]
        return list(items)[:limit]

    def stats(self, hours: int | None = None) -> dict[str, float | int | dict[str, dict[str, float | int]]]:
        items = self.list(limit=len(self._items), hours=hours)
        total = len(items)
        successes = sum(1 for item in items if item.success)
        total_latency = sum(item.latency_ms for item in items)
        total_cost = sum(item.estimated_cost_usd for item in items)
        module_stats: dict[str, dict[str, float | int]] = {}
        for item in items:
            bucket = module_stats.setdefault(
                item.module,
                {"calls": 0, "avg_latency_ms": 0.0, "estimated_cost_usd": 0.0, "successes": 0},
            )
            bucket["calls"] += 1
            bucket["estimated_cost_usd"] = round(float(bucket["estimated_cost_usd"]) + item.estimated_cost_usd, 6)
            bucket["avg_latency_ms"] = float(bucket["avg_latency_ms"]) + item.latency_ms
            if item.success:
                bucket["successes"] += 1

        for bucket in module_stats.values():
            calls = int(bucket["calls"])
            bucket["avg_latency_ms"] = round(float(bucket["avg_latency_ms"]) / calls, 2) if calls else 0.0
            bucket["success_rate"] = round(int(bucket["successes"]) / calls, 4) if calls else 0.0
            del bucket["successes"]

        return {
            "total_traces": total,
            "success_rate": round(successes / total, 4) if total else 0.0,
            "avg_latency_ms": round(total_latency / total, 2) if total else 0.0,
            "estimated_cost_usd": round(total_cost, 6),
            "by_module": module_stats,
        }


class EvalReportStore:
    def __init__(self, max_items: int = 100):
        self._reports: deque[EvalReport] = deque(maxlen=max_items)

    def add(self, report: EvalReport) -> None:
        self._reports.appendleft(report)

    def list(self, module: str | None = None, limit: int = 20) -> list[EvalReport]:
        items: Iterable[EvalReport] = self._reports
        if module:
            items = [item for item in items if item.module == module]
        return list(items)[:limit]

    def get(self, eval_id: str) -> EvalReport | None:
        for report in self._reports:
            if report.eval_id == eval_id:
                return report
        return None


trace_store = TraceStore()
report_store = EvalReportStore()
