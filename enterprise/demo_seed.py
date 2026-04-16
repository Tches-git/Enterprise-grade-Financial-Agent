"""Enterprise demo seed data generator.

Populates all in-memory stores with interconnected, realistic demo data
that references the same IDs from tests/fixtures/seed_demo_data.sql.
This ensures a unified, end-to-end demo experience across all modules.

Called on application startup from api_app.py.
"""

import random
from datetime import datetime, timedelta

import structlog

from enterprise.dashboard.routes import configure_stores as configure_dashboard_stores
from enterprise.llm_eval.trace_store import trace_store
from enterprise.rag.chunker import split_document
from enterprise.rag.embedder import Embedder, EmbeddingProvider
from enterprise.rag.routes import get_rag_chain
from enterprise.rag.schemas import ChunkConfig
from enterprise.rag.vector_store import VectorStore

LOG = structlog.get_logger()

ORG_ID = "o_demo_cmb"

DEPARTMENTS = {
    "dept_corp_credit": "对公信贷部",
    "dept_personal_fin": "个人金融部",
    "dept_asset_mgmt": "资产管理部",
    "dept_risk_mgmt": "风险管理部",
    "dept_compliance": "合规审计部",
    "dept_it": "信息技术部",
}

BUSINESS_LINES = {
    "bl_corp_loan": "对公贷款",
    "bl_retail_credit": "零售信贷",
    "bl_wealth_mgmt": "财富管理",
    "bl_intl_settle": "国际结算",
}

DEPT_BL_MAP = {
    "dept_corp_credit": ["bl_corp_loan", "bl_intl_settle"],
    "dept_personal_fin": ["bl_retail_credit"],
    "dept_asset_mgmt": ["bl_wealth_mgmt"],
    "dept_risk_mgmt": ["bl_corp_loan", "bl_retail_credit", "bl_wealth_mgmt", "bl_intl_settle"],
    "dept_compliance": ["bl_corp_loan", "bl_retail_credit", "bl_wealth_mgmt", "bl_intl_settle"],
    "dept_it": ["bl_corp_loan"],
}

DEPT_OPERATORS = {
    "dept_corp_credit": ["eu_cc_op1", "eu_cc_op2", "eu_cc_cross"],
    "dept_personal_fin": ["eu_pf_op"],
    "dept_asset_mgmt": ["eu_am_op"],
    "dept_risk_mgmt": ["eu_risk_viewer1", "eu_risk_viewer2"],
    "dept_compliance": ["eu_comp_approver", "eu_comp_viewer"],
    "dept_it": ["eu_it_op"],
}

DEPT_APPROVERS = {
    "dept_corp_credit": "eu_cc_approver",
    "dept_personal_fin": "eu_pf_approver",
    "dept_asset_mgmt": "eu_am_approver",
    "dept_compliance": "eu_comp_approver",
}

TASK_TEMPLATES = {
    "bl_corp_loan": [
        "企业贷款申请材料审核",
        "贷款额度计算与风险评估",
        "企业信用报告查询",
        "贷后监控数据采集",
        "抵押物价值评估录入",
        "贷款合同条款自动化审查",
        "企业财务报表数据提取",
    ],
    "bl_retail_credit": [
        "个人征信报告查询",
        "信用卡申请资料核验",
        "零售贷款利率计算",
        "个人还款能力评估",
        "消费贷款自动化审批",
        "客户KYC信息更新",
    ],
    "bl_wealth_mgmt": [
        "基金产品净值更新",
        "客户资产配置方案生成",
        "理财产品到期提醒处理",
        "投资组合风险分析",
        "高净值客户画像更新",
    ],
    "bl_intl_settle": [
        "跨境汇款合规审查",
        "国际结算单据核验",
        "外汇交易数据录入",
        "贸易融资申请处理",
        "进出口报关信息采集",
    ],
}

ERROR_TYPES = [
    ("ELEMENT_NOT_FOUND", 30),
    ("TIMEOUT", 25),
    ("LLM_FAILURE", 20),
    ("PAGE_LOAD_ERROR", 10),
    ("NAVIGATION_ERROR", 8),
    ("CAPTCHA_BLOCKED", 5),
    ("SESSION_EXPIRED", 2),
]

RISK_REASONS = {
    "high": [
        "大额交易操作，金额超过100万元",
        "敏感客户信息批量导出",
        "贷款额度调整超过审批权限",
        "跨境交易金额异常",
        "关联交易检测触发",
    ],
    "critical": [
        "系统权限变更操作",
        "核心数据库批量修改",
        "超大额资金划转（超过1000万）",
        "监管报送数据修改",
        "客户隐私数据大规模访问",
    ],
}

_COMPLIANCE_DOCS = [
    {
        "source_file": "banking_compliance.md",
        "type": "compliance",
        "text": "跨境汇款、客户隐私导出、大额转账必须进入人工审批流程，金额超过一百万元的操作默认升级为高风险。",
    },
    {
        "source_file": "workflow_examples.md",
        "type": "workflow_example",
        "text": "成功案例：先登录企业信贷系统，再检索客户档案，核验授信信息，最后导出审批材料并提交复核。",
    },
]


def _generate_tasks(rng: random.Random, now: datetime, count: int = 250) -> list[dict]:
    tasks = []
    operational_depts = ["dept_corp_credit", "dept_personal_fin", "dept_asset_mgmt", "dept_it"]
    dept_weights = [0.40, 0.25, 0.20, 0.15]
    error_names = [name for name, _ in ERROR_TYPES]
    error_weights = [weight for _, weight in ERROR_TYPES]

    for index in range(count):
        dept_id = rng.choices(operational_depts, weights=dept_weights, k=1)[0]
        bl_id = rng.choice(DEPT_BL_MAP[dept_id])
        creator = rng.choice(DEPT_OPERATORS.get(dept_id, ["eu_it_op"]))
        task_name = rng.choice(TASK_TEMPLATES.get(bl_id, TASK_TEMPLATES["bl_corp_loan"]))

        days_ago = min(int(rng.expovariate(0.15)), 30)
        created_at = (now - timedelta(days=days_ago, hours=rng.randint(0, 6))).replace(
            hour=rng.randint(8, 18),
            minute=rng.randint(0, 59),
            second=rng.randint(0, 59),
        )

        roll = rng.random()
        if roll < 0.72:
            status = "completed"
        elif roll < 0.87:
            status = "failed"
        elif roll < 0.92:
            status = "running"
        elif roll < 0.97:
            status = "needs_human"
        else:
            status = "pending_approval"

        if status == "running":
            created_at = now - timedelta(hours=rng.randint(0, 3), minutes=rng.randint(0, 59))

        if status == "completed":
            duration_ms = rng.randint(30000, 900000)
        elif status == "failed":
            duration_ms = rng.randint(10000, 300000)
        elif status == "running":
            duration_ms = None
        else:
            duration_ms = rng.randint(20000, 600000)

        error_type = rng.choices(error_names, weights=error_weights, k=1)[0] if status == "failed" else None
        tasks.append(
            {
                "task_id": f"tsk_demo_{index + 1:04d}",
                "org_id": ORG_ID,
                "organization_id": ORG_ID,
                "department_id": dept_id,
                "business_line_id": bl_id,
                "status": status,
                "created_at": created_at.isoformat(),
                "duration_ms": duration_ms,
                "error_type": error_type,
                "created_by": creator,
                "task_name": task_name,
            }
        )

    tasks.sort(key=lambda task: task["created_at"])
    return tasks


def _generate_approvals(rng: random.Random, tasks: list[dict]) -> list[dict]:
    approvals: list[dict] = []
    approval_index = 0

    def add_approval(task: dict, risk_level: str, status: str, response_min: int | None = None) -> None:
        nonlocal approval_index
        approval_index += 1
        requested_at = datetime.fromisoformat(task["created_at"])
        approver_dept = "dept_compliance" if risk_level == "critical" else task["department_id"]
        decided_at = (requested_at + timedelta(minutes=response_min)).isoformat() if response_min is not None else None
        approvals.append(
            {
                "org_id": ORG_ID,
                "approval_id": f"apr_demo_{approval_index:04d}",
                "status": status,
                "requested_at": requested_at.isoformat(),
                "decided_at": decided_at,
                "department_id": task["department_id"],
                "business_line_id": task["business_line_id"],
                "approver_department_id": approver_dept,
                "risk_reason": rng.choice(RISK_REASONS[risk_level]),
            }
        )

    for task in [item for item in tasks if item["status"] == "pending_approval"]:
        add_approval(task, rng.choice(["high", "critical"]), "pending")

    for task in rng.sample([item for item in tasks if item["status"] == "completed"], k=20):
        add_approval(task, rng.choice(["high", "critical"]), "approved", response_min=rng.randint(5, 90))

    return approvals


def _generate_model_calls(rng: random.Random, tasks: list[dict]) -> list[dict]:
    calls = []
    for task in tasks[:80]:
        tier = rng.choice(["light", "standard", "heavy"])
        total_tokens = rng.randint(800, 8000)
        calls.append(
            {
                "org_id": ORG_ID,
                "task_id": task["task_id"],
                "model_tier": tier,
                "cached": rng.random() < 0.25,
                "total_tokens": total_tokens,
                "estimated_cost_usd": round(total_tokens / 1000 * {"light": 0.0002, "standard": 0.001, "heavy": 0.005}[tier], 4),
            }
        )
    return calls


def _seed_rag_documents() -> None:
    rag_chain = get_rag_chain()
    vector_store: VectorStore = rag_chain.retriever.vector_store
    embedder = Embedder(provider=EmbeddingProvider.HASH)
    config = ChunkConfig()

    if vector_store.stats()["total_chunks"] > 0:
        return

    for document in _COMPLIANCE_DOCS:
        metadata = {
            "source_file": document["source_file"],
            "type": document["type"],
            "organization_id": ORG_ID,
        }
        chunks = split_document(document["text"], config, metadata)
        embeddings = []
        for chunk in chunks:
            embeddings.append(embedder._embed(chunk.content, is_query=False))
        vector_store.add_chunks(chunks, embeddings)


def populate_all_stores(seed: int = 20260410) -> None:
    rng = random.Random(seed)
    now = datetime.utcnow()

    tasks = _generate_tasks(rng, now)
    approvals = _generate_approvals(rng, tasks)
    model_calls = _generate_model_calls(rng, tasks)

    configure_dashboard_stores(tasks=tasks, approvals=approvals, model_calls=model_calls)
    _seed_rag_documents()

    if trace_store.list(limit=1):
        return

    LOG.info(
        "Enterprise demo stores populated",
        tasks=len(tasks),
        approvals=len(approvals),
        model_calls=len(model_calls),
    )
