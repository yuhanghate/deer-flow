# 架构概述

本文档全面概述了 DeerFlow 后端架构。

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Client (Browser)                             │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          Nginx (Port 2026)                               │
│                    Unified Reverse Proxy Entry Point                      │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  /api/langgraph/*  →  LangGraph Server (2024)                      │  │
│  │  /api/*            →  Gateway API (8001)                           │  │
│  │  /*                →  Frontend (3000)                               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│   LangGraph Server  │ │    Gateway API      │ │     Frontend        │
│     (Port 2024)     │ │    (Port 8001)      │ │    (Port 3000)      │
│                     │ │                     │ │                     │
│  - Agent Runtime    │ │  - Models API       │ │  - Next.js App      │
│  - Thread Mgmt      │ │  - MCP Config       │ │  - React UI         │
│  - SSE Streaming    │ │  - Skills Mgmt      │ │  - Chat Interface   │
│  - Checkpointing    │ │  - File Uploads     │ │                     │
│                     │ │  - Thread Cleanup   │ │                     │
│                     │ │  - Artifacts        │ │                     │
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘
          │                       │
          │     ┌─────────────────┘
          │     │
          ▼     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Shared Configuration                              │
│  ┌─────────────────────────┐  ┌────────────────────────────────────────┐ │
│  │      config.yaml        │  │      extensions_config.json            │ │
│  │  - Models               │  │  - MCP Servers                         │ │
│  │  - Tools                │  │  - Skills State                        │ │
│  │  - Sandbox              │  │                                        │ │
│  │  - Summarization        │  │                                        │ │
│  └─────────────────────────┘  └────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

## 组件详细信息

### LangGraph 服务器

LangGraph 服务器是核心代理运行时，基于 LangGraph 构建，用于强大的多代理工作流程编排。

**入口点**：`packages/harness/deerflow/agents/lead_agent/agent.py:make_lead_agent`

**主要职责**：
- 代理创建和配置
- 线程状态管理
- 中间件链执行
- 工具执行编排
- SSE 流媒体实时响应

**配置**：`langgraph.json`

```json
{
  "agent": {
    "type": "agent",
    "path": "deerflow.agents:make_lead_agent"
  }
}
```

### 网关API

FastAPI 应用程序为非代理操作提供 REST 端点。

**入口点**：`app/gateway/app.py`

**路由器**：
- `models.py` - `/api/models` - 模型列表和详细信息
- `mcp.py` - `/api/mcp` - MCP 服务器配置
- `skills.py` - `/api/skills` - 技能管理
- `uploads.py` - `/api/threads/{id}/uploads` - 文件上传
- `threads.py` - `/api/threads/{id}` - LangGraph删除后本地DeerFlow线程数据清理
- `artifacts.py` - `/api/threads/{id}/artifacts` - 工件服务
- `suggestions.py` - `/api/threads/{id}/suggestions` - 后续建议生成

Web 会话删除流程现在分为两个后端表面：LangGraph 处理线程状态的“DELETE /api/langgraph/threads/{thread_id}”，然后网关“threads.py”路由器通过“Paths.delete_thread_dir()”删除 DeerFlow 管理的文件系统数据。

### 代理架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           make_lead_agent(config)                        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Middleware Chain                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 1. ThreadDataMiddleware  - Initialize workspace/uploads/outputs  │   │
│  │ 2. UploadsMiddleware     - Process uploaded files               │   │
│  │ 3. SandboxMiddleware     - Acquire sandbox environment          │   │
│  │ 4. SummarizationMiddleware - Context reduction (if enabled)     │   │
│  │ 5. TitleMiddleware       - Auto-generate titles                 │   │
│  │ 6. TodoListMiddleware    - Task tracking (if plan_mode)         │   │
│  │ 7. ViewImageMiddleware   - Vision model support                 │   │
│  │ 8. ClarificationMiddleware - Handle clarifications              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Agent Core                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │      Model       │  │      Tools       │  │    System Prompt     │   │
│  │  (from factory)  │  │  (configured +   │  │  (with skills)       │   │
│  │                  │  │   MCP + builtin) │  │                      │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 线程状态

`ThreadState` 通过附加字段扩展了 LangGraph 的 `AgentState`：

```python
class ThreadState(AgentState):
    # Core state from AgentState
    messages: list[BaseMessage]

    # DeerFlow extensions
    sandbox: dict             # Sandbox environment info
    artifacts: list[str]      # Generated file paths
    thread_data: dict         # {workspace, uploads, outputs} paths
    title: str | None         # Auto-generated conversation title
    todos: list[dict]         # Task tracking (plan mode)
    viewed_images: dict       # Vision model image data
```

### 沙盒系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Sandbox Architecture                           │
└─────────────────────────────────────────────────────────────────────────┘

                      ┌─────────────────────────┐
                      │    SandboxProvider      │ (Abstract)
                      │  - acquire()            │
                      │  - get()                │
                      │  - release()            │
                      └────────────┬────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                                         │
              ▼                                         ▼
┌─────────────────────────┐              ┌─────────────────────────┐
│  LocalSandboxProvider   │              │  AioSandboxProvider     │
│  (packages/harness/deerflow/sandbox/local.py) │              │  (packages/harness/deerflow/community/)       │
│                         │              │                         │
│  - Singleton instance   │              │  - Docker-based         │
│  - Direct execution     │              │  - Isolated containers  │
│  - Development use      │              │  - Production use       │
└─────────────────────────┘              └─────────────────────────┘

                      ┌─────────────────────────┐
                      │        Sandbox          │ (Abstract)
                      │  - execute_command()    │
                      │  - read_file()          │
                      │  - write_file()         │
                      │  - list_dir()           │
                      └─────────────────────────┘
```

**虚拟路径映射**：

|虚拟路径|物理路径|
|------------|----------------|
| `/mnt/用户数据/工作空间` | `backend/.deer-flow/threads/{thread_id}/user-data/workspace` |
| `/mnt/用户数据/上传` | `backend/.deer-flow/threads/{thread_id}/user-data/uploads` |
| `/mnt/用户数据/输出` | `backend/.deer-flow/threads/{thread_id}/user-data/outputs` |
| `/mnt/技能` | `鹿流/技能/` |

### 工具系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Tool Sources                                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   Built-in Tools    │  │  Configured Tools   │  │     MCP Tools       │
│  (packages/harness/deerflow/tools/)       │  │  (config.yaml)      │  │  (extensions.json)  │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ - present_file      │  │ - web_search        │  │ - github            │
│ - ask_clarification │  │ - web_fetch         │  │ - filesystem        │
│ - view_image        │  │ - bash              │  │ - postgres          │
│                     │  │ - read_file         │  │ - brave-search      │
│                     │  │ - write_file        │  │ - puppeteer         │
│                     │  │ - str_replace       │  │ - ...               │
│                     │  │ - ls                │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
           │                       │                       │
           └───────────────────────┴───────────────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   get_available_tools() │
                      │   (packages/harness/deerflow/tools/__init__)  │
                      └─────────────────────────┘
```

### 模型工厂

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Model Factory                                   │
│                     (packages/harness/deerflow/models/factory.py)                              │
└─────────────────────────────────────────────────────────────────────────┘

config.yaml:
┌─────────────────────────────────────────────────────────────────────────┐
│ models:                                                                  │
│   - name: gpt-4                                                         │
│     display_name: GPT-4                                                 │
│     use: langchain_openai:ChatOpenAI                                    │
│     model: gpt-4                                                        │
│     api_key: $OPENAI_API_KEY                                            │
│     max_tokens: 4096                                                    │
│     supports_thinking: false                                            │
│     supports_vision: true                                               │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   create_chat_model()   │
                      │  - name: str            │
                      │  - thinking_enabled     │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   resolve_class()       │
                      │  (reflection system)    │
                      └────────────┬────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │   BaseChatModel         │
                      │  (LangChain instance)   │
                      └─────────────────────────┘
```

**支持的提供商**：
- OpenAI (`langchain_openai:ChatOpenAI`)
- 人类 (`langchain_anthropic:ChatAnthropic`)
- DeepSeek (`langchain_deepseek:ChatDeepSeek`)
- 通过 LangChain 集成进行定制

### MCP 集成

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          MCP Integration                                 │
│                        (packages/harness/deerflow/mcp/manager.py)                              │
└─────────────────────────────────────────────────────────────────────────┘

extensions_config.json:
┌─────────────────────────────────────────────────────────────────────────┐
│ {                                                                        │
│   "mcpServers": {                                                       │
│     "github": {                                                         │
│       "enabled": true,                                                  │
│       "type": "stdio",                                                  │
│       "command": "npx",                                                 │
│       "args": ["-y", "@modelcontextprotocol/server-github"],           │
│       "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"}                          │
│     }                                                                   │
│   }                                                                     │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │  MultiServerMCPClient   │
                      │  (langchain-mcp-adapters)│
                      └────────────┬────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
       ┌───────────┐        ┌───────────┐        ┌───────────┐
       │  stdio    │        │   SSE     │        │   HTTP    │
       │ transport │        │ transport │        │ transport │
       └───────────┘        └───────────┘        └───────────┘
```

### 技能系统

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Skills System                                   │
│                       (packages/harness/deerflow/skills/loader.py)                             │
└─────────────────────────────────────────────────────────────────────────┘

Directory Structure:
┌─────────────────────────────────────────────────────────────────────────┐
│ skills/                                                                  │
│ ├── public/                        # Public skills (committed)           │
│ │   ├── pdf-processing/                                                 │
│ │   │   └── SKILL.md                                                    │
│ │   ├── frontend-design/                                                │
│ │   │   └── SKILL.md                                                    │
│ │   └── ...                                                             │
│ └── custom/                        # Custom skills (gitignored)          │
│     └── user-installed/                                                 │
│         └── SKILL.md                                                    │
└─────────────────────────────────────────────────────────────────────────┘

SKILL.md Format:
┌─────────────────────────────────────────────────────────────────────────┐
│ ---                                                                      │
│ name: PDF Processing                                                     │
│ description: Handle PDF documents efficiently                            │
│ license: MIT                                                            │
│ allowed-tools:                                                          │
│   - read_file                                                           │
│   - write_file                                                          │
│   - bash                                                                │
│ ---                                                                      │
│                                                                          │
│ # Skill Instructions                                                     │
│ Content injected into system prompt...                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 请求流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Request Flow Example                             │
│                    User sends message to agent                           │
└─────────────────────────────────────────────────────────────────────────┘

1. Client → Nginx
   POST /api/langgraph/threads/{thread_id}/runs
   {"input": {"messages": [{"role": "user", "content": "Hello"}]}}

2. Nginx → LangGraph Server (2024)
   Proxied to LangGraph server

3. LangGraph Server
   a. Load/create thread state
   b. Execute middleware chain:
      - ThreadDataMiddleware: Set up paths
      - UploadsMiddleware: Inject file list
      - SandboxMiddleware: Acquire sandbox
      - SummarizationMiddleware: Check token limits
      - TitleMiddleware: Generate title if needed
      - TodoListMiddleware: Load todos (if plan mode)
      - ViewImageMiddleware: Process images
      - ClarificationMiddleware: Check for clarifications

   c. Execute agent:
      - Model processes messages
      - May call tools (bash, web_search, etc.)
      - Tools execute via sandbox
      - Results added to messages

   d. Stream response via SSE

4. Client receives streaming response
```

## 数据流

### 文件上传流程

```
1. Client uploads file
   POST /api/threads/{thread_id}/uploads
   Content-Type: multipart/form-data

2. Gateway receives file
   - Validates file
   - Stores in .deer-flow/threads/{thread_id}/user-data/uploads/
   - If document: converts to Markdown via markitdown

3. Returns response
   {
     "files": [{
       "filename": "doc.pdf",
       "path": ".deer-flow/.../uploads/doc.pdf",
       "virtual_path": "/mnt/user-data/uploads/doc.pdf",
       "artifact_url": "/api/threads/.../artifacts/mnt/.../doc.pdf"
     }]
   }

4. Next agent run
   - UploadsMiddleware lists files
   - Injects file list into messages
   - Agent can access via virtual_path
```

### 线程清理流程

```
1. Client deletes conversation via LangGraph
   DELETE /api/langgraph/threads/{thread_id}

2. Web UI follows up with Gateway cleanup
   DELETE /api/threads/{thread_id}

3. Gateway removes local DeerFlow-managed files
   - Deletes .deer-flow/threads/{thread_id}/ recursively
   - Missing directories are treated as a no-op
   - Invalid thread IDs are rejected before filesystem access
```

### 配置重新加载

```
1. Client updates MCP config
   PUT /api/mcp/config

2. Gateway writes extensions_config.json
   - Updates mcpServers section
   - File mtime changes

3. MCP Manager detects change
   - get_cached_mcp_tools() checks mtime
   - If changed: reinitializes MCP client
   - Loads updated server configurations

4. Next agent run uses new tools
```

## 安全考虑

### 沙箱隔离

- 代理代码在沙箱边界内执行
- 本地沙箱：直接执行（仅限开发）
- Docker沙箱：容器隔离（推荐生产）
- 文件操作中防止路径遍历

### API 安全

- 线程隔离：每个线程都有独立的数据目录
- 文件验证：检查上传的路径安全性
- 环境变量解析：秘密未存储在配置中

### MCP 安全

- 每个MCP服务器都在自己的进程中运行
- 环境变量在运行时解析
- 服务器可以独立启用/禁用

## 性能考虑因素

### 缓存

- MCP 工具通过文件 mtime 失效进行缓存
- 配置加载一次，文件更改时重新加载
- 技能在启动时解析一次，缓存在内存中

### 流媒体

- SSE用于实时响应流
- 减少第一个令牌的时间
- 实现长期操作的进度可见性

### 上下文管理

- 当接近限制时，摘要中间件会减少上下文
- 可配置的触发器：令牌、消息或分数
- 保留最近的消息，同时总结较旧的消息