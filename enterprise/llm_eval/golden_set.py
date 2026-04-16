from __future__ import annotations

from .schemas import GoldenCase


def get_default_golden_set() -> list[GoldenCase]:
    return [
        GoldenCase(
            case_id="risk_001",
            module="risk_detector",
            input_text="为企业客户执行跨境转账 500 万元并导出交易记录",
            expected_output={"risk_level": "critical", "reason_contains": "跨境"},
            tags=["banking", "transfer", "critical"],
            metadata={"type": "compliance"},
        ),
        GoldenCase(
            case_id="risk_002",
            module="risk_detector",
            input_text="查询客户近 3 个月对账单",
            expected_output={"risk_level": "low"},
            tags=["banking", "query", "low"],
            metadata={"type": "compliance"},
        ),
        GoldenCase(
            case_id="risk_003",
            module="risk_detector",
            input_text="修改客户保单受益人为非直系亲属",
            expected_output={"risk_level": "high", "reason_contains": "受益人"},
            tags=["insurance", "beneficiary_change", "high"],
            metadata={"type": "compliance"},
        ),
        GoldenCase(
            case_id="planner_001",
            module="planner",
            input_text="登录信贷系统并完成企业贷款审批前的数据核验",
            expected_output={"min_steps": 3, "must_include": ["登录", "核验"]},
            tags=["planner", "credit"],
            metadata={"type": "workflow_example"},
        ),
        GoldenCase(
            case_id="planner_002",
            module="planner",
            input_text="进入国际结算系统，查询待处理跨境付款并导出清单",
            expected_output={"min_steps": 3, "must_include": ["查询", "导出"]},
            tags=["planner", "settlement"],
            metadata={"type": "workflow_example"},
        ),
    ]
