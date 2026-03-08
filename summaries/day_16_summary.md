# Day 16 — Demo Data Integration & Frontend-Backend Alignment

## 今日改动

将企业各模块后端的空内存存储填充为统一、互联的演示数据，修复前端页面与后端 API 的字段不匹配问题，使审批中心、审计日志、运营大屏在启动后即可直观展示完整业务数据。

### 1. 演示数据生成器（enterprise/demo_seed.py）

- 537 行 Python 模块，在 FastAPI 应用启动时由 `api_app.py` 调用 `populate_all_stores()`
- 使用确定性随机种子 `random.Random(42)` 保证每次启动数据一致
- 生成数据量：250 个任务、58 个审批请求（10 个 pending）、~950 条审计日志、1200 条模型调用记录、25 条缓存统计
- 所有 ID 体系与 `tests/fixtures/seed_demo_data.sql` 一致：组织 `o_demo_cmb`、6 个部门、4 条业务线、16 个用户
- 跨模块数据联通：同一个 task_id 在任务列表、审批请求、审计日志、模型调用中均可关联追溯

### 2. 前端-后端字段对齐

**审批中心（ApprovalsPage.tsx）：**
- 类型定义修正：`action_description` → `operation_description`、`department_name` → `department_id`、`business_line` → `business_line_id`、`screenshot_url` → `screenshot_path`
- 新增 `DEPT_NAMES` / `BL_NAMES` 查找表，将 ID 映射为可读中文名
- 演示数据 task_id 改为与种子数据一致的 `tsk_demo_XXXX` 格式
- 审批/拒绝请求体从 `{ remark }` 改为 `{ note }`，匹配后端 `DecisionRequest`

**审计日志（AuditLogsPage.tsx）：**
- 截图字段名修正：`screenshot_before_key` → `screenshot_before_url`、`screenshot_after_key` → `screenshot_after_url`

**运营大屏（DashboardPage.tsx）：**
- 从 4 卡片简单布局升级为 7 区块完整大屏：概览卡片、业务线饼图、任务趋势折线图、审批响应时间、LLM 成本分析表格、近期任务列表、成功率/平均耗时统计
- `delta_tasks` / `delta_success` 改为可选字段，无数据时不显示
- 新增 `/approval-time` 和 `/cost` API 调用及 fallback

### 3. 国际化扩展

- locales.ts 新增 50 行翻译键（中英双语各 25 条）
- 覆盖大屏新增区块：任务趋势、审批响应、LLM 成本、模型层级、近期任务表头等

## 设计决策

| 决策 | 理由 |
|------|------|
| 确定性随机种子（seed=42） | 每次重启数据完全一致，方便调试和演示 |
| 数据量级：250 任务 / 1200 模型调用 | 足以填充大屏图表产生直观效果，又不影响启动速度 |
| ID 复用 seed_demo_data.sql | 一套 ID 体系贯穿 SQL 种子数据和内存演示数据，消除数据孤岛 |
| 前端保留 fallback 演示数据 | API 不可达时仍有基本展示，开发阶段可脱离后端独立调试 |
| 部门/业务线 ID → 名称查找表放在前端 | 避免为了显示名称多一次 API 调用，静态映射足够 |

## 踩坑记录

1. **前后端字段命名不一致**：Day 12 创建前端页面时使用的字段名（如 `action_description`）与 Day 6/8 后端实际存储字段名（如 `operation_description`）不匹配，导致 API 返回数据后前端显示为空。需要逐字段核对后端 store schema。
2. **DashboardPage 可选字段处理**：后端 overview 接口不一定返回 `delta_tasks` 字段，前端模板字符串 `` `+${data.delta_tasks}%` `` 会渲染 `+undefined%`，需要 null check。
3. **conda multiline 脚本限制**：`conda run -n finrpa python -c "..."` 不支持多行字符串参数，验证脚本必须写入临时文件再执行。
4. **Windows GBK 编码陷阱**：`open('demo_seed.py').read()` 在 Windows 默认使用 GBK 编码，含中文注释的 UTF-8 文件会报 `UnicodeDecodeError`，必须显式指定 `encoding='utf-8'`。
