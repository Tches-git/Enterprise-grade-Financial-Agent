from __future__ import annotations

from collections import Counter
import re
from typing import Any

from .schemas import EvalCaseResult, EvalMetrics

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")
_RISK_LABELS = ["low", "medium", "high", "critical"]


def compute_risk_metrics(results: list[EvalCaseResult]) -> dict[str, float]:
    total = len(results)
    if total == 0:
        return {
            "accuracy": 0.0,
            "weighted_f1": 0.0,
            "miss_rate": 0.0,
            "conservative_rate": 0.0,
        }

    exact_matches = 0
    critical_total = 0
    critical_missed = 0
    conservative = 0
    label_counts: Counter[str] = Counter()
    true_positive: Counter[str] = Counter()
    predicted_counts: Counter[str] = Counter()

    order = {label: index for index, label in enumerate(_RISK_LABELS)}

    for result in results:
        expected = str(result.expected_output.get("risk_level", "")).lower()
        actual = str(result.actual_output.get("risk_level", "")).lower()
        if expected == actual:
            exact_matches += 1
            true_positive[expected] += 1
        label_counts[expected] += 1
        predicted_counts[actual] += 1
        if expected == "critical":
            critical_total += 1
            if actual != "critical":
                critical_missed += 1
        if expected in order and actual in order and order.get(actual, -1) > order.get(expected, -1):
            conservative += 1

    weighted_f1 = 0.0
    for label, support in label_counts.items():
        if support == 0:
            continue
        precision = true_positive[label] / max(predicted_counts[label], 1)
        recall = true_positive[label] / support
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        weighted_f1 += f1 * support
    weighted_f1 /= total

    return {
        "accuracy": round(exact_matches / total, 4),
        "weighted_f1": round(weighted_f1, 4),
        "miss_rate": round(critical_missed / critical_total, 4) if critical_total else 0.0,
        "conservative_rate": round(conservative / total, 4),
    }


def compute_planner_metrics(results: list[EvalCaseResult]) -> dict[str, float]:
    total = len(results)
    if total == 0:
        return {
            "plan_validity": 0.0,
            "avg_step_count": 0.0,
            "goal_coverage": 0.0,
        }

    valid_count = 0
    total_steps = 0
    coverage_scores: list[float] = []

    for result in results:
        actual_steps = result.actual_output.get("steps", [])
        if isinstance(actual_steps, list):
            valid_count += 1
            total_steps += len(actual_steps)
        input_text = str(result.expected_output.get("input_text", result.notes or ""))
        must_include = result.expected_output.get("must_include", [])
        step_text = " ".join(str(step) for step in actual_steps)
        if must_include:
            matched = sum(1 for keyword in must_include if keyword in step_text)
            coverage_scores.append(matched / len(must_include))
        else:
            coverage_scores.append(_lexical_overlap(input_text, step_text))

    return {
        "plan_validity": round(valid_count / total, 4),
        "avg_step_count": round(total_steps / max(valid_count, 1), 2),
        "goal_coverage": round(sum(coverage_scores) / len(coverage_scores), 4) if coverage_scores else 0.0,
    }


async def llm_as_judge(
    case_input: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    judge_callable=None,
) -> float:
    if judge_callable is None:
        return _heuristic_judge_score(case_input, expected, actual)

    prompt = (
        "你是一位金融 AI 系统评估专家。给定输入、期望输出、实际输出，"
        "请从准确性、完整性、推理质量三个维度打分（每项 0-10），"
        "并返回 JSON：{\"accuracy\": number, \"completeness\": number, \"reasoning\": number}.\n\n"
        f"输入: {case_input}\n期望输出: {expected}\n实际输出: {actual}"
    )
    try:
        response = await judge_callable(prompt)
        if isinstance(response, dict):
            scores = [float(response.get(key, 0)) for key in ("accuracy", "completeness", "reasoning")]
            return round(sum(scores) / 30, 4)
    except Exception:
        return _heuristic_judge_score(case_input, expected, actual)
    return _heuristic_judge_score(case_input, expected, actual)


def build_eval_metrics(
    module: str,
    results: list[EvalCaseResult],
    judge_scores: list[float],
) -> EvalMetrics:
    latencies = [result.latency_ms for result in results]
    passed_cases = sum(1 for result in results if result.passed)
    base_metrics = compute_risk_metrics(results) if module == "risk_detector" else compute_planner_metrics(results)
    return EvalMetrics(
        accuracy=base_metrics.get("accuracy", 0.0),
        weighted_f1=base_metrics.get("weighted_f1", 0.0),
        miss_rate=base_metrics.get("miss_rate", 0.0),
        conservative_rate=base_metrics.get("conservative_rate", 0.0),
        plan_validity=base_metrics.get("plan_validity", 0.0),
        avg_step_count=base_metrics.get("avg_step_count", 0.0),
        goal_coverage=base_metrics.get("goal_coverage", 0.0),
        llm_judge_score=round(sum(judge_scores) / len(judge_scores), 4) if judge_scores else 0.0,
        avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        total_cases=len(results),
        passed_cases=passed_cases,
    )


def _heuristic_judge_score(case_input: str, expected: dict[str, Any], actual: dict[str, Any]) -> float:
    exact_bonus = 1.0 if expected.get("risk_level") == actual.get("risk_level") else 0.0
    overlap_bonus = _lexical_overlap(case_input, str(actual))
    return round(min(1.0, 0.6 * exact_bonus + 0.4 * overlap_bonus), 4)


def _lexical_overlap(left: str, right: str) -> float:
    left_terms = {match.group(0).lower() for match in _WORD_RE.finditer(left)}
    right_terms = {match.group(0).lower() for match in _WORD_RE.finditer(right)}
    if not left_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms)
