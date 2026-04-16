"""Three-layer resilient LLM caller.

Layer 1 (Prompt): Forces structured JSON output via system prompt + schema
Layer 2 (Parse):  Pydantic validation + markdown cleanup + exponential backoff retry
Layer 3 (Task):   After max retries, transitions task to NEEDS_HUMAN state
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from enterprise.llm_eval.tracer import LLMTracer

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

RETRY_DELAYS = [1.0, 2.0, 4.0]
MAX_RETRIES = 3
MARKDOWN_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
RETRY_HINTS = {
    "JSONDecodeError": "\n\nIMPORTANT: Your previous response was not valid JSON. Respond with ONLY one JSON object. No markdown fences, no explanation.",
    "ValidationError": "\n\nIMPORTANT: Your previous JSON was missing fields or had invalid types. Follow the schema exactly: {schema}",
    "generic": "\n\nIMPORTANT: Previous attempt failed ({error}). Try again carefully and follow the required output format exactly.",
}


@dataclass
class LLMCallResult:
    """Result of a resilient LLM call."""

    success: bool
    data: Any = None
    raw_response: str | None = None
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    needs_human: bool = False


def build_structured_prompt(
    task_description: str,
    schema_class: type[BaseModel],
    additional_context: str = "",
) -> str:
    schema_json = json.dumps(schema_class.model_json_schema(), indent=2)

    prompt = (
        "You are a financial RPA assistant. You MUST respond with valid JSON "
        "matching the following schema. Do NOT include any text outside the JSON object.\n\n"
        f"## Required JSON Schema\n```json\n{schema_json}\n```\n\n"
    )

    if additional_context:
        prompt += f"## Context\n{additional_context}\n\n"

    prompt += f"## Task\n{task_description}\n"
    return prompt


def clean_llm_response(raw: str) -> str:
    text = raw.strip()
    match = MARKDOWN_FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()
    return text


def parse_and_validate(raw: str, schema_class: type[T]) -> T:
    cleaned = clean_llm_response(raw)
    data = json.loads(cleaned)
    return schema_class.model_validate(data)


def _mutate_prompt(base_prompt: str, schema_class: type[BaseModel], error_type: str, error_detail: str) -> str:
    if error_type == "JSONDecodeError":
        return base_prompt + RETRY_HINTS["JSONDecodeError"]
    if error_type == "ValidationError":
        schema = json.dumps(schema_class.model_json_schema(), ensure_ascii=False)
        return base_prompt + RETRY_HINTS["ValidationError"].format(schema=schema)
    return base_prompt + RETRY_HINTS["generic"].format(error=error_detail)


async def call_llm_with_retry(
    llm_callable,
    prompt: str,
    schema_class: type[T],
    max_retries: int = MAX_RETRIES,
    retry_delays: list[float] | None = None,
    tracer: LLMTracer | None = None,
) -> LLMCallResult:
    if retry_delays is None:
        retry_delays = RETRY_DELAYS[:max_retries]

    result = LLMCallResult(success=False)
    current_prompt = prompt
    traced_callable = tracer.wrap(llm_callable) if tracer else llm_callable

    for attempt in range(max_retries):
        result.attempts = attempt + 1

        try:
            raw_response = await traced_callable(current_prompt)
            result.raw_response = raw_response
            parsed = parse_and_validate(raw_response, schema_class)
            result.success = True
            result.data = parsed
            logger.info("LLM call succeeded on attempt %d", attempt + 1)
            return result
        except json.JSONDecodeError as exc:
            error_msg = f"Attempt {attempt + 1}: JSON parse error — {exc}"
            result.errors.append(error_msg)
            current_prompt = _mutate_prompt(prompt, schema_class, "JSONDecodeError", str(exc))
            logger.warning(error_msg)
        except ValidationError as exc:
            error_msg = f"Attempt {attempt + 1}: Schema validation error — {exc}"
            result.errors.append(error_msg)
            current_prompt = _mutate_prompt(prompt, schema_class, "ValidationError", str(exc))
            logger.warning(error_msg)
        except Exception as exc:
            error_msg = f"Attempt {attempt + 1}: LLM call error — {type(exc).__name__}: {exc}"
            result.errors.append(error_msg)
            current_prompt = _mutate_prompt(prompt, schema_class, "generic", str(exc))
            logger.warning(error_msg)

        if attempt < max_retries - 1:
            delay = retry_delays[min(attempt, len(retry_delays) - 1)]
            logger.info("Retrying in %.1fs...", delay)
            await asyncio.sleep(delay)

    result.needs_human = True
    logger.error("LLM call failed after %d attempts. Task needs human intervention.", max_retries)
    return result
