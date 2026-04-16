"""Two-stage financial risk detection engine.

Stage 1: Fast keyword + regex scan against industry-specific libraries.
Stage 2: LLM-based contextual analysis (only if Stage 1 hits).
Fallback: If LLM fails and Stage 1 hit, conservatively return 'high'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from enterprise.rag.rag_chain import RAGChain

from .risk_keywords import (
    ALL_KEYWORDS,
    INDUSTRY_KEYWORDS,
    IndustryType,
    KeywordEntry,
    has_high_amount,
)

LOG = structlog.get_logger()


@dataclass
class RiskAssessment:
    """Result of risk detection on an operation."""

    risk_level: str
    reason: str
    matched_keywords: list[str] = field(default_factory=list)
    stage: int = 1
    llm_fallback: bool = False


def _keyword_scan(
    text: str,
    industry: IndustryType | None = None,
) -> list[KeywordEntry]:
    keywords = INDUSTRY_KEYWORDS.get(industry, ALL_KEYWORDS) if industry else ALL_KEYWORDS
    text_lower = text.lower()

    matched = []
    for kw in keywords:
        if kw.keyword.lower() in text_lower:
            matched.append(kw)

    risk_order = {"critical": 0, "high": 1, "medium": 2}
    matched.sort(key=lambda keyword: risk_order.get(keyword.risk_level, 3))
    return matched


async def _llm_risk_analysis(
    text: str,
    matched_keywords: list[KeywordEntry],
    page_context: str | None = None,
    llm_callable=None,
    industry: IndustryType | None = None,
    rag_chain: RAGChain | None = None,
) -> RiskAssessment | None:
    if llm_callable is None:
        return None

    rag_context = None
    if rag_chain is not None:
        try:
            rag_context = await rag_chain.build_augmented_context(
                query=text,
                filter_metadata={"type": "compliance"},
                max_context_tokens=1500,
            )
        except Exception as exc:
            LOG.warning("RAG risk context lookup failed", error=str(exc))

    prompt = f"""You are a senior financial compliance officer with expertise in {industry or 'financial'} operations.

## Analysis Framework
Analyze this operation step by step:
1. Operation Type: what financial action is being performed?
2. Risk Indicators: which matched keywords indicate real risk vs false positives?
3. Amount Assessment: does the operation involve monetary amounts and how large are they?
4. Regulatory Impact: could this violate AML, KYC, approval, or reporting requirements?
5. Reversibility: is the operation easy to reverse if it goes wrong?
6. Final Judgment: provide the overall risk level.

## Risk Level Definitions
- medium: operation involves sensitive data or moderate amounts, standard review is sufficient
- high: operation could cause significant financial loss or regulatory issues, department approval required
- critical: operation involves very large amounts, cross-border transactions, or material compliance exposure

## Operation Details
- Description: {text}
- Matched risk keywords: {', '.join(kw.keyword for kw in matched_keywords)}
- Keyword categories: {', '.join(sorted({kw.category for kw in matched_keywords}))}
{f'- Page context: {page_context}' if page_context else ''}
{f'## Reference regulations\n{rag_context.augmented_text}' if rag_context and rag_context.augmented_text else ''}

Respond with a JSON object:
{{"reasoning": "brief step-by-step analysis", "risk_level": "medium|high|critical", "reason": "one-sentence summary"}}
"""

    try:
        result = await llm_callable(prompt)
        if result and isinstance(result, dict):
            level = result.get("risk_level", "high")
            reason = result.get("reason", "LLM analysis")
            if level in ("medium", "high", "critical"):
                return RiskAssessment(
                    risk_level=level,
                    reason=reason,
                    matched_keywords=[kw.keyword for kw in matched_keywords],
                    stage=2,
                )
    except Exception as exc:
        LOG.warning("LLM risk analysis failed", error=str(exc))

    return None


async def detect_risk(
    text: str,
    industry: IndustryType | None = None,
    page_context: str | None = None,
    llm_callable=None,
    rag_chain: RAGChain | None = None,
) -> RiskAssessment:
    matched = _keyword_scan(text, industry)

    if not matched:
        if has_high_amount(text):
            return RiskAssessment(
                risk_level="medium",
                reason="Large monetary amount detected without specific risk keywords",
                matched_keywords=[],
                stage=1,
            )
        return RiskAssessment(
            risk_level="low",
            reason="No risk indicators detected",
            stage=1,
        )

    stage1_level = matched[0].risk_level
    stage1_keywords = [kw.keyword for kw in matched]

    if has_high_amount(text) and stage1_level == "high":
        stage1_level = "critical"

    LOG.info(
        "Stage 1 risk detected",
        level=stage1_level,
        keywords=stage1_keywords[:5],
        text_preview=text[:100],
    )

    llm_result = await _llm_risk_analysis(
        text=text,
        matched_keywords=matched,
        page_context=page_context,
        llm_callable=llm_callable,
        industry=industry,
        rag_chain=rag_chain,
    )

    if llm_result:
        LOG.info(
            "Stage 2 LLM confirmed risk",
            level=llm_result.risk_level,
            reason=llm_result.reason,
        )
        return llm_result

    if llm_callable is not None:
        LOG.warning(
            "LLM risk analysis failed, using conservative fallback",
            stage1_level=stage1_level,
        )
        fallback_level = "high" if stage1_level == "medium" else stage1_level
        return RiskAssessment(
            risk_level=fallback_level,
            reason=f"Stage 1 keyword match (LLM fallback): {', '.join(stage1_keywords[:3])}",
            matched_keywords=stage1_keywords,
            stage=1,
            llm_fallback=True,
        )

    return RiskAssessment(
        risk_level=stage1_level,
        reason=f"Keyword match: {', '.join(stage1_keywords[:3])}",
        matched_keywords=stage1_keywords,
        stage=1,
    )
