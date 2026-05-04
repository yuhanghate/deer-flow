/*
 Navicat Premium Dump SQL

 Source Server         : Postgresql (10.35.65.47)
 Source Server Type    : PostgreSQL
 Source Server Version : 160013 (160013)
 Source Host           : 10.35.65.47:5432
 Source Catalog        : deerflow
 Source Schema         : public

 Target Server Type    : PostgreSQL
 Target Server Version : 160013 (160013)
 File Encoding         : 65001

 Date: 04/05/2026 22:08:38

 表结构说明（共 11 张表，分 4 类）：

 ┌──────────────────────────────────────────────────────────────────┐
 │ 1. 用户认证类                                                     │
 │    users                    用户表（账号、角色、OAuth 登录）         │
 ├──────────────────────────────────────────────────────────────────┤
 │ 2. 对话/运行类（业务核心）                                          │
 │    threads_meta             对话线程元信息（对话列表、标题、用户归属）  │
 │    runs                     每次对话的运行记录（模型、token 用量、状态）│
 │    run_events               运行事件流水（消息流、trace、生命周期事件） │
 │    feedback                 用户对每次运行的反馈（点赞/踩、评论）       │
 ├──────────────────────────────────────────────────────────────────┤
 │ 3. LangGraph 状态持久化（框架内置）                                  │
 │    checkpoints              对话状态快照（LangGraph checkpointer）   │
 │    checkpoint_blobs         状态通道数据二进制存储                   │
 │    checkpoint_writes        状态写入记录                           │
 │    checkpoint_migrations    checkpoint 迁移版本                   │
 ├──────────────────────────────────────────────────────────────────┤
 │ 4. LangGraph Store（通用 KV 存储）                                  │
 │    store                    带 TTL 的 JSON KV 存储                 │
 │    store_migrations         store 迁移版本                        │
 └──────────────────────────────────────────────────────────────────┘

 关联关系：

   users 1 ── N threads_meta      (user_id)
   users 1 ── N runs              (user_id)
   users 1 ── N run_events        (user_id)
   users 1 ── N feedback          (user_id)

   threads_meta 1 ── N runs       (thread_id)
   threads_meta 1 ── N run_events (thread_id)

   runs 1 ── N run_events         (thread_id + run_id)
   runs 1 ── N feedback           (thread_id + run_id)

   checkpoints / checkpoint_blobs / checkpoint_writes 通过 thread_id 关联 threads_meta
   store 独立 KV 表，无外键关联

*/


-- ============================================================================
-- 1. 用户认证类
-- ============================================================================

-- ----------------------------
-- Table structure for users
-- 用户表：存储系统账号、密码、角色、OAuth 第三方登录绑定
-- 系统角色：admin（管理员） / user（普通用户）
-- 关联：1 个用户 → N 个对话线程 / N 条运行记录 / N 条反馈
-- ----------------------------
DROP TABLE IF EXISTS "public"."users";
CREATE TABLE "public"."users" (
  "id" varchar(36) COLLATE "pg_catalog"."default" NOT NULL,          -- 用户主键（UUID 字符串）
  "email" varchar(320) COLLATE "pg_catalog"."default" NOT NULL,      -- 邮箱地址（唯一）
  "password_hash" varchar(128) COLLATE "pg_catalog"."default",       -- bcrypt 密码哈希（OAuth 用户为空）
  "system_role" varchar(16) COLLATE "pg_catalog"."default" NOT NULL, -- 系统角色：admin / user
  "created_at" timestamptz(6) NOT NULL,                              -- 创建时间（UTC）
  "oauth_provider" varchar(32) COLLATE "pg_catalog"."default",       -- OAuth 提供方（github / google 等）
  "oauth_id" varchar(128) COLLATE "pg_catalog"."default",            -- OAuth 第三方用户 ID
  "needs_setup" bool NOT NULL,                                       -- 是否需要初始化设置（管理员首次登录）
  "token_version" int4 NOT NULL                                      -- JWT 版本，修改密码时递增以废除旧 token
);
ALTER TABLE "public"."users" OWNER TO "root";

-- ----------------------------
-- Records of users
-- ----------------------------


-- ============================================================================
-- 2. 对话/运行类（业务核心）
-- ============================================================================

-- ----------------------------
-- Table structure for threads_meta
-- 对话线程元信息表：每个线程对应一次独立的对话会话
-- 关联：N 条线程 → 1 个用户（user_id）；1 条线程 → N 次运行（runs）
-- ----------------------------
DROP TABLE IF EXISTS "public"."threads_meta";
CREATE TABLE "public"."threads_meta" (
  "thread_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,   -- 线程主键（UUID）
  "assistant_id" varchar(128) COLLATE "pg_catalog"."default",        -- 关联的助手 ID
  "user_id" varchar(64) COLLATE "pg_catalog"."default",              -- 所属用户 ID → users.id
  "display_name" varchar(256) COLLATE "pg_catalog"."default",        -- 线程显示名称（自动生成的标题）
  "status" varchar(20) COLLATE "pg_catalog"."default" NOT NULL,      -- 线程状态：idle / busy / error
  "metadata_json" json NOT NULL,                                     -- 扩展元数据（JSON）
  "created_at" timestamptz(6) NOT NULL,                              -- 创建时间
  "updated_at" timestamptz(6) NOT NULL                               -- 更新时间
);
ALTER TABLE "public"."threads_meta" OWNER TO "root";

-- ----------------------------
-- Records of threads_meta
-- ----------------------------


-- ----------------------------
-- Table structure for runs
-- 运行记录表：每次用户发送消息并收到 AI 回复算一次 run
-- 记录了模型名称、token 用量、运行状态、错误信息等
-- 关联：N 次运行 → 1 个线程（thread_id）；N 次运行 → 1 个用户（user_id）
--       1 次运行 → N 条事件（run_events）；1 次运行 → N 条反馈（feedback）
-- ----------------------------
DROP TABLE IF EXISTS "public"."runs";
CREATE TABLE "public"."runs" (
  "run_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,      -- 运行主键（UUID）
  "thread_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,   -- 所属线程 ID → threads_meta.thread_id
  "assistant_id" varchar(128) COLLATE "pg_catalog"."default",        -- 关联的助手 ID
  "user_id" varchar(64) COLLATE "pg_catalog"."default",              -- 发起用户 ID → users.id
  "status" varchar(20) COLLATE "pg_catalog"."default" NOT NULL,      -- 运行状态：pending / running / success / error / timeout / interrupted
  "model_name" varchar(128) COLLATE "pg_catalog"."default",          -- 使用的模型名称
  "multitask_strategy" varchar(20) COLLATE "pg_catalog"."default" NOT NULL, -- 多任务策略：reject / enqueue / interrupt
  "metadata_json" json NOT NULL,                                     -- 运行元数据（JSON）
  "kwargs_json" json NOT NULL,                                       -- 运行参数（JSON）
  "error" text COLLATE "pg_catalog"."default",                       -- 错误信息（失败时）
  "message_count" int4 NOT NULL,                                     -- 消息总数
  "first_human_message" text COLLATE "pg_catalog"."default",         -- 用户首条消息（方便列表页展示）
  "last_ai_message" text COLLATE "pg_catalog"."default",             -- AI 最后回复（方便列表页展示）
  "total_input_tokens" int4 NOT NULL,                                -- 输入 token 总数
  "total_output_tokens" int4 NOT NULL,                               -- 输出 token 总数
  "total_tokens" int4 NOT NULL,                                      -- 总 token 用量（input + output）
  "llm_call_count" int4 NOT NULL,                                    -- LLM 调用次数
  "lead_agent_tokens" int4 NOT NULL,                                 -- 主 agent 消耗的 token
  "subagent_tokens" int4 NOT NULL,                                   -- 子 agent 消耗的 token
  "middleware_tokens" int4 NOT NULL,                                 -- 中间件消耗的 token
  "follow_up_to_run_id" varchar(64) COLLATE "pg_catalog"."default",  -- 关联的前序 run_id（追问场景）
  "created_at" timestamptz(6) NOT NULL,                              -- 创建时间
  "updated_at" timestamptz(6) NOT NULL                               -- 更新时间
);
ALTER TABLE "public"."runs" OWNER TO "root";

-- ----------------------------
-- Records of runs
-- ----------------------------


-- ----------------------------
-- Table structure for run_events
-- 运行事件流水表：记录每次运行中的每一条事件（AI 文本增量、工具调用、工具结果、生命周期事件）
-- 通过 seq 字段保证同一线程内的事件顺序
-- 关联：N 条事件 → 1 个线程（thread_id）；N 条事件 → 1 次运行（run_id）
-- ----------------------------
DROP TABLE IF EXISTS "public"."run_events";
CREATE TABLE "public"."run_events" (
  "id" int4 NOT NULL DEFAULT nextval('run_events_id_seq'::regclass), -- 自增主键
  "thread_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,   -- 所属线程 ID → threads_meta.thread_id
  "run_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,      -- 所属运行 ID → runs.run_id
  "user_id" varchar(64) COLLATE "pg_catalog"."default",              -- 所属用户 ID → users.id
  "event_type" varchar(32) COLLATE "pg_catalog"."default" NOT NULL,  -- 事件类型（如 agent_message, tool_call, tool_result）
  "category" varchar(16) COLLATE "pg_catalog"."default" NOT NULL,    -- 事件分类：message / trace / lifecycle
  "content" text COLLATE "pg_catalog"."default" NOT NULL,            -- 事件内容（AI 回复文本、工具参数等）
  "event_metadata" json NOT NULL,                                    -- 事件扩展元数据（JSON）
  "seq" int4 NOT NULL,                                               -- 线程内事件序号（递增，保证顺序）
  "created_at" timestamptz(6) NOT NULL                               -- 创建时间
);
ALTER TABLE "public"."run_events" OWNER TO "root";

-- ----------------------------
-- Records of run_events
-- ----------------------------


-- ----------------------------
-- Table structure for feedback
-- 用户反馈表：记录用户对每次运行的评价（点赞/踩）
-- 关联：N 条反馈 → 1 次运行（thread_id + run_id）；N 条反馈 → 1 个用户（user_id）
-- 同一用户对同一运行的反馈唯一（uq_feedback_thread_run_user）
-- ----------------------------
DROP TABLE IF EXISTS "public"."feedback";
CREATE TABLE "public"."feedback" (
  "feedback_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL, -- 反馈主键（UUID）
  "run_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,      -- 关联的运行 ID → runs.run_id
  "thread_id" varchar(64) COLLATE "pg_catalog"."default" NOT NULL,   -- 关联的线程 ID → threads_meta.thread_id
  "user_id" varchar(64) COLLATE "pg_catalog"."default",              -- 反馈用户 ID → users.id
  "message_id" varchar(64) COLLATE "pg_catalog"."default",           -- 关联的具体消息 ID（可选）
  "rating" int4 NOT NULL,                                            -- 评分：+1（点赞） / -1（点踩）
  "comment" text COLLATE "pg_catalog"."default",                     -- 用户评论（可选）
  "created_at" timestamptz(6) NOT NULL                               -- 反馈时间
);
ALTER TABLE "public"."feedback" OWNER TO "root";

-- ----------------------------
-- Records of feedback
-- ----------------------------


-- ============================================================================
-- 3. LangGraph 状态持久化（框架内置，由 langgraph-checkpoint-postgres 管理）
-- ============================================================================

-- ----------------------------
-- Table structure for checkpoints
-- 对话状态快照表：LangGraph checkpointer 核心表
-- 记录每次对话的状态快照（messages、artifacts、todos 等），支持对话恢复和历史回溯
-- 关联：通过 thread_id 关联 threads_meta.thread_id
-- ----------------------------
DROP TABLE IF EXISTS "public"."checkpoints";
CREATE TABLE "public"."checkpoints" (
  "thread_id" text COLLATE "pg_catalog"."default" NOT NULL,          -- 所属线程 ID
  "checkpoint_ns" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT ''::text, -- 命名空间（子 agent 隔离）
  "checkpoint_id" text COLLATE "pg_catalog"."default" NOT NULL,      -- 快照 ID（主键之一）
  "parent_checkpoint_id" text COLLATE "pg_catalog"."default",        -- 父快照 ID（构建状态时间线）
  "type" text COLLATE "pg_catalog"."default",                        -- 快照类型
  "checkpoint" jsonb NOT NULL,                                       -- 完整状态快照（JSONB）
  "metadata" jsonb NOT NULL DEFAULT '{}'::jsonb                      -- 快照元数据（时间戳、步骤数等）
);
ALTER TABLE "public"."checkpoints" OWNER TO "root";

-- ----------------------------
-- Records of checkpoints
-- ----------------------------
BEGIN;
COMMIT;

-- ----------------------------
-- Table structure for checkpoint_blobs
-- 状态通道数据存储：存储 checkpoint 中各 channel 的二进制数据
-- 与 checkpoints 表配合使用，checkpoint 存结构，blobs 存大数据
-- 关联：通过 thread_id + checkpoint_ns 关联 checkpoints
-- ----------------------------
DROP TABLE IF EXISTS "public"."checkpoint_blobs";
CREATE TABLE "public"."checkpoint_blobs" (
  "thread_id" text COLLATE "pg_catalog"."default" NOT NULL,          -- 所属线程 ID
  "checkpoint_ns" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT ''::text, -- 命名空间
  "channel" text COLLATE "pg_catalog"."default" NOT NULL,            -- 通道名称（messages、todos 等）
  "version" text COLLATE "pg_catalog"."default" NOT NULL,            -- 数据版本号
  "type" text COLLATE "pg_catalog"."default" NOT NULL,               -- 数据类型
  "blob" bytea                                                       -- 二进制数据
);
ALTER TABLE "public"."checkpoint_blobs" OWNER TO "root";

-- ----------------------------
-- Records of checkpoint_blobs
-- ----------------------------
BEGIN;
COMMIT;

-- ----------------------------
-- Table structure for checkpoint_writes
-- 状态写入记录表：记录每次 checkpointer 写入的中间状态
-- 用于支持 LangGraph 的时间旅行、断点恢复等功能
-- 关联：通过 thread_id + checkpoint_ns 关联 checkpoints
-- ----------------------------
DROP TABLE IF EXISTS "public"."checkpoint_writes";
CREATE TABLE "public"."checkpoint_writes" (
  "thread_id" text COLLATE "pg_catalog"."default" NOT NULL,          -- 所属线程 ID
  "checkpoint_ns" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT ''::text, -- 命名空间
  "checkpoint_id" text COLLATE "pg_catalog"."default" NOT NULL,      -- 快照 ID
  "task_id" text COLLATE "pg_catalog"."default" NOT NULL,            -- 任务 ID
  "idx" int4 NOT NULL,                                               -- 写入索引
  "channel" text COLLATE "pg_catalog"."default" NOT NULL,            -- 通道名称
  "type" text COLLATE "pg_catalog"."default",                        -- 数据类型
  "blob" bytea NOT NULL,                                             -- 写入的二进制数据
  "task_path" text COLLATE "pg_catalog"."default" NOT NULL DEFAULT ''::text -- 任务路径（子 agent 追踪）
);
ALTER TABLE "public"."checkpoint_writes" OWNER TO "root";

-- ----------------------------
-- Records of checkpoint_writes
-- ----------------------------
BEGIN;
COMMIT;

-- ----------------------------
-- Table structure for checkpoint_migrations
-- Checkpoint 迁移版本表：记录 LangGraph checkpointer 的数据库结构迁移版本
-- ----------------------------
DROP TABLE IF EXISTS "public"."checkpoint_migrations";
CREATE TABLE "public"."checkpoint_migrations" (
  "v" int4 NOT NULL                                                  -- 迁移版本号
);
ALTER TABLE "public"."checkpoint_migrations" OWNER TO "root";

-- ----------------------------
-- Records of checkpoint_migrations
-- ----------------------------
BEGIN;
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (0);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (1);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (2);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (3);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (4);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (5);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (6);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (7);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (8);
INSERT INTO "public"."checkpoint_migrations" ("v") VALUES (9);
COMMIT;


-- ============================================================================
-- 4. LangGraph Store（通用 KV 存储，用于 Memory 等模块）
-- ============================================================================

-- ----------------------------
-- Table structure for store
-- 通用 KV 存储表：用于 LangGraph Store API，存储 Memory、配置等结构化数据
-- 支持 TTL 自动过期，通过 prefix 实现命名空间隔离
-- 独立表，无外键关联其他业务表
-- ----------------------------
DROP TABLE IF EXISTS "public"."store";
CREATE TABLE "public"."store" (
  "prefix" text COLLATE "pg_catalog"."default" NOT NULL,             -- 命名空间前缀（如 memory/、config/）
  "key" text COLLATE "pg_catalog"."default" NOT NULL,                -- 键名（prefix + key 联合主键）
  "value" jsonb NOT NULL,                                            -- 值（JSONB）
  "created_at" timestamptz(6) DEFAULT CURRENT_TIMESTAMP,             -- 创建时间
  "updated_at" timestamptz(6) DEFAULT CURRENT_TIMESTAMP,             -- 更新时间
  "expires_at" timestamptz(6),                                       -- 过期时间（到期自动清理）
  "ttl_minutes" int4                                                 -- TTL 时长（分钟）
);
ALTER TABLE "public"."store" OWNER TO "root";

-- ----------------------------
-- Records of store
-- ----------------------------
BEGIN;
COMMIT;

-- ----------------------------
-- Table structure for store_migrations
-- Store 迁移版本表：记录 LangGraph Store 的数据库结构迁移版本
-- ----------------------------
DROP TABLE IF EXISTS "public"."store_migrations";
CREATE TABLE "public"."store_migrations" (
  "v" int4 NOT NULL                                                  -- 迁移版本号
);
ALTER TABLE "public"."store_migrations" OWNER TO "root";

-- ----------------------------
-- Records of store_migrations
-- ----------------------------
BEGIN;
INSERT INTO "public"."store_migrations" ("v") VALUES (0);
INSERT INTO "public"."store_migrations" ("v") VALUES (1);
INSERT INTO "public"."store_migrations" ("v") VALUES (2);
INSERT INTO "public"."store_migrations" ("v") VALUES (3);
COMMIT;


-- ============================================================================
-- Sequences
-- ============================================================================

-- ----------------------------
-- Sequence structure for run_events_id_seq
-- run_events 表的自增主键序列
-- ----------------------------
DROP SEQUENCE IF EXISTS "public"."run_events_id_seq";
CREATE SEQUENCE "public"."run_events_id_seq"
INCREMENT 1
MINVALUE  1
MAXVALUE 2147483647
START 1
CACHE 1;
ALTER SEQUENCE "public"."run_events_id_seq" OWNER TO "root";


-- ============================================================================
-- Indexes & Constraints
-- ============================================================================

-- ----------------------------
-- Indexes for table users
-- ----------------------------
-- 邮箱唯一索引：保证每个邮箱只能注册一个账号
CREATE UNIQUE INDEX "ix_users_email" ON "public"."users" USING btree (
  "email" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
-- OAuth 身份唯一索引：同一 OAuth 提供方 + 第三方 ID 只能绑定一个账号
CREATE UNIQUE INDEX "idx_users_oauth_identity" ON "public"."users" USING btree (
  "oauth_provider" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "oauth_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key for table users
-- ----------------------------
ALTER TABLE "public"."users" ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");


-- ----------------------------
-- Indexes for table threads_meta
-- ----------------------------
CREATE INDEX "ix_threads_meta_assistant_id" ON "public"."threads_meta" USING btree (
  "assistant_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_threads_meta_user_id" ON "public"."threads_meta" USING btree (
  "user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key for table threads_meta
-- ----------------------------
ALTER TABLE "public"."threads_meta" ADD CONSTRAINT "threads_meta_pkey" PRIMARY KEY ("thread_id");


-- ----------------------------
-- Indexes for table runs
-- ----------------------------
CREATE INDEX "ix_runs_thread_id" ON "public"."runs" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
-- 复合索引：按线程 + 状态查询（筛选进行中的对话）
CREATE INDEX "ix_runs_thread_status" ON "public"."runs" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "status" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_runs_user_id" ON "public"."runs" USING btree (
  "user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key for table runs
-- ----------------------------
ALTER TABLE "public"."runs" ADD CONSTRAINT "runs_pkey" PRIMARY KEY ("run_id");


-- ----------------------------
-- Indexes for table run_events
-- ----------------------------
-- 复合索引：按线程 + 运行 + 序号查询（SSE 流式推送）
CREATE INDEX "ix_events_run" ON "public"."run_events" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "run_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "seq" "pg_catalog"."int4_ops" ASC NULLS LAST
);
-- 复合索引：按线程 + 分类 + 序号查询（分类事件流）
CREATE INDEX "ix_events_thread_cat_seq" ON "public"."run_events" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "category" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "seq" "pg_catalog"."int4_ops" ASC NULLS LAST
);
CREATE INDEX "ix_run_events_user_id" ON "public"."run_events" USING btree (
  "user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Constraints for table run_events
-- ----------------------------
-- 唯一约束：同一线程内序号不重复
ALTER TABLE "public"."run_events" ADD CONSTRAINT "uq_events_thread_seq" UNIQUE ("thread_id", "seq");

-- ----------------------------
-- Primary Key for table run_events
-- ----------------------------
ALTER TABLE "public"."run_events" ADD CONSTRAINT "run_events_pkey" PRIMARY KEY ("id");


-- ----------------------------
-- Indexes for table feedback
-- ----------------------------
CREATE INDEX "ix_feedback_run_id" ON "public"."feedback" USING btree (
  "run_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_feedback_thread_id" ON "public"."feedback" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "ix_feedback_user_id" ON "public"."feedback" USING btree (
  "user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Constraints for table feedback
-- ----------------------------
-- 唯一约束：同一用户对同一运行的反馈唯一
ALTER TABLE "public"."feedback" ADD CONSTRAINT "uq_feedback_thread_run_user" UNIQUE ("thread_id", "run_id", "user_id");

-- ----------------------------
-- Primary Key for table feedback
-- ----------------------------
ALTER TABLE "public"."feedback" ADD CONSTRAINT "feedback_pkey" PRIMARY KEY ("feedback_id");


-- ----------------------------
-- Indexes for table checkpoints
-- ----------------------------
CREATE INDEX "checkpoints_thread_id_idx" ON "public"."checkpoints" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key for table checkpoints
-- ----------------------------
ALTER TABLE "public"."checkpoints" ADD CONSTRAINT "checkpoints_pkey" PRIMARY KEY ("thread_id", "checkpoint_ns", "checkpoint_id");


-- ----------------------------
-- Indexes for table checkpoint_blobs
-- ----------------------------
CREATE INDEX "checkpoint_blobs_thread_id_idx" ON "public"."checkpoint_blobs" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key for table checkpoint_blobs
-- ----------------------------
ALTER TABLE "public"."checkpoint_blobs" ADD CONSTRAINT "checkpoint_blobs_pkey" PRIMARY KEY ("thread_id", "checkpoint_ns", "channel", "version");


-- ----------------------------
-- Indexes for table checkpoint_writes
-- ----------------------------
CREATE INDEX "checkpoint_writes_thread_id_idx" ON "public"."checkpoint_writes" USING btree (
  "thread_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key for table checkpoint_writes
-- ----------------------------
ALTER TABLE "public"."checkpoint_writes" ADD CONSTRAINT "checkpoint_writes_pkey" PRIMARY KEY ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx");


-- ----------------------------
-- Primary Key for table checkpoint_migrations
-- ----------------------------
ALTER TABLE "public"."checkpoint_migrations" ADD CONSTRAINT "checkpoint_migrations_pkey" PRIMARY KEY ("v");


-- ----------------------------
-- Indexes for table store
-- ----------------------------
-- 过期时间索引（部分索引）：只索引有过期时间的记录，用于定时清理
CREATE INDEX "idx_store_expires_at" ON "public"."store" USING btree (
  "expires_at" "pg_catalog"."timestamptz_ops" ASC NULLS LAST
) WHERE expires_at IS NOT NULL;
-- 前缀模式匹配索引：用于 prefix LIKE 'xxx%' 查询
CREATE INDEX "store_prefix_idx" ON "public"."store" USING btree (
  "prefix" COLLATE "pg_catalog"."default" "pg_catalog"."text_pattern_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key for table store
-- ----------------------------
ALTER TABLE "public"."store" ADD CONSTRAINT "store_pkey" PRIMARY KEY ("prefix", "key");


-- ----------------------------
-- Primary Key for table store_migrations
-- ----------------------------
ALTER TABLE "public"."store_migrations" ADD CONSTRAINT "store_migrations_pkey" PRIMARY KEY ("v");


-- ----------------------------
-- Alter sequences owned by
-- ----------------------------
ALTER SEQUENCE "public"."run_events_id_seq"
OWNED BY "public"."run_events"."id";
SELECT setval('"public"."run_events_id_seq"', 1, false);
