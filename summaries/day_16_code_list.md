# Day 16 — Demo Data Integration 代码清单

## 新增文件

| 文件路径 | 功能说明 |
|---------|---------|
| `enterprise/demo_seed.py` | 企业演示数据生成器（537 行），启动时填充所有内存存储 |

## 修改文件 — 后端

| 文件路径 | 修改说明 |
|---------|---------|
| `skyvern/forge/api_app.py` | 在路由注册后调用 `populate_all_stores()` 填充演示数据（+4 行） |

## 修改文件 — 前端

| 文件路径 | 修改说明 |
|---------|---------|
| `skyvern-frontend/src/routes/enterprise/approvals/ApprovalsPage.tsx` | 字段对齐（operation_description/department_id/business_line_id/screenshot_path），新增部门/业务线名称查找表，修正请求体格式 |
| `skyvern-frontend/src/routes/enterprise/audit/AuditLogsPage.tsx` | 截图字段名修正（screenshot_before_url/screenshot_after_url） |
| `skyvern-frontend/src/routes/enterprise/dashboard/DashboardPage.tsx` | 升级为 7 区块完整大屏（概览/饼图/趋势/审批时间/LLM 成本/任务列表/统计），新增 API 调用，+435/-72 行 |
| `skyvern-frontend/src/i18n/locales.ts` | 新增 50 行中英翻译键（大屏新区块） |

## 数据生成规模

| 数据类型 | 数量 | 存储位置 |
|---------|------|---------|
| 任务（tasks） | 250 | dashboard store |
| 审批请求（approvals） | 58（10 pending） | approval store + dashboard store |
| 审计日志（audit logs） | ~950 | audit store |
| 模型调用（model calls） | 1200 | dashboard store |
| 缓存统计（cache stats） | 25 hits / 5 misses | action cache store |
