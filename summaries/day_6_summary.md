# Day 6 — 审批引擎与 Redis Pub/Sub

## 今日改动

完成完整的审批流引擎，支持按风险等级路由到不同审批人、协程挂起等待 Redis 消息、超时自动拒绝，核心工作分四部分：

1. **审批请求数据模型**：`enterprise/approval/models.py` 定义了 `ApprovalRequestModel`，记录审批全生命周期——task_id、发起组织/部门/业务线、风险等级与原因、操作截图路径、审批路由（目标审批部门与角色、抄送部门列表）、生命周期状态（pending → approved / rejected / timeout）、审批人 ID、决策时间与备注、超时配置。包含 `ApprovalStatus` 枚举和按风险等级区分的默认超时配置（high: 1 小时, critical: 30 分钟）
2. **Redis Pub/Sub 等待机制**：`enterprise/approval/pubsub.py` 实现了三个核心函数——`build_approval_request()` 从风险检测和路由结果构建审批记录；`wait_for_decision()` 订阅以 `approval:{id}` 为 key 的 Redis 频道，协程挂起等待审批消息或超时；`publish_decision()` 将审批决策发布到频道唤醒等待协程。`create_approval_and_wait()` 封装了完整流程：创建审批记录 → 持久化到数据库 → 订阅等待 → 根据结果更新记录状态
3. **审批操作 API**：`enterprise/approval/routes.py` 提供三个接口——`GET /enterprise/approvals/pending`（返回当前用户有权审批的待处理列表）、`POST /enterprise/approvals/{id}/approve`（通过审批）、`POST /enterprise/approvals/{id}/reject`（拒绝审批）。每个接口严格校验组织归属、部门审批权限、状态幂等性（已处理的请求返回 409 Conflict）
4. **路由注册**：在 `skyvern/forge/api_app.py` 中注册审批路由到 `/api/v1` 前缀下

新增测试 67 个（Day 6），累计 262 个，全部通过。

## 设计决策

### Redis Pub/Sub vs 轮询数据库

审批等待有两种实现方案：

- **轮询数据库**：任务协程每隔 N 秒查询 `approval_requests` 表的状态变化。实现简单，但存在延迟-资源消耗的 trade-off——轮询间隔短则数据库压力大，轮询间隔长则审批响应慢
- **Redis Pub/Sub（当前方案）**：任务协程订阅频道后完全挂起（不消耗 CPU），审批人操作后通过 publish 即时唤醒。延迟近乎为零，且不产生数据库轮询负载

选择 Pub/Sub 的核心理由：金融场景下 RPA 任务可能大量并发（如月末批量对账），每个高危操作都会产生一个等待中的协程。轮询方案在 100+ 并发审批时会产生显著的数据库压力，而 Pub/Sub 的订阅数量对 Redis 几乎没有额外开销。

### 超时策略：critical 短于 high

`DEFAULT_TIMEOUTS` 设置 critical 级别 30 分钟、high 级别 1 小时。直觉上 critical 似乎应该给予更长的审议时间，但实际设计相反，理由如下：

- critical 级别操作（如合规部审批的大额跨境汇款）通常有更严格的时效性要求，监管合规窗口往往以分钟计
- critical 操作路由到合规部专职审批人，响应速度预期快于普通部门的兼职审批人
- 超时后操作被自动拒绝（而非自动通过），短超时意味着更快地释放被挂起的 RPA 任务资源
- 组织可以通过 `timeout_override` 参数按需调整，默认值仅作为合理起点

### 内存 Store vs 数据库直连

API 路由层使用 `_approval_store` 字典而非直接注入 SQLAlchemy session，原因是：

- **测试隔离**：单元测试无需启动数据库，通过 `configure_store()` 注入字典即可完成全部 API 逻辑测试
- **关注点分离**：路由层负责权限校验和状态转换逻辑，持久化细节由 `pubsub.py` 的 `create_approval_and_wait()` 处理
- **渐进迁移**：生产部署时只需将 `_approval_store` 替换为数据库查询层，API 逻辑无需改动

### 审批权限的多层校验

审批操作执行三层权限校验，任一层不通过即拒绝：

1. **角色校验**（`require_approver` 依赖）：用户必须在至少一个部门持有 approver 角色
2. **组织校验**：审批请求的 `organization_id` 必须与当前用户的 `org_id` 一致
3. **部门校验**：用户必须在审批请求的 `approver_department_id` 中持有 approver 角色（或为 org_admin / 持有 cross_org_approve 权限）

三层校验确保：跨组织无法审批、跨部门无法越权、仅持有 operator 角色的用户无法审批。

## 金融企业场景下的工程意义

**审批即合规**：银行业的核心风控原则之一是"操作与审批分离"（dual control）。Day 3 在数据模型层实现了 operator/approver 互斥约束，Day 6 在运行时层实现了审批拦截。两者结合，从「谁能操作、谁能审批」到「高危操作必须被审批」形成了完整的双控链路。

**协程挂起的业务价值**：传统审批系统通常将任务拆分为"提交审批"和"审批通过后继续"两个独立步骤，需要复杂的状态机来恢复执行上下文。Redis Pub/Sub + asyncio 的方案让任务协程直接挂起在操作现场，审批通过后从挂起点继续执行，保持了完整的页面上下文和浏览器会话——这对 RPA 场景至关重要，因为页面状态（表单填写进度、多步骤操作的中间状态）难以序列化和恢复。

**部门级审批隔离**：对公信贷部的转账操作只能由对公信贷部的审批人审批，个人金融部的审批人看不到也无法操作。这与 Day 4 的数据隔离形成统一的安全边界——数据看不到，操作审不了，从可见性和可操作性两个维度实现了部门级隔离。

**超时即拒绝**：金融操作的超时策略采用"默认拒绝"而非"默认通过"，体现了安全领域的 fail-safe 原则。审批人未在规定时间内响应，操作被自动拒绝，RPA 任务资源被释放。这避免了因审批人休假或疏忽导致高危操作长时间挂起、最终被遗忘的风险。

## 踩坑记录

1. **asyncio event loop 在同步测试中不可用**：最初的 `TestApprovalPermission` 使用 `unittest.TestCase`，通过 `asyncio.get_event_loop().run_until_complete()` 调用异步的 `require_approver` 函数。Python 3.11 中 `get_event_loop()` 在无活跃 loop 时抛出 `RuntimeError`。修复方式：改为 `unittest.IsolatedAsyncioTestCase` + `await` 直接调用
2. **Pub/Sub 消息的 bytes vs str**：Redis 返回的消息 data 可能是 `bytes` 或 `str` 类型，取决于客户端配置。`wait_for_decision()` 需要处理两种情况——若为 bytes 则 decode 为 UTF-8 后再解析 JSON
