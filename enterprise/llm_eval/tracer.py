from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable

from .schemas import LLMTrace
from .trace_store import trace_store

MODEL_TIER_PRICING = {
    "light": 0.0002,
    "standard": 0.001,
    "heavy": 0.005,
}


class LLMTracer:
    def __init__(
        self,
        module_name: str,
        model_tier: str = "standard",
        metadata: dict[str, Any] | None = None,
    ):
        self.module_name = module_name
        self.model_tier = model_tier
        self.metadata = metadata or {}

    def wrap(self, llm_callable: Callable[[str], Awaitable[Any]]) -> Callable[[str], Awaitable[Any]]:
        async def traced_callable(prompt: str) -> Any:
            start = time.monotonic()
            try:
                response = await llm_callable(prompt)
                latency_ms = int((time.monotonic() - start) * 1000)
                trace_store.add(
                    LLMTrace(
                        trace_id=f"trace_{uuid.uuid4().hex[:12]}",
                        timestamp=datetime.utcnow(),
                        module=self.module_name,
                        prompt=prompt,
                        response=self._stringify(response),
                        model_tier=self.model_tier,
                        latency_ms=latency_ms,
                        input_tokens=self._estimate_tokens(prompt),
                        output_tokens=self._estimate_tokens(self._stringify(response)),
                        estimated_cost_usd=self._estimate_cost(prompt, response),
                        success=True,
                        metadata=self.metadata,
                    )
                )
                return response
            except Exception as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                trace_store.add(
                    LLMTrace(
                        trace_id=f"trace_{uuid.uuid4().hex[:12]}",
                        timestamp=datetime.utcnow(),
                        module=self.module_name,
                        prompt=prompt,
                        response="",
                        model_tier=self.model_tier,
                        latency_ms=latency_ms,
                        input_tokens=self._estimate_tokens(prompt),
                        output_tokens=0,
                        estimated_cost_usd=self._estimate_cost(prompt, ""),
                        success=False,
                        error=str(exc),
                        metadata=self.metadata,
                    )
                )
                raise

        return traced_callable

    def _estimate_cost(self, prompt: Any, response: Any) -> float:
        total_tokens = self._estimate_tokens(self._stringify(prompt)) + self._estimate_tokens(self._stringify(response))
        unit_price = MODEL_TIER_PRICING.get(self.model_tier, MODEL_TIER_PRICING["standard"])
        return round(total_tokens / 1000 * unit_price, 6)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value
        return str(value)
