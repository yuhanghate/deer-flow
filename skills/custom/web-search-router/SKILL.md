---
name: web-search-router
description: 按站点类型把“网页检索/采集”任务路由到专用或通用执行流。用户提到智慧芽、指定站点、跨站检索、网页抽取、专利比对去重、先列计划再执行时使用本 skill。优先分流到 web-search-zhihuiya；未知或多站点任务分流到 web-search-generic。适用于 DeerFlow 规划 + Playwright/CDP 原子工具执行，不依赖 browser-use。
---

# Web Search Router

## 目标

把用户请求稳定分发到正确执行链路，减少执行阶段跑偏。

## 路由规则（严格按序）

0. **先检查是否有检索关键词**
   -> 无关键词时先调用 `ask_clarification` 询问，不进入网页执行
1. **命中智慧芽特征**（关键词如“智慧芽”“zhihuiya”“patsnap”）  
   -> 路由到 `web-search-zhihuiya`
2. **用户提供明确站点域名**，但非智慧芽  
   -> 路由到 `web-search-generic`
3. **用户说“全网/多个网站/随便找”**  
   -> 先用 `web-search-generic` 做站点探测，再回收结构化结果
4. **用户要求比对/去重/总结**  
   -> 先完成检索与抽取，再做统一 schema 聚合与去重

## 执行契约

- 必须先输出「执行计划（3-7 步）」再调用网页工具。
- 必须输出目标 skill 名称与原因（一句话）。
- 若缺少检索关键词，必须先追问，不得直接打开网页盲搜。
- 若需登录且当前站点未登录，先返回重认证提示，不盲目重试。
- 任何网页执行失败，返回结构化错误码：`AUTH_REQUIRED`、`TIMEOUT`、`SELECTOR_NOT_FOUND`、`BLOCKED`。

## 会话策略路由（新增）

在调用 `browser_open_session` 前，必须先决策 `reuse_policy`：

1. **默认**：`task_isolated`
   - 用于大多数任务，避免下载、全屏、登录态、弹窗等状态串扰
2. **同对话连续操作同一站点**：`conversation_origin_tab`
   - 必须传稳定 `conversation_id`（建议 thread_id）
   - 当目标 URL 与当前会话 origin 一致时复用
3. **用户明确要求“单独开一个”**：
   - 优先 `force_new=true`（强隔离）
   - 如果用户要“同会话另开页对照”，用 `open_in_new_tab=true`
4. **高风险动作（下载、全屏、登录、批量提交）**：
   - 强制退回 `task_isolated`，不与普通检索混用

### 决策表（直接执行）

- `用户含“单独开/新开页面/不要影响当前页”` -> `task_isolated + force_new=true`
- `同一对话且同域名连续检索` -> `conversation_origin_tab`
- `同一对话但跨域名切换` -> 新建会话（`task_isolated`）
- `包含下载/全屏/登录步骤` -> `task_isolated`

## 统一输出字段

所有分流后的结果最终聚合为同一结构：

```json
{
  "site": "string",
  "query": "string",
  "query_source": "user_input | clarified_by_user",
  "items": [
    {
      "title": "string",
      "app_no": "string",
      "pub_no": "string",
      "assignee": "string",
      "abstract": "string",
      "source_url": "string"
    }
  ],
  "session_plan": {
    "reuse_policy": "task_isolated | conversation_single_tab | conversation_origin_tab",
    "conversation_id": "string|null",
    "force_new": false,
    "open_in_new_tab": false
  },
  "errors": [],
  "next_action": "string"
}
```

## 去重策略

1. 先硬去重：`app_no` 或 `pub_no`
2. 再软去重：`title + abstract` 语义相似（高相似合并，保留来源）

## 不要做的事

- 不要直接跳过路由去执行复杂网页步骤。
- 不要在未确认登录态时持续点击和翻页。
- 不要在跨域名或高风险动作时盲目复用已有会话。
- 不要输出“必然成功/必然授权”等确定性结论。

