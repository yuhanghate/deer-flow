---
name: web-search-zhihuiya
description: 面向智慧芽（zhihuiya/patsnap）站点的专用检索与抽取流程。用户要求在智慧芽查专利、抓概要、做对比、去重、导出候选列表时使用本 skill。默认使用 DeerFlow 规划与 Playwright/CDP 原子工具执行（browser_open_session、browser_goto、browser_click、browser_type、browser_wait、browser_extract_text、browser_extract_list、browser_get_url、browser_close_session）。
---

# Web Search Zhihuiya

## 目标

在“已登录智慧芽”的前提下，稳定完成：检索 -> 抽取 -> 结构化 -> 比对去重。

## 关键词采集（必须）

1. 若用户未明确给出检索词，必须先调用 `ask_clarification` 追问关键词，再执行任何网页动作。
2. 关键词建议结构（优先级从高到低）：
   - 核心主题词（必填）：如“固态电池”
   - 可选限定词：申请人、时间范围、技术点
3. 拿到关键词后先标准化为 `query`（去首尾空格，保留原中文）。

## URL 优先检索（新增默认）

优先使用参数化 URL 直达智慧芽结果页，而不是先找搜索框：

`https://analytics.zhihuiya.com/search/result/standard/1?sort=sdesc&limit=50&q={query}&_type=query&search_mode=publication`

- `{query}` 必须做 URL 编码
- 直达失败（重定向登录页/加载异常）才回退 UI 交互流

## 执行流程（固定顺序）

1. **会话准备**
   - 调用 `browser_open_session`
   - 使用已配置 CDP（或本地浏览器）接管页面
2. **登录态确认**
   - 访问智慧芽首页或查询页
   - 通过头像/用户菜单等登录标志判断是否登录
   - 未登录时返回 `AUTH_REQUIRED` 并停止
3. **检索执行**
   - 优先 `browser_goto(参数化搜索URL)`
   - 必要时再回退到“填写关键词 + 点击搜索”
4. **结果抽取**
   - 优先用 `browser_extract_list` 一次抽取列表字段
   - 单条补充字段用 `browser_extract_text`
5. **规范化与去重**
   - 统一字段名
   - `app_no/pub_no` 硬去重，再做语义去重
6. **关闭会话**
   - 调用 `browser_close_session`

## 推荐工具调用顺序

`browser_open_session` -> `browser_goto` -> `browser_wait` -> `browser_type` -> `browser_click` -> `browser_wait` -> `browser_extract_list` -> `browser_get_url` -> `browser_close_session`

## 证据强约束（必须执行）

1. 任一步工具调用返回 `ok=false`，必须立即停止并返回错误码（如 `AUTH_REQUIRED`/`TIMEOUT`），不得继续生成结果。
2. 输出结果前必须携带以下证据字段：
   - `current_url`
   - `screenshot_path`
   - `raw_extract_preview`（抽取文本前 200-500 字）
3. 证据不全时只允许返回失败状态，禁止输出“已获取榜单/已完成比对”等结论。

## 输出结构（必须）

```json
{
  "site": "zhihuiya",
  "query": "string",
  "query_source": "user_input | clarified_by_user",
  "search_url": "string",
  "total_candidates": 0,
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
  "dedup_summary": {
    "raw_count": 0,
    "after_hard_dedup": 0,
    "after_semantic_dedup": 0
  },
  "errors": []
}
```

## 异常处理

- 登录失效：`AUTH_REQUIRED`
- 页面结构变化：`SELECTOR_NOT_FOUND`，并返回失败步骤
- 长时间无响应：`TIMEOUT`
- 人机验证或封禁：`BLOCKED`

## 不要做的事

- 不要在失败后无限重试同一点击动作。
- 不要在未拿到列表数据前直接输出“完成”。
- 不要在用户未给关键词时自行脑补检索词直接执行。
- 不要在 `ok=false` 或证据不全时输出具体候选条目。
- 不要泄露账号信息、cookie、token。

