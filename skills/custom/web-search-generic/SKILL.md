---
name: web-search-generic
description: 面向任意网站的通用网页检索与结构化抽取 skill。用户指定非智慧芽站点、要求跨站采集、未知页面结构、按聊天驱动网页操作时使用本 skill。只使用 DeerFlow + Playwright/CDP 原子工具执行，不依赖 browser-use。重点是计划执行、可回放日志、统一字段输出与可控重试。
---

# Web Search Generic

## 目标

对未知或多变页面进行“可控探索”，并稳定输出结构化结果。

## 执行策略

### 1) 先计划

先输出 3-7 步执行计划，再开始调用浏览器工具。

如果任务是“搜索/检索类”且用户未提供关键词，先调用 `ask_clarification` 获取关键词，再进入网页执行。

会话策略默认使用 `browser_open_session(reuse_policy="task_isolated")`。仅在明确需要复用时才改为：

- 同一对话固定一个 tab：`reuse_policy="conversation_single_tab"` + 传入稳定 `conversation_id`
- 同一对话同域名复用：`reuse_policy="conversation_origin_tab"` + 传入稳定 `conversation_id`
- 用户明确要求“单独开新页面”：`force_new=true` 或 `open_in_new_tab=true`

### 2) 小步执行

每次只做一个原子动作，动作后立刻校验：

- 校验 URL 变化（`browser_get_url`）
- 校验元素出现（`browser_wait` + selector）
- 校验抽取内容非空（`browser_extract_text` / `browser_extract_list`）

### 3) 失败重试（有限）

- 同一步最多重试 2 次
- 仍失败则换策略（例如改 selector、回到上一步、刷新页面）
- 超过上限返回结构化错误，不死循环

## 推荐原子工具编排

`browser_open_session` -> `browser_goto` -> `browser_wait` -> `browser_click/browser_type` -> `browser_wait` -> `browser_extract_text/browser_extract_list` -> `browser_get_url` -> `browser_close_session`

## 证据强约束（必须执行）

1. 任一步工具调用返回 `ok=false`，必须立即停止执行并返回结构化错误，不得继续生成业务结果。
2. 最终回答必须包含以下证据字段，缺一不可：
   - `current_url`
   - `screenshot_path`
   - `raw_extract_preview`（抽取文本前 200-500 字）
3. 若证据字段不完整，只能返回“执行失败/证据不足”，禁止输出榜单、排名或具体数据。

## 抽取规范

优先抽取以下字段，缺失允许为空字符串：

- `title`
- `app_no`
- `pub_no`
- `assignee`
- `abstract`
- `source_url`

## 输出结构（必须）

```json
{
  "site": "string",
  "query": "string",
  "plan": ["step1", "step2"],
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
  "evidence": {
    "current_url": "string",
    "screenshot_path": "string",
    "raw_extract_preview": "string"
  },
  "errors": [
    {
      "code": "TIMEOUT",
      "step": "string",
      "message": "string"
    }
  ],
  "next_action": "string"
}
```

## 去重规则

1. `app_no` / `pub_no` 硬去重
2. `title + abstract` 语义去重
3. 合并重复项时保留多个 `source_url`

## 不要做的事

- 不要把多步动作塞进一个工具调用描述里。
- 不要在没有证据时声称“页面没有结果”。
- 不要在 `ok=false` 或证据缺失时输出任何具体榜单内容。
- 不要输出浏览器内部敏感信息（cookie/token/localStorage）。

