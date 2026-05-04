# VIP 计费系统完整分析

> 分析时间：2026-05-05
> 分支：dev
> 状态：已重构为 input/output 分别计费

---

## 一、系统概览

VIP 计费系统是一个 **Token 预付费模型**——用户购买套餐获得 Token 额度，每次 AI 对话完成后按实际消耗分别扣减输入/输出 Token。

定价模型：

- 成本价：输入 ¥0.004/1K，输出 ¥0.016/1K（6 倍于输入）
- 售价：成本 × 3 = 输入 ¥0.012/1K，输出 ¥0.048/1K
- 套餐按 6:1 比例（输入:输出）分配 tokens

### 核心流程

```
用户注册 → 自动分配免费套餐 → 发起对话 → 对话完成 → 分别扣减 input/output tokens
                                                         ↓
                                                任一额度用尽 → 弹出升级对话框 → 选择套餐付费 → 充值 Token
```

---

## 二、数据库层（4 张表）

### 2.1 表关系图

```
users 1 ── N user_quotas          (user_id)
users 1 ── N orders               (user_id)
users 1 ── N quota_logs           (user_id)
subscription_plans 1 ── N user_quotas  (plan_id)
subscription_plans 1 ── N orders       (plan_id)
runs 1 ── N quota_logs            (run_id)
```

### 2.2 subscription_plans — 套餐定义表

关键字段：

- `input_token_quota` — 赠送的输入 token 额度
- `output_token_quota` — 赠送的输出 token 额度

预置数据：

| ID | 名称 | 价格 | 输入 tokens | 输出 tokens |
| --- | --- | --- | --- | --- |
| plan-free-00000001 | 免费体验 | ¥0 | 300,000 | 50,000 |
| plan-basic-00000002 | 基础版 | ¥9.9 | 1,500,000 | 250,000 |
| plan-pro-00000003 | 专业版 | ¥49 | 7,500,000 | 1,250,000 |
| plan-flagship-0000004 | 旗舰版 | ¥139 | 21,250,000 | 3,541,667 |
| plan-enterprise-00005 | 企业版 | ¥199 | 30,500,000 | 5,083,333 |

### 2.3 user_quotas — 用户额度表（每人一行）

关键字段：

- `input_quota_total / input_quota_used / input_quota_remaining`
- `output_quota_total / output_quota_used / output_quota_remaining`
- `status` — `active` / `exhausted`（input 和 output 都用尽时才为 exhausted）

### 2.4 orders — 订单表

关键字段：

- `input_quota_granted` — 本订单赠送的输入 token
- `output_quota_granted` — 本订单赠送的输出 token

### 2.5 quota_logs — 额度变更流水表

关键字段：

- `input_change_amount / output_change_amount` — 变更数量
- `input_balance_before / input_balance_after / output_balance_before / output_balance_after`

---

## 三、后端业务逻辑

### 3.1 BillingService 核心方法

文件：[backend/app/gateway/billing/service.py](backend/app/gateway/billing/service.py)

#### deduct_quota(user_id, run_id, input_tokens, output_tokens)

- 分别扣减 input/output 额度
- 两者都用尽时 `status = "exhausted"`，否则 `status = "active"`
- 写入审计日志（分别记录 input/output 变更量）

#### ensure_default_quota(user_id)

- 查找 `is_default=True` 的免费套餐
- 创建额度行，分别授予 input/output quota

#### create_order(user_id, plan_id)

- 记录套餐的 `input_token_quota` 和 `output_token_quota`

#### fulfil_order(order_id)

- 分别叠加 input/output quota
- 写入审计日志

### 3.2 对话完成后的自动扣减钩子

文件：[backend/app/gateway/services.py](backend/app/gateway/services.py)

在 `start_run()` 中挂载 `done_callback`：

```python
task.add_done_callback(
    lambda t: asyncio.create_task(_deduct_quota_on_completion(user_id, record.run_id, record, request.app))
)
```

`_deduct_quota_on_completion()` 流程：

1. 等待 0.5 秒（让 run_store 先持久化）
2. 优先从 `app.state.run_store.get(run_id)` 获取 `total_input_tokens` / `total_output_tokens`
3. 回退到 `record.metadata`（兼容旧路径）
4. 调用 `billing.deduct_quota(user_id, run_id, input_tokens, output_tokens)`

### 3.3 BillingService 初始化

文件：[backend/app/gateway/deps.py](backend/app/gateway/deps.py)

在 `langgraph_runtime()` 中初始化（有数据库时启用，无数据库时为 None）。

---

## 四、API 路由

文件：[backend/app/gateway/routers/billing.py](backend/app/gateway/routers/billing.py)

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/billing/plans` | 无需 | 获取所有可用套餐 |
| GET | `/api/billing/quota` | 需要 | 当前用户额度（自动确保默认额度） |
| GET | `/api/billing/orders` | 需要 | 当前用户订单历史 |
| POST | `/api/billing/orders` | 需要 | 创建购买订单 |
| POST | `/api/billing/webhook/{provider}` | 无需 | 支付回调（占位实现） |

响应模型变更：

- `QuotaResponse`：input/output 各自的 total/used/remaining
- `PlanResponse`：`input_token_quota` + `output_token_quota`
- `OrderHistoryItem`：`input_quota_granted` + `output_quota_granted`
- `OrderResponse`：同上

---

## 五、前端实现

### 5.1 类型定义

文件：[frontend/src/core/billing/types.ts](frontend/src/core/billing/types.ts)

- `BillingPlan`：`input_token_quota` + `output_token_quota`
- `UserQuota`：input/output 各自的 total/used/remaining
- `BillingOrder`：`input_quota_granted` + `output_quota_granted`

### 5.2 UI 组件

#### QuotaBar（额度条）

- 显示 input + output 总剩余 tokens
- Sheet 内分别展示输入/输出两个进度条卡片
- 任一使用 ≥ 80% 时变为红色警告色

#### PricingSheet（价格表）

- 每个套餐显示 "输入 X · 输出 Y"

#### UpgradeDialog（升级对话框）

- 只显示付费套餐
- 每个套餐显示 "输入 X · 输出 Y"

---

## 六、额度生命周期

```
[用户注册/首次登录]
       │
       ▼
ensure_default_quota() → 获得 输入 300K + 输出 50K
       │
       ▼
[用户发起对话]
       │
       ▼
[对话完成] → deduct_quota(input, output) → 分别扣减
       │
       ▼
[input_remaining <= 0 AND output_remaining <= 0]?
       ├─ 是 → status="exhausted" → 弹出升级对话框
       └─ 否 → status="active"
       │
       ▼
[用户选择套餐] → create_order() → 生成 pending 订单
       │
       ▼
[支付完成] → fulfil_order() → 分别叠加 input/output quota
       │
       ▼
[继续使用] → 回到"对话完成"阶段
```

---

## 七、当前未完成的模块

1. **支付回调**：`POST /api/billing/webhook/{provider}` 是占位实现
2. **额度用尽弹窗触发**：前端监听 `deerflow:quota-exhausted` 事件，尚未找到触发代码
3. **支付方式选择**：前端未传 `payment_method` 参数

---

## 八、关键代码文件索引

| 模块 | 文件路径 |
| --- | --- |
| ORM 模型 | [backend/packages/harness/deerflow/persistence/billing/__init__.py](backend/packages/harness/deerflow/persistence/billing/__init__.py) |
| 业务服务 | [backend/app/gateway/billing/service.py](backend/app/gateway/billing/service.py) |
| API 路由 | [backend/app/gateway/routers/billing.py](backend/app/gateway/routers/billing.py) |
| 依赖注入 | [backend/app/gateway/deps.py](backend/app/gateway/deps.py) |
| 扣减钩子 | [backend/app/gateway/services.py](backend/app/gateway/services.py) |
| 前端类型 | [frontend/src/core/billing/types.ts](frontend/src/core/billing/types.ts) |
| 前端 API | [frontend/src/core/billing/api.ts](frontend/src/core/billing/api.ts) |
| 额度条 | [frontend/src/components/workspace/billing/quota-bar.tsx](frontend/src/components/workspace/billing/quota-bar.tsx) |
| 价格表 | [frontend/src/components/workspace/billing/pricing-sheet.tsx](frontend/src/components/workspace/billing/pricing-sheet.tsx) |
| 升级对话框 | [frontend/src/components/workspace/billing/upgrade-dialog.tsx](frontend/src/components/workspace/billing/upgrade-dialog.tsx) |
| SQL 建表脚本 | [sql/custom-20260505.sql](sql/custom-20260505.sql) |
