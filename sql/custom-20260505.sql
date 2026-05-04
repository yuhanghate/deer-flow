/*
  DeerFlow - VIP 付费功能 独立建表脚本
  日期: 2026-05-05
  更新: 2026-05-05 — input/output tokens 分别计费

  说明:
    本文件包含 4 张新增的计费相关表，与官方 deerflow-20260505.sql
    中的 11 张原有表完全独立，合并 main 分支时不会产生冲突。

  ┌──────────────────────────────────────────────────────────────────┐
  │ 新增表（共 4 张）                                                 │
  ├──────────────────────────────────────────────────────────────────┤
  │ subscription_plans    套餐定义（免费体验/基础/专业/旗舰/企业）     │
  │ user_quotas           用户 token 配额（每人一行，记录剩余额度）     │
  │ orders                订单表（记录每笔支付流水）                   │
  │ quota_logs            Token 用量流水（扣减/充值明细，用于对账）     │
  └──────────────────────────────────────────────────────────────────┘

  关联关系:

    users 1 ── N user_quotas          (user_id)
    users 1 ── N orders               (user_id)
    users 1 ── N quota_logs           (user_id)

    subscription_plans 1 ── N user_quotas  (plan_id)
    subscription_plans 1 ── N orders       (plan_id)

    runs 1 ── N quota_logs            (run_id)

  定价说明:
    成本价: 输入 ¥0.004/1K, 输出 ¥0.016/1K（6 倍于输入）
    售价:   输入 ¥0.012/1K, 输出 ¥0.048/1K（3 倍成本）
    套餐按 6:1（输入:输出）比例分配 tokens
*/


-- ============================================================================
-- 1. 套餐定义表
-- ============================================================================

-- subscription_plans
-- 存储可选的会员套餐，由管理员预置数据，不随用户操作新增行。
-- 关联：1 个套餐 → N 条用户配额记录；1 个套餐 → N 条订单
-- ----------------------------
DROP TABLE IF EXISTS "public"."subscription_plans";
CREATE TABLE "public"."subscription_plans" (
  "id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,          -- 套餐主键（UUID）
  "name" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,        -- 套餐名称：免费体验 / 基础版 / 专业版 / 旗舰版 / 企业版
  "description" text COLLATE "pg_catalog"."default",                 -- 套餐描述
  "price_cents" int4 NOT NULL,                                       -- 价格（分），免费套餐为 0
  "input_token_quota" int8 NOT NULL,                                 -- 赠送的输入 token 额度
  "output_token_quota" int8 NOT NULL,                                -- 赠送的输出 token 额度
  "is_default" bool NOT NULL DEFAULT false,                          -- 是否为新用户默认套餐（免费体验）
  "is_active" bool NOT NULL DEFAULT true,                            -- 是否可购买（下架后不可见）
  "sort_order" int4 NOT NULL DEFAULT 0,                              -- 展示排序（从小到大）
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP     -- 更新时间
);
ALTER TABLE "public"."subscription_plans" OWNER TO "root";

ALTER TABLE "public"."subscription_plans" ADD CONSTRAINT "subscription_plans_pkey" PRIMARY KEY ("id");

CREATE INDEX "ix_plans_is_active" ON "public"."subscription_plans" USING btree ("is_active");
CREATE INDEX "ix_plans_sort_order" ON "public"."subscription_plans" USING btree ("sort_order");

-- 预置套餐数据
-- 免费体验 ¥0   → 输入 300,000    + 输出 50,000
-- 基础版   ¥9.9 → 输入 1,500,000  + 输出 250,000
-- 专业版   ¥49  → 输入 7,500,000  + 输出 1,250,000
-- 旗舰版   ¥139 → 输入 21,250,000 + 输出 3,541,667
-- 企业版   ¥199 → 输入 30,500,000 + 输出 5,083,333
-- ----------------------------
INSERT INTO "public"."subscription_plans" ("id", "name", "description", "price_cents", "input_token_quota", "output_token_quota", "is_default", "is_active", "sort_order") VALUES
  ('plan-free-00000001',    '免费体验', '注册即送，用完即止',                         0,      300000,     50000,  true,  true, 0),
  ('plan-basic-00000002',   '基础版',   '9.9 元 / 输入 1.5M + 输出 250K',           990,    1500000,    250000, false, true, 1),
  ('plan-pro-00000003',     '专业版',   '49 元 / 输入 7.5M + 输出 1.25M',          4900,    7500000,   1250000, false, true, 2),
  ('plan-flagship-0000004', '旗舰版',   '139 元 / 输入 21.25M + 输出 3.54M',      13900,   21250000,   3541667, false, true, 3),
  ('plan-enterprise-00005', '企业版',   '199 元 / 输入 30.5M + 输出 5.08M',       19900,   30500000,   5083333, false, true, 4);


-- ============================================================================
-- 2. 用户配额表
-- ============================================================================

-- user_quotas
-- 记录每个用户当前剩余的 token 额度。每个用户只有一行。
-- 购买套餐后增加 input/output quota_remaining，每次运行完成后分别扣减实际消耗的
-- input_tokens 和 output_tokens。
-- 关联：N 条配额 → 1 个用户（user_id）；N 条配额 → 1 个套餐（plan_id）
-- ----------------------------
DROP TABLE IF EXISTS "public"."user_quotas";
CREATE TABLE "public"."user_quotas" (
  "id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,          -- 配额主键（UUID）
  "user_id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,     -- 所属用户 ID → users.id
  "plan_id" varchar(36) COLLATE "pg_catalog"."default",              -- 当前激活的套餐 ID → subscription_plans.id（免费体验时可能为空）
  "input_quota_total" int8 NOT NULL DEFAULT 0,                       -- 累计购买的输入 token 总额
  "input_quota_used" int8 NOT NULL DEFAULT 0,                        -- 已消耗的输入 token 数量
  "input_quota_remaining" int8 NOT NULL DEFAULT 0,                   -- 剩余可用输入 token
  "output_quota_total" int8 NOT NULL DEFAULT 0,                      -- 累计购买的输出 token 总额
  "output_quota_used" int8 NOT NULL DEFAULT 0,                       -- 已消耗的输出 token 数量
  "output_quota_remaining" int8 NOT NULL DEFAULT 0,                  -- 剩余可用输出 token
  "status" varchar(20) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'active', -- 状态：active（正常）/ exhausted（已用完）
  "first_activated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 首次激活时间（注册送免费额度时）
  "last_recharged_at" timestamptz(6),                                -- 最近一次充值时间
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP     -- 更新时间
);
ALTER TABLE "public"."user_quotas" OWNER TO "root";

ALTER TABLE "public"."user_quotas" ADD CONSTRAINT "user_quotas_pkey" PRIMARY KEY ("id");

-- 用户唯一索引：每个用户只有一条配额记录
CREATE UNIQUE INDEX "ix_quotas_user_id" ON "public"."user_quotas" USING btree ("user_id");
-- 状态索引：快速查找已用完额度的用户
CREATE INDEX "ix_quotas_status" ON "public"."user_quotas" USING btree ("status");


-- ============================================================================
-- 3. 订单表
-- ============================================================================

-- orders
-- 记录用户的每一笔支付订单。支付成功后自动给用户充值 token 额度。
-- 关联：N 条订单 → 1 个用户（user_id）；N 条订单 → 1 个套餐（plan_id）
-- ----------------------------
DROP TABLE IF EXISTS "public"."orders";
CREATE TABLE "public"."orders" (
  "id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,          -- 订单主键（UUID）
  "order_no" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,    -- 业务订单号（用户可见，如 DF20260505123456）
  "user_id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,     -- 下单用户 ID → users.id
  "plan_id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,     -- 购买的套餐 ID → subscription_plans.id
  "amount_cents" int4 NOT NULL,                                      -- 实际支付金额（分）
  "payment_method" varchar(32) COLLATE "pg_catalog"."default",       -- 支付方式：alipay / wechat_pay / stripe
  "payment_status" varchar(20) COLLATE "pg_catalog"."default" NOT NULL DEFAULT 'pending', -- 支付状态：pending / paid / failed / refunded
  "payment_id" varchar(128) COLLATE "pg_catalog"."default",          -- 第三方支付流水号
  "input_quota_granted" int8 NOT NULL DEFAULT 0,                     -- 本订单赠送的输入 token 额度
  "output_quota_granted" int8 NOT NULL DEFAULT 0,                    -- 本订单赠送的输出 token 额度
  "error_message" text COLLATE "pg_catalog"."default",               -- 支付失败原因
  "paid_at" timestamptz(6),                                          -- 支付完成时间
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,    -- 订单创建时间
  "updated_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP     -- 更新时间
);
ALTER TABLE "public"."orders" OWNER TO "root";

ALTER TABLE "public"."orders" ADD CONSTRAINT "orders_pkey" PRIMARY KEY ("id");

-- 业务订单号唯一索引
CREATE UNIQUE INDEX "ix_orders_order_no" ON "public"."orders" USING btree ("order_no");
-- 按用户查询订单历史
CREATE INDEX "ix_orders_user_id" ON "public"."orders" USING btree ("user_id");
-- 按支付状态筛选
CREATE INDEX "ix_orders_payment_status" ON "public"."orders" USING btree ("payment_status");
-- 第三方流水号索引（webhook 回调查询）
CREATE INDEX "ix_orders_payment_id" ON "public"."orders" USING btree ("payment_id");


-- ============================================================================
-- 4. Token 用量流水表
-- ============================================================================

-- quota_logs
-- 记录每一次 token 扣减详情，用于对账和用户查看用量明细。
-- 关联：N 条日志 → 1 个用户（user_id）；N 条日志 → 1 次运行（run_id）
-- ----------------------------
DROP TABLE IF EXISTS "public"."quota_logs";
CREATE TABLE "public"."quota_logs" (
  "id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,          -- 日志主键（UUID）
  "user_id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,     -- 所属用户 ID → users.id
  "run_id" varchar(64) COLLATE "pg_catalog"."default",               -- 关联的运行 ID → runs.run_id
  "change_type" varchar(20) COLLATE "pg_catalog"."default" NOT NULL, -- 变更类型：deduct（扣减）/ recharge（充值）/ grant（赠送）/ refund（退款）
  "input_change_amount" int8 NOT NULL,                               -- 输入 token 变更数量（扣减为负数，充值为正数）
  "output_change_amount" int8 NOT NULL,                              -- 输出 token 变更数量（扣减为负数，充值为正数）
  "input_balance_before" int8 NOT NULL,                              -- 变更前输入余额
  "input_balance_after" int8 NOT NULL,                               -- 变更后输入余额
  "output_balance_before" int8 NOT NULL,                             -- 变更前输出余额
  "output_balance_after" int8 NOT NULL,                              -- 变更后输出余额
  "remark" text COLLATE "pg_catalog"."default",                      -- 备注说明
  "created_at" timestamptz(6) NOT NULL DEFAULT CURRENT_TIMESTAMP     -- 记录时间
);
ALTER TABLE "public"."quota_logs" OWNER TO "root";

ALTER TABLE "public"."quota_logs" ADD CONSTRAINT "quota_logs_pkey" PRIMARY KEY ("id");

-- 按用户查询用量明细
CREATE INDEX "ix_quota_logs_user_id" ON "public"."quota_logs" USING btree ("user_id");
-- 按关联运行 ID 查询
CREATE INDEX "ix_quota_logs_run_id" ON "public"."quota_logs" USING btree ("run_id");
-- 按变更类型筛选
CREATE INDEX "ix_quota_logs_change_type" ON "public"."quota_logs" USING btree ("change_type");
