# API 参考

本文档提供了 DeerFlow 后端 API 的完整参考。

## 概述

DeerFlow后端公开了两组API：

1. **LangGraph API** - 代理交互、线程和流 (`/api/langgraph/*`)
2. **网关 API** - 模型、MCP、技能、上传和工件 (`/api/*`)

所有 API 均通过端口 2026 的 Nginx 反向代理访问。

## LangGraph API

基本 URL：`/api/langgraph`

LangGraph API 由 LangGraph 服务器提供，并遵循 LangGraph SDK 约定。

### 话题

#### 创建线程

```http
POST /api/langgraph/threads
Content-Type: application/json
```

**请求正文：**

```json
{
  "metadata": {}
}
```

**回应：**

```json
{
  "thread_id": "abc123",
  "created_at": "2024-01-15T10:30:00Z",
  "metadata": {}
}
```

#### 获取线程状态

```http
GET /api/langgraph/threads/{thread_id}/state
```

**回应：**

```json
{
  "values": {
    "messages": [...],
    "sandbox": {...},
    "artifacts": [...],
    "thread_data": {...},
    "title": "Conversation Title"
  },
  "next": [],
  "config": {...}
}
```

### 运行

#### 创建运行

通过输入执行代理。

```http
POST /api/langgraph/threads/{thread_id}/runs
Content-Type: application/json
```

**请求正文：**

```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  },
  "config": {
    "recursion_limit": 100,
    "configurable": {
      "model_name": "gpt-4",
      "thinking_enabled": false,
      "is_plan_mode": false
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

**流模式兼容性：**
- 使用：`values`、`messages-tuple`、`custom`、`updates`、`events`、`debug`、`tasks`、`checkpoints`
- 不要使用：`tools`（在当前的`langgraph-api`中已弃用/无效，并且会触发模式验证错误）

**递归限制：**

`config.recursion_limit` 限制 LangGraph 将执行的图步骤数
在一次运行中。 `/api/langgraph/*` 端点直接连接到 LangGraph
服务器，因此继承 LangGraph 的本机默认值 **25**，即
对于计划模式或大量子代理运行而言太低 - 代理通常会出错
第一轮子代理结果出现后出现“GraphRecursionError”
在首席特工合成最终答案之前返回。

DeerFlow 自己的网关和 IM 通道路径通过默认设置来缓解这种情况
`build_run_config` 中的 `100` （参见 `backend/app/gateway/services.py`），但是
直接调用 LangGraph API 的客户端必须设置 `recursion_limit`
明确地在请求正文中。 `100` 与网关默认值匹配，是一个
安全起点；如果运行深层嵌套的子代理图，请增加它。

**可配置选项：**
- `model_name`（字符串）：覆盖默认模型
- `thinking_enabled`（布尔值）：为支持的模型启用扩展思维
- `is_plan_mode`（布尔值）：启用 TodoList 中间件进行任务跟踪

**响应：** 服务器发送事件 (SSE) 流

```
event: values
data: {"messages": [...], "title": "..."}

event: messages
data: {"content": "Hello! I'd be happy to help.", "role": "assistant"}

event: end
data: {}
```

#### 获取运行历史记录

```http
GET /api/langgraph/threads/{thread_id}/runs
```

**回应：**

```json
{
  "runs": [
    {
      "run_id": "run123",
      "status": "success",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### 流运行

实时流式传输响应。

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Content-Type: application/json
```

与 Create Run 相同的请求正文。返回 SSE 流。

---

## 网关API

基本 URL：`/api`

### 模型

#### 列出型号

从配置中获取所有可用的 LLM 模型。

```http
GET /api/models
```

**回应：**

```json
{
  "models": [
    {
      "name": "gpt-4",
      "display_name": "GPT-4",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "claude-3-opus",
      "display_name": "Claude 3 Opus",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "deepseek-v3",
      "display_name": "DeepSeek V3",
      "supports_thinking": true,
      "supports_vision": false
    }
  ]
}
```

#### 获取模型详细信息

```http
GET /api/models/{model_name}
```

**回应：**

```json
{
  "name": "gpt-4",
  "display_name": "GPT-4",
  "model": "gpt-4",
  "max_tokens": 4096,
  "supports_thinking": false,
  "supports_vision": true
}
```

### MCP 配置

#### 获取 MCP 配置

获取当前 MCP 服务器配置。

```http
GET /api/mcp/config
```

**回应：**

```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "***"
      },
      "description": "GitHub operations"
    },
    "filesystem": {
      "enabled": false,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "description": "File system access"
    }
  }
}
```

#### 更新 MCP 配置

更新 MCP 服务器配置。

```http
PUT /api/mcp/config
Content-Type: application/json
```

**请求正文：**

```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN"
      },
      "description": "GitHub operations"
    }
  }
}
```

**回应：**

```json
{
  "success": true,
  "message": "MCP configuration updated"
}
```

### 技能

#### 列出技能

获得所有可用的技能。

```http
GET /api/skills
```

**回应：**

```json
{
  "skills": [
    {
      "name": "pdf-processing",
      "display_name": "PDF Processing",
      "description": "Handle PDF documents efficiently",
      "enabled": true,
      "license": "MIT",
      "path": "public/pdf-processing"
    },
    {
      "name": "frontend-design",
      "display_name": "Frontend Design",
      "description": "Design and build frontend interfaces",
      "enabled": false,
      "license": "MIT",
      "path": "public/frontend-design"
    }
  ]
}
```

#### 获取技能详细信息

```http
GET /api/skills/{skill_name}
```

**回应：**

```json
{
  "name": "pdf-processing",
  "display_name": "PDF Processing",
  "description": "Handle PDF documents efficiently",
  "enabled": true,
  "license": "MIT",
  "path": "public/pdf-processing",
  "allowed_tools": ["read_file", "write_file", "bash"],
  "content": "# PDF Processing\n\nInstructions for the agent..."
}
```

####启用技能

```http
POST /api/skills/{skill_name}/enable
```

**回应：**

```json
{
  "success": true,
  "message": "Skill 'pdf-processing' enabled"
}
```

#### 禁用技能

```http
POST /api/skills/{skill_name}/disable
```

**回应：**

```json
{
  "success": true,
  "message": "Skill 'pdf-processing' disabled"
}
```

####安装技巧

从“.skill”文件安装技能。

```http
POST /api/skills/install
Content-Type: multipart/form-data
```

**请求正文：**
- `file`：要安装的`.skill` 文件

**回应：**

```json
{
  "success": true,
  "message": "Skill 'my-skill' installed successfully",
  "skill": {
    "name": "my-skill",
    "display_name": "My Skill",
    "path": "custom/my-skill"
  }
}
```

### 文件上传

#### 上传文件

将一个或多个文件上传到一个线程。

```http
POST /api/threads/{thread_id}/uploads
Content-Type: multipart/form-data
```

**请求正文：**
- `files`：要上传的一个或多个文件

**回应：**

```json
{
  "success": true,
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "markdown_file": "document.md",
      "markdown_path": ".deer-flow/threads/abc123/user-data/uploads/document.md",
      "markdown_virtual_path": "/mnt/user-data/uploads/document.md",
      "markdown_artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.md"
    }
  ],
  "message": "Successfully uploaded 1 file(s)"
}
```

**支持的文档格式**（自动转换为 Markdown）：
- PDF（`.pdf`）
- PowerPoint（`.ppt`、`.pptx`）
- Excel（`.xls`、`.xlsx`）
- Word（`.doc`、`.docx`）

#### 列出上传的文件

```http
GET /api/threads/{thread_id}/uploads/list
```

**回应：**

```json
{
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "extension": ".pdf",
      "modified": 1705997600.0
    }
  ],
  "count": 1
}
```

#### 删除文件

```http
DELETE /api/threads/{thread_id}/uploads/{filename}
```

**回应：**

```json
{
  "success": true,
  "message": "Deleted document.pdf"
}
```

### 线程清理

删除 LangGraph 线程本身后，删除 `.deer-flow/threads/{thread_id}` 下 DeerFlow 管理的本地线程文件。

```http
DELETE /api/threads/{thread_id}
```

**回应：**

```json
{
  "success": true,
  "message": "Deleted local thread data for abc123"
}
```

**错误行为：**
- `422` 表示无效线程 ID
- `500` 返回通用 `{"detail": "Failed to delete local thread data."}` 响应，而完整的异常详细信息保留在服务器日志中

### 文物

#### 获取神器

下载或查看代理生成的工件。

```http
GET /api/threads/{thread_id}/artifacts/{path}
```

**路径示例：**
- `/api/threads/abc123/artifacts/mnt/user-data/outputs/result.txt`
- `/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf`

**查询参数：**
- `download`（布尔值）：如果为`true`，则使用 Content-Disposition 标头强制下载

**响应：** 具有适当 Content-Type 的文件内容

---

## 错误响应

所有 API 以一致的格式返回错误：

```json
{
  "detail": "Error message describing what went wrong"
}
```

**HTTP 状态代码：**
- `400` - 错误请求：输入无效
- `404` - 未找到：未找到资源
- `422` - 验证错误：请求验证失败
- `500` - 内部服务器错误：服务器端错误

---

## 身份验证

目前，DeerFlow 尚未实现身份验证。无需凭据即可访问所有 API。

注意：这是关于DeerFlow API 身份验证。 MCP 出站连接仍可以对已配置的 HTTP/SSE MCP 服务器使用 OAuth。

对于生产部署，建议：
1. 使用 Nginx 进行基本身份验证或 OAuth 集成
2. 在 VPN 或专用网络后面部署
3. 实现自定义认证中间件

---

## 速率限制

默认情况下不实施速率限制。对于生产部署，在 Nginx 中配置速率限制：

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://backend;
}
```

---

## WebSocket 支持

LangGraph 服务器支持 WebSocket 连接以进行实时流传输。连接到：

```
ws://localhost:2026/api/langgraph/threads/{thread_id}/runs/stream
```

---

## SDK使用

### Python（LangGraph SDK）

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2026/api/langgraph")

# Create thread
thread = await client.threads.create()

# Run agent
async for event in client.runs.stream(
    thread["thread_id"],
    "lead_agent",
    input={"messages": [{"role": "user", "content": "Hello"}]},
    config={"configurable": {"model_name": "gpt-4"}},
    stream_mode=["values", "messages-tuple", "custom"],
):
    print(event)
```

### JavaScript/TypeScript

```typescript
// Using fetch for Gateway API
const response = await fetch('/api/models');
const data = await response.json();
console.log(data.models);

// Using EventSource for streaming
const eventSource = new EventSource(
  `/api/langgraph/threads/${threadId}/runs/stream`
);
eventSource.onmessage = (event) => {
  console.log(JSON.parse(event.data));
};
```

### cURL 示例

```bash
# List models
curl http://localhost:2026/api/models

# Get MCP config
curl http://localhost:2026/api/mcp/config

# Upload file
curl -X POST http://localhost:2026/api/threads/abc123/uploads \
  -F "files=@document.pdf"

# Enable skill
curl -X POST http://localhost:2026/api/skills/pdf-processing/enable

# Create thread and run agent
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -d '{}'

curl -X POST http://localhost:2026/api/langgraph/threads/abc123/runs \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "Hello"}]},
    "config": {
      "recursion_limit": 100,
      "configurable": {"model_name": "gpt-4"}
    }
  }'
```

> `/api/langgraph/*` 端点绕过 DeerFlow 的网关并继承
> LangGraph 的原生 `recursion_limit` 默认值为 25，对于
> 计划模式或子代理运行。显式设置 `config.recursion_limit` — 请参阅
> [创建运行](#create-run) 部分了解详细信息。